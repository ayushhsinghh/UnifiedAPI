"""Offline Psychology learning, evidence, image-budget and generation contracts."""
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
from src.facts.psychology import PSYCHOLOGY_RESPONSE_SCHEMA, LESSON_TYPES, DIAGRAM_TYPES, build_psychology_prompt, validate_psychology_content
from src.facts.evidence import normalize_evidence
from src.facts.lifecycle import expected_image_keys
from src.facts.visual_prompts import build_section_image_context


def fixture():
    return json.loads((Path(__file__).parent / 'fixtures/psychology_lesson.json').read_text())


class PsychologyContractTests(unittest.TestCase):
    def test_formats_and_legacy_contract(self):
        fact = fixture()
        self.assertTrue(validate_psychology_content(fact))
        for lesson_type, diagram_type in zip(LESSON_TYPES, DIAGRAM_TYPES):
            fact['psychology_lesson']['lesson_type'] = lesson_type
            fact['psychology_lesson']['diagram']['type'] = diagram_type
            self.assertTrue(validate_psychology_content(fact))
        self.assertIn('summary', PSYCHOLOGY_RESPONSE_SCHEMA['required'])
        self.assertNotIn('timeline', PSYCHOLOGY_RESPONSE_SCHEMA['required'])

    def test_unknown_values_stay_null_and_bad_numbers_fail(self):
        fact = fixture()
        item = fact['psychology_lesson']['evidence'][0]
        item['study_notes'].update(year=None, sample_size=None)
        item['statistics'][0]['value'] = None
        fact['psychology_lesson']['opening_scenario']['prediction'] = None
        self.assertTrue(validate_psychology_content(fact))
        for value in (0, -1, 2.5, 'unknown', float('inf')):
            item['study_notes']['sample_size'] = value
            self.assertFalse(validate_psychology_content(fact), value)

    def test_evidence_and_causation_are_constrained(self):
        mutations = [
            lambda l: l['evidence'][0].update(source_ids=['missing']),
            lambda l: l['evidence'][0].update(research_design='observational', inference='causal', causal_justification='An association exists.'),
            lambda l: l['evidence'][0].update(inference='causal', causal_justification=''),
            lambda l: l['replication'].update(status='consistent', source_ids=[]),
            lambda l: l['evidence'][0]['statistics'][0].update(source_ids=[]),
            lambda l: l['boundary_conditions'].update(populations=[]),
            lambda l: l['diagram']['edges'][0].update(relationship_type='causal'),
            lambda l: l['diagram']['edges'][0].update(to_id='missing'),
            lambda l: l['knowledge_checks'][0].update(related_step_ids=['missing']),
            lambda l: l['explanation_steps'].pop(),
        ]
        for mutate in mutations:
            fact = fixture()
            mutate(fact['psychology_lesson'])
            self.assertFalse(validate_psychology_content(fact))
        fact = fixture()
        fact['psychology_lesson']['diagram'].update(type='none', nodes=[], edges=[])
        self.assertTrue(validate_psychology_content(fact))

    def test_sources_images_and_prompt_boundaries(self):
        fact = fixture()
        fact['psychology_lesson']['big_idea']['source_ids'] = ['s1', 'missing', 's1']
        normalize_evidence(fact)
        self.assertEqual(fact['psychology_lesson']['big_idea']['source_ids'], ['s1'])
        self.assertEqual(expected_image_keys(fact['visual_suggestions']), ['cover', 'overview', 'how_it_works'])
        fact['visual_suggestions']['how_it_works'] = ''
        self.assertFalse(validate_psychology_content(fact))
        self.assertIn('not research evidence', build_section_image_context('cover', fixture()))
        prompt = build_psychology_prompt(['prior topic'])
        for text in ('prior topic', 'experience-first', 'not_assessed', 'Use null', 'never a diagnostic', '3-5-image'):
            self.assertIn(text, prompt)


class PsychologyGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_schema_retry_and_preserved_image_policy(self):
        from test_fact_evidence_lifecycle import generator_module
        generator = generator_module()
        generator.PSYCHOLOGY_RESPONSE_SCHEMA = PSYCHOLOGY_RESPONSE_SCHEMA
        generator.validate_psychology_content = validate_psychology_content
        invalid = copy.deepcopy(fixture())
        invalid['psychology_lesson']['evidence'][0]['source_ids'] = []
        create = AsyncMock(side_effect=[types.SimpleNamespace(parsed=invalid), types.SimpleNamespace(parsed=fixture())])
        generator.genai.Client.return_value.aio.models.generate_content = create
        with patch.object(generator.asyncio, 'sleep', new=AsyncMock()):
            result = await generator.generate_daily_fact('psychology')
        self.assertEqual(create.call_count, 2)
        self.assertIs(create.call_args.kwargs['config']['response_schema'], PSYCHOLOGY_RESPONSE_SCHEMA)
        self.assertEqual(result['psychology_validation']['scientific_review'], 'not_performed')
        self.assertEqual(expected_image_keys(result['visual_suggestions']), ['cover', 'overview', 'how_it_works'])


if __name__ == '__main__':
    unittest.main()
