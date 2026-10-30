"""Offline constitutional learning and fixed-official-edition quote checks."""
import asyncio
import copy
import json
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

APP = Path(__file__).resolve().parents[1] / 'app'
sys.path.insert(0, str(APP))
package = types.ModuleType('src.facts')
package.__path__ = [str(APP / 'src/facts')]
sys.modules.setdefault('src.facts', package)
from src.facts.constitution import CONSTITUTION_RESPONSE_SCHEMA, LESSON_TYPES, DIAGRAM_TYPES, build_constitution_prompt, validate_constitution_content, official_source
from src.facts.constitution_sources import enrich_constitution_text, article_excerpt, SOURCE_URL
from src.facts import constitution_sources
from src.facts.evidence import normalize_evidence
from src.facts.lifecycle import expected_image_keys
from src.facts.visual_prompts import build_section_image_context


def fixture():
    return json.loads((Path(__file__).parent / 'fixtures/constitution_lesson.json').read_text())


def optional_context(lesson):
    # Synthetic data tests the schema, not a legal claim or a real judgment.
    lesson['amendment_timeline'] = [{'label':'A test change', 'date':None, 'change':'A synthetic schema example.', 'significance':'Used only to test rendering metadata.', 'source_ids':['s1']}]
    lesson['case_note'] = {'name':'Synthetic test case', 'court':'Test court', 'citation':'Test citation', 'decision_date':None,
        'question':'A schema question.', 'decision':'A schema decision.', 'significance':'A test entry.', 'limits':'Not a real judgment.', 'source_ids':['s1']}


class ConstitutionContractTests(unittest.TestCase):
    def test_all_formats_and_common_contract(self):
        f = fixture()
        self.assertTrue(validate_constitution_content(f))
        optional_context(f['constitution_lesson'])
        for kind, diagram in zip(LESSON_TYPES, DIAGRAM_TYPES):
            f['constitution_lesson']['lesson_type'] = kind
            f['constitution_lesson']['diagram']['type'] = diagram
            self.assertTrue(validate_constitution_content(f), kind)
        self.assertIn('summary', CONSTITUTION_RESPONSE_SCHEMA['required'])
        self.assertNotIn('timeline', CONSTITUTION_RESPONSE_SCHEMA['required'])

    def test_references_dates_and_official_attribution(self):
        mutations = [
            lambda l: l['constitutional_basis'][0].update(source_ids=['missing']),
            lambda l: l['explanation_steps'][0].update(basis_ids=['missing']),
            lambda l: l['knowledge_checks'][0].update(related_step_ids=['missing']),
            lambda l: l['scope_and_limits'].update(who_it_concerns=[]),
            lambda l: l['constitutional_basis'][0].update(reference='Article unknown', quote_candidate='A long but unsupported legal quotation for this test.'),
            lambda l: l['diagram']['edges'][0].update(to_id='missing'),
            lambda l: l.update(lesson_type='case_explainer'),
            lambda l: l.update(lesson_type='amendment'),
        ]
        for mutate in mutations:
            f = fixture()
            mutate(f['constitution_lesson'])
            self.assertFalse(validate_constitution_content(f))
        f = fixture()
        f['sources'][0]['url'] = 'https://legislative.gov.in.attacker.test/source'
        self.assertFalse(validate_constitution_content(f))
        for url in ('http://www.sci.gov.in/file', 'https://user:pass@sci.gov.in/file', 'https://sci.gov.in:8443/file'):
            self.assertFalse(official_source(url))
        f = fixture()
        optional_context(f['constitution_lesson'])
        f['constitution_lesson']['case_note']['decision_date'] = '2024-02-31'
        self.assertFalse(validate_constitution_content(f))

    def test_image_budget_nested_sources_and_prompt(self):
        f = fixture()
        self.assertEqual(expected_image_keys(f['visual_suggestions']), ['cover', 'overview', 'how_it_works'])
        f['constitution_lesson']['big_idea']['source_ids'] = ['s1', 'missing', 's1']
        normalize_evidence(f)
        self.assertEqual(f['constitution_lesson']['big_idea']['source_ids'], ['s1'])
        f['visual_suggestions']['overview'] = ''
        self.assertFalse(validate_constitution_content(f))
        self.assertIn('not an authentic document', build_section_image_context('cover', fixture()))
        prompt = build_constitution_prompt(['old topic'])
        for text in ('old topic', 'non-expert', 'quote_candidate', 'verification dates', '3-5-image'):
            self.assertIn(text, prompt)


CANDIDATE = 'A synthetic excerpt with enough words to test exact matching safely.'
DOCUMENT = f'1. Test heading.—{CANDIDATE}\n2. Another test heading.—A different synthetic statement.\n3. Closing heading.'


class SourceMatchingTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(importlib.util.find_spec('pypdf') and importlib.util.find_spec('requests'), 'PDF runtime dependencies are not installed')
    def test_real_pdf_parser_with_a_bounded_local_response(self):
        # A real one-page PDF with synthetic wording, never a fabricated legal source.
        stream = f'BT /F1 12 Tf 40 200 Td (1. Synthetic heading.) Tj 0 -18 Td ({CANDIDATE}) Tj 0 -18 Td (2. Closing heading.) Tj ET'.encode()
        objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
            b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 300] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
            b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>', b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream']
        data, offsets = b'%PDF-1.4\n', [0]
        for i, obj in enumerate(objects, 1):
            offsets.append(len(data))
            data += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'
        xref = len(data)
        data += b'xref\n0 6\n0000000000 65535 f \n' + b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
        data += f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
        class Response:
            status_code = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def raise_for_status(self): pass
            def iter_content(self, size): return iter([data])
        with patch.object(constitution_sources, '_cache', None), patch('requests.get', return_value=Response()) as request:
            text, checked_at = constitution_sources._load_official_text()
        self.assertTrue(checked_at)
        self.assertEqual(article_excerpt(text, 'Article 1', CANDIDATE), CANDIDATE)
        self.assertEqual(request.call_args.args[0], SOURCE_URL)
        self.assertFalse(request.call_args.kwargs['allow_redirects'])

    def test_exact_matching_stays_inside_the_named_article(self):
        self.assertEqual(article_excerpt(DOCUMENT, 'Article 1', CANDIDATE), CANDIDATE)
        self.assertIsNone(article_excerpt(DOCUMENT, 'Article 2', CANDIDATE))
        self.assertIsNone(article_excerpt(DOCUMENT, 'Article 1', CANDIDATE.lower()))
        self.assertIsNone(article_excerpt(DOCUMENT, 'Article 999999', CANDIDATE))
        self.assertIsNone(article_excerpt('1. A missing closing boundary. ' + CANDIDATE, 'Article 1', CANDIDATE))

    async def test_model_verification_is_overwritten_and_candidates_are_removed(self):
        f = fixture()
        basis = f['constitution_lesson']['constitutional_basis'][0]
        basis.update(reference='Article 1', quote_candidate=CANDIDATE, original_text='Untrusted quote', text_verification={'status':'matched_official_edition'})
        f['constitution_lesson']['source_context'] = {'current_law_verified_at':'invented'}
        result = await enrich_constitution_text(f, loader=lambda: (DOCUMENT, '2026-10-30T00:00:00+00:00'))
        self.assertEqual(basis['original_text'], CANDIDATE)
        self.assertEqual(basis['text_verification']['source_url'], SOURCE_URL)
        self.assertNotIn('quote_candidate', basis)
        self.assertIsNone(result['constitution_lesson']['source_context']['current_law_verified_at'])
        self.assertEqual(result['constitution_validation']['legal_review'], 'not_performed')

    async def test_unavailable_or_mismatched_source_keeps_only_the_paraphrase(self):
        for loader in (lambda: ('', None), lambda: (DOCUMENT, '2026-10-30T00:00:00+00:00')):
            f = fixture()
            basis = f['constitution_lesson']['constitutional_basis'][0]
            basis['quote_candidate'] = CANDIDATE
            await enrich_constitution_text(f, loader=loader)
            self.assertEqual(basis['original_text'], '')
            self.assertEqual(basis['text_verification']['status'], 'not_verified')
            self.assertTrue(basis['plain_meaning'])

    async def test_absent_candidate_does_not_fetch_the_source(self):
        def unexpected():
            raise AssertionError('No source request expected')
        f = fixture()
        await enrich_constitution_text(f, loader=unexpected)
        self.assertIsNone(f['constitution_lesson']['source_context']['source_checked_at'])


class ConstitutionGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_schema_retry_enrichment_and_image_policy(self):
        from test_fact_evidence_lifecycle import generator_module
        generator = generator_module()
        generator.CONSTITUTION_RESPONSE_SCHEMA = CONSTITUTION_RESPONSE_SCHEMA
        generator.validate_constitution_content = validate_constitution_content
        generator.enrich_constitution_text = enrich_constitution_text
        invalid = copy.deepcopy(fixture())
        invalid['constitution_lesson']['explanation_steps'][0]['basis_ids'] = ['missing']
        create = AsyncMock(side_effect=[types.SimpleNamespace(parsed=invalid), types.SimpleNamespace(parsed=fixture())])
        generator.genai.Client.return_value.aio.models.generate_content = create
        with patch.object(generator.asyncio, 'sleep', new=AsyncMock()):
            result = await generator.generate_daily_fact('indian_constitution')
        self.assertEqual(create.call_count, 2)
        self.assertIs(create.call_args.kwargs['config']['response_schema'], CONSTITUTION_RESPONSE_SCHEMA)
        self.assertIsNone(result['constitution_lesson']['source_context']['current_law_verified_at'])
        self.assertEqual(expected_image_keys(result['visual_suggestions']), ['cover', 'overview', 'how_it_works'])


if __name__ == '__main__':
    unittest.main()
