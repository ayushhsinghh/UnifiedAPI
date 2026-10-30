"""Offline Biology schema, evidence, image-budget and generation regressions."""
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
from src.facts.biology import BIOLOGY_RESPONSE_SCHEMA, LESSON_TYPES, DIAGRAM_TYPES, build_biology_prompt, validate_biology_content
from src.facts.evidence import normalize_evidence
from src.facts.lifecycle import expected_image_keys
from src.facts.visual_prompts import build_section_image_context


def fixture():
    return json.loads((Path(__file__).parent / 'fixtures/biology_lesson.json').read_text())


class BiologyContractTests(unittest.TestCase):
    def test_five_lesson_types_and_legacy_fields(self):
        fact = fixture()
        self.assertTrue(validate_biology_content(fact))
        for lesson_type, diagram_type in zip(LESSON_TYPES, DIAGRAM_TYPES):
            fact['biology_lesson']['lesson_type'] = lesson_type
            fact['biology_lesson']['diagram']['type'] = diagram_type
            self.assertTrue(validate_biology_content(fact))
        for key in ('summary', 'core_mechanics', 'learning_takeaways', 'sources_or_references'):
            self.assertIn(key, BIOLOGY_RESPONSE_SCHEMA['required'])
        for key in ('timeline', 'history', 'quote'):
            self.assertNotIn(key, BIOLOGY_RESPONSE_SCHEMA['required'])

    def test_invalid_context_references_bounds_and_diagrams(self):
        mutations = [
            lambda l: l['context'].update(organism=''),
            lambda l: l['context'].update(conditions=[]),
            lambda l: l['explanation_steps'].pop(),
            lambda l: l['explanation_steps'][0].update(player_ids=['missing']),
            lambda l: l['knowledge_checks'][0].update(related_step_ids=['missing']),
            lambda l: l['big_idea'].update(analogy='Some comparison', analogy_limit=''),
            lambda l: l['diagram']['edges'][0].update(to_id='missing'),
            lambda l: l['diagram']['edges'][0].update(to_id='a'),
            lambda l: l['diagram'].update(type='script'),
            lambda l: l['diagram']['nodes'][1].update(id='a'),
            lambda l: l['evidence_and_limits'].update(scope_limits=[]),
            lambda l: l['evidence_and_limits'].update(evidence=[]),
            lambda l: l['change_scenario'].update(limitations=''),
        ]
        for mutate in mutations:
            fact = fixture()
            mutate(fact['biology_lesson'])
            self.assertFalse(validate_biology_content(fact))
        fact = fixture()
        fact['biology_lesson']['diagram'].update(type='none', nodes=[], edges=[])
        self.assertTrue(validate_biology_content(fact))
        fact = fixture()
        fact['biology_lesson']['lesson_type'] = 'inheritance'
        fact['biology_lesson']['diagram']['type'] = 'inheritance'
        fact['biology_lesson']['diagram']['edges'].append({'from_id': 'c', 'to_id': 'a', 'relationship': 'Invalid ancestry loop'})
        self.assertFalse(validate_biology_content(fact))

    def test_nested_source_ids_and_uncertainty(self):
        fact = fixture()
        fact['biology_lesson']['evidence_and_limits']['evidence'][0]['source_ids'] = ['s1', 'missing', 's1']
        normalize_evidence(fact)
        self.assertEqual(fact['biology_lesson']['evidence_and_limits']['evidence'][0]['source_ids'], ['s1'])
        self.assertNotIn('verified', fact['sources'][0])

    def test_image_budget_and_biology_image_context(self):
        fact = fixture()
        self.assertEqual(expected_image_keys(fact['visual_suggestions']), ['cover', 'overview', 'how_it_works'])
        fact['visual_suggestions']['overview'] = ''
        self.assertFalse(validate_biology_content(fact))
        self.assertIn('named organism, scale and conditions', build_section_image_context('cover', fixture()))
        prompt = build_biology_prompt(['old topic'])
        for text in ('old topic', 'ONE Biology lesson', 'population changes', 'personal medical advice', '3-5-image'):
            self.assertIn(text, prompt)


class BiologyGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_contract_and_image_preservation(self):
        from test_fact_evidence_lifecycle import generator_module
        generator = generator_module()
        generator.BIOLOGY_RESPONSE_SCHEMA = BIOLOGY_RESPONSE_SCHEMA
        generator.validate_biology_content = validate_biology_content
        invalid = copy.deepcopy(fixture())
        invalid['biology_lesson']['context']['organism'] = ''
        create = AsyncMock(side_effect=[types.SimpleNamespace(parsed=invalid), types.SimpleNamespace(parsed=fixture())])
        generator.genai.Client.return_value.aio.models.generate_content = create
        with patch.object(generator.asyncio, 'sleep', new=AsyncMock()):
            result = await generator.generate_daily_fact('biology')
        self.assertEqual(create.call_count, 2)
        self.assertIs(create.call_args.kwargs['config']['response_schema'], BIOLOGY_RESPONSE_SCHEMA)
        self.assertTrue(result['biology_validation']['structure_checked'])
        self.assertEqual(result['biology_validation']['scientific_review'], 'not_performed')
        self.assertEqual(expected_image_keys(result['visual_suggestions']), ['cover', 'overview', 'how_it_works'])


if __name__ == '__main__':
    unittest.main()
