"""Offline Indian-law contract and routing tests; no legal verification claim."""
import copy
import json
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
from src.facts.indian_laws import INDIAN_LAWS_RESPONSE_SCHEMA, LESSON_TYPES, build_indian_laws_prompt, validate_indian_laws_content
from src.facts.evidence import normalize_evidence
from src.facts.visual_prompts import build_section_image_context

def fixture():
    return json.loads((Path(__file__).parent / 'fixtures/indian_law_lesson.json').read_text())

class IndianLawContractTests(unittest.TestCase):
    def test_all_formats_and_optional_context(self):
        fact = fixture()
        for kind in LESSON_TYPES:
            fact['indian_law_lesson']['lesson_type'] = kind
            fact['indian_law_lesson']['case_note'] = dict(name='Synthetic case',court='Test court',citation='Test citation',decision_date=None,
                question='A schema question.',decision='A synthetic decision.',significance='A schema example.',limits='Not a real judgment.',source_ids=['s1'])
            self.assertTrue(validate_indian_laws_content(fact), kind)
        l = fact['indian_law_lesson']
        l['commentary'] = [dict(title='Synthetic test commentary', explanation='For schema tests only.', limits='Not a legal authority.', source_ids=['s2'])]
        fact['sources'].append({'id':'s2','title':'Synthetic secondary reference','url':'https://example.org/commentary'})
        l['law_changes'] = [dict(label='Synthetic change',date=None,status='proposed',change='For schema tests only.',significance='Not a legal claim.',source_ids=['s1'])]
        self.assertTrue(validate_indian_laws_content(fact))

    def test_invalid_references_dates_authority_and_required_content(self):
        mutations = [lambda l:l['legal_basis'][0].update(source_ids=['missing']),
            lambda l:l['legal_basis'][0].update(source_kind='commentary'),
            lambda l:l['legal_basis'][0].update(commencement_date='2024-02-31'),
            lambda l:l['explanation_steps'][0].update(basis_ids=['missing']),
            lambda l:l['knowledge_checks'][0].update(related_step_ids=['missing']),
            lambda l:l['applicability'].update(jurisdiction=''),
            lambda l:l['worked_example'].update(limits=''),
            lambda l:l.update(lesson_type='case_explainer',case_note=None),
            lambda l:l.update(lesson_type='comparison',contrast_example=None)]
        for mutate in mutations:
            fact = fixture(); mutate(fact['indian_law_lesson'])
            self.assertFalse(validate_indian_laws_content(fact))
        for url in ('https://indiacode.nic.in.attacker.example/test', 'http://indiacode.nic.in/test', 'https://user:password@indiacode.nic.in/test'):
            fact = fixture(); fact['sources'][0]['url'] = url
            self.assertFalse(validate_indian_laws_content(fact))

    def test_nested_sources_images_and_prompt(self):
        fact = fixture()
        fact['indian_law_lesson']['plain_rule']['source_ids'] = ['s1','missing','s1']
        normalize_evidence(fact)
        self.assertEqual(fact['indian_law_lesson']['plain_rule']['source_ids'], ['s1'])
        self.assertTrue(validate_indian_laws_content(fact))
        fact['visual_suggestions']['overview'] = ''
        self.assertFalse(validate_indian_laws_content(fact))
        for value in ('excluded topic','commentary','jurisdiction','commencement','3-5-image','non-expert'):
            self.assertIn(value, build_indian_laws_prompt(['excluded topic']))
        self.assertIn('not authentic legal', build_section_image_context('cover', fixture()))

class IndianLawGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_schema_invalid_retry_and_server_owned_verification(self):
        from test_fact_evidence_lifecycle import generator_module
        generator = generator_module()
        generator.INDIAN_LAWS_RESPONSE_SCHEMA = INDIAN_LAWS_RESPONSE_SCHEMA
        generator.validate_indian_laws_content = validate_indian_laws_content
        invalid = fixture(); invalid['indian_law_lesson']['legal_basis'][0]['source_ids'] = ['missing']
        valid = fixture(); valid['indian_laws_validation'] = {'legal_currency_check':'verified', 'checked_at':'invented'}
        create = AsyncMock(side_effect=[types.SimpleNamespace(parsed=invalid),types.SimpleNamespace(parsed=valid)])
        generator.genai.Client.return_value.aio.models.generate_content = create
        with patch.object(generator.asyncio, 'sleep', new=AsyncMock()):
            result = await generator.generate_daily_fact('indian_laws')
        self.assertEqual(create.call_count, 2)
        self.assertIs(create.call_args.kwargs['config']['response_schema'], INDIAN_LAWS_RESPONSE_SCHEMA)
        self.assertEqual(result['indian_laws_validation']['legal_currency_check'], 'not_performed')
        self.assertEqual(result['indian_laws_validation']['retrieved_sources'], [])
        self.assertIsNone(result['indian_laws_validation']['checked_at'])

if __name__ == '__main__': unittest.main()
