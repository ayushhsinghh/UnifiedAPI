"""Offline Physics lesson/schema, dimensional, and generator regressions."""
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
from src.facts.physics import PHYSICS_RESPONSE_SCHEMA, build_physics_prompt, validate_physics_content, unit_dimensions
from src.facts.evidence import normalize_evidence
from src.facts.lifecycle import expected_image_keys
from src.facts.visual_prompts import build_section_image_context


def fixture():
    return json.loads((Path(__file__).parent / 'fixtures/physics_lesson.json').read_text())


class PhysicsContractTests(unittest.TestCase):
    def test_complete_lesson_and_legacy_contract(self):
        self.assertTrue(validate_physics_content(fixture()))
        for field in ('topic', 'headline_fact', 'summary', 'core_mechanics', 'sources', 'sources_or_references'):
            self.assertIn(field, PHYSICS_RESPONSE_SCHEMA['required'])
        for field in ('history', 'timeline', 'quote', 'cultural_significance'):
            self.assertNotIn(field, PHYSICS_RESPONSE_SCHEMA['required'])

    def test_arithmetic_dimensions_and_invalid_calculations(self):
        for key, value in [('result', 99), ('unit', 'm/s'), ('operand_ids', ['missing', 'mass']),
                           ('operation', 'eval'), ('result', float('nan'))]:
            fact = fixture()
            fact['physics_lesson']['worked_example']['calculations'][0][key] = value
            self.assertFalse(validate_physics_content(fact), (key, value))
        fact = fixture()
        fact['physics_lesson']['worked_example']['givens'][1]['value'] = 0
        self.assertFalse(validate_physics_content(fact))
        self.assertEqual(unit_dimensions('N/kg'), unit_dimensions('m/s^2'))
        with self.assertRaises(ValueError):
            unit_dimensions('__import__(os)')

    def test_qualitative_examples_are_allowed(self):
        fact = fixture()
        example = fact['physics_lesson']['worked_example']
        example['givens'], example['calculations'] = [], []
        fact['physics_lesson']['mathematics'] = []
        self.assertTrue(validate_physics_content(fact))

    def test_steps_checks_analogies_and_symbol_references_are_bounded(self):
        cases = [
            lambda l: l['explanation_steps'].pop(),
            lambda l: l['knowledge_checks'][0].update(related_step_ids=['missing']),
            lambda l: l['intuition'].update(analogy_limit=''),
            lambda l: l['mathematics'][0].update(symbol_ids=['undefined']),
            lambda l: l.update(model_limits=[]),
        ]
        for mutate in cases:
            fact = fixture()
            mutate(fact['physics_lesson'])
            self.assertFalse(validate_physics_content(fact))

    def test_supported_diagrams_and_invalid_geometry(self):
        fact = fixture()
        diagram = fact['physics_lesson']['diagram']
        for kind in ('comparison', 'energy_flow'):
            diagram['type'] = kind
            diagram['items'] = [{'label': 'A', 'detail': 'One state'}, {'label': 'B', 'detail': 'Another state'}]
            self.assertTrue(validate_physics_content(fact))
        diagram.update(type='ray', rays=[{'label': 'Incident ray', 'x1': 0, 'y1': 1, 'x2': .5, 'y2': .5}])
        self.assertTrue(validate_physics_content(fact))
        diagram['rays'][0]['x1'] = 99
        self.assertFalse(validate_physics_content(fact))
        diagram['rays'] = []
        diagram.update(type='graph', x_label='Time', x_unit='s', y_label='Distance', y_unit='m', points=[{'x':0,'y':0},{'x':1,'y':2}])
        self.assertTrue(validate_physics_content(fact))
        diagram['points'][1]['x'] = 0
        self.assertFalse(validate_physics_content(fact))
        diagram.update(type='none', points=[])
        self.assertTrue(validate_physics_content(fact))

    def test_nested_source_ids_normalize_without_verification_claim(self):
        fact = fixture()
        fact['physics_lesson']['explanation_steps'][0]['source_ids'] = ['s1', 'missing', 's1']
        normalize_evidence(fact)
        self.assertEqual(fact['physics_lesson']['explanation_steps'][0]['source_ids'], ['s1'])
        self.assertNotIn('verified', fact['sources'][0])

    def test_prompt_scope_dedup_static_diagrams_and_optional_maths(self):
        prompt = build_physics_prompt(['Already covered'])
        for text in ('Already covered', 'curious beginner', 'Math is optional', 'No HTML', 'only when useful', '3-5-image'):
            self.assertIn(text, prompt)

    def test_cover_overview_and_explanation_are_required(self):
        fact = fixture()
        self.assertEqual(expected_image_keys(fact['visual_suggestions']), ['cover', 'overview', 'how_it_works'])
        for slot in ('cover', 'overview', 'how_it_works'):
            changed = fixture()
            changed['visual_suggestions'][slot] = ''
            self.assertFalse(validate_physics_content(changed))

    def test_image_context_preserves_physics_and_cover_layout(self):
        context = build_section_image_context('cover', fixture())
        for text in ('left third quiet', 'loaded trolley', 'scientific diagrams separately'):
            self.assertIn(text, context)


class PhysicsGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_physics_selects_schema_checks_content_and_preserves_cover(self):
        from test_fact_evidence_lifecycle import generator_module
        generator = generator_module()
        generator.PHYSICS_RESPONSE_SCHEMA = PHYSICS_RESPONSE_SCHEMA
        generator.validate_physics_content = validate_physics_content
        valid = fixture()
        invalid = copy.deepcopy(valid)
        invalid['physics_lesson']['worked_example']['calculations'][0]['result'] = 999
        create = AsyncMock(side_effect=[types.SimpleNamespace(parsed=invalid), types.SimpleNamespace(parsed=valid)])
        generator.genai.Client.return_value.aio.models.generate_content = create
        with patch.object(generator.asyncio, 'sleep', new=AsyncMock()):
            result = await generator.generate_daily_fact('physics')
        self.assertEqual(create.call_count, 2)
        self.assertIs(create.call_args.kwargs['config']['response_schema'], PHYSICS_RESPONSE_SCHEMA)
        self.assertTrue(result['physics_validation']['arithmetic_checked'])
        self.assertEqual(result['physics_validation']['scientific_review'], 'not_performed')
        self.assertEqual(result['visual_suggestions'], valid['visual_suggestions'])


if __name__ == '__main__':
    unittest.main()
