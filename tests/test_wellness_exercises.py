"""Offline contract regressions for wellness and written exercise guides.

Run with: python -m unittest discover -s tests
No exercise provider key, MongoDB or live LLM required.
"""
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

# Avoid the facts package's eager LLM SDK import in these offline tests.
package = types.ModuleType('src.facts')
package.__path__ = [str(Path(__file__).resolve().parents[1] / 'app/src/facts')]
sys.modules.setdefault('src.facts', package)
from src.facts import prompts
from src.facts.schemas import FITNESS_RESPONSE_SCHEMA, INDIAN_DIET_RESPONSE_SCHEMA, validate_wellness_content
from src.facts.constants import CATEGORY_HINTS
from src.facts.evidence import normalize_evidence


def example(schema):
    if schema.get('nullable'):
        return None
    if schema['type'] == 'OBJECT':
        return {key: example(value) for key, value in schema['properties'].items() if key in schema['required']}
    if schema['type'] == 'ARRAY':
        return []
    if schema['type'] == 'NUMBER':
        return 1
    return schema.get('enum', ['example'])[0]


class ContractTests(unittest.TestCase):
    def test_categories_and_practical_contracts(self):
        self.assertTrue({'fitness', 'indian_diet', 'nutrition_myths', 'home_workouts'} <= CATEGORY_HINTS.keys())
        for category, schema in [('fitness', FITNESS_RESPONSE_SCHEMA), ('home_workouts', FITNESS_RESPONSE_SCHEMA), ('indian_diet', INDIAN_DIET_RESPONSE_SCHEMA)]:
            self.assertTrue(validate_wellness_content(example(schema), category))
            self.assertFalse(validate_wellness_content({'headline_fact': 'No guide'}, category))
        self.assertNotIn('history', FITNESS_RESPONSE_SCHEMA['required'])

    def test_written_exercises_do_not_require_a_catalog_search(self):
        schema = FITNESS_RESPONSE_SCHEMA['properties']['training_guide']['properties']['exercises']['items']
        self.assertNotIn('search_query', schema['properties'])
        self.assertEqual(set(schema['required']), {
            'name', 'sets', 'reps', 'rest_seconds', 'steps',
            'easier_option', 'progression', 'source_ids',
        })
        fact = example(FITNESS_RESPONSE_SCHEMA)
        exercise = example(schema)
        fact['training_guide']['exercises'] = [exercise]
        self.assertTrue(validate_wellness_content(fact, 'fitness'))
        # Existing archived guides may retain the unused legacy field.
        exercise['search_query'] = 'legacy query'
        self.assertTrue(validate_wellness_content(fact, 'home_workouts'))
        from src.facts import prompts
        prompt = prompts._build_wellness_prompt('fitness', [])
        self.assertIn('self-contained written instructions', prompt)

    def test_unknown_nutrients_stay_null_but_negative_and_string_values_fail(self):
        fact = example(INDIAN_DIET_RESPONSE_SCHEMA)
        food = example(INDIAN_DIET_RESPONSE_SCHEMA['properties']['nutrition_guide']['properties']['food_items']['items'])
        fact['nutrition_guide']['food_items'] = [food]
        self.assertTrue(validate_wellness_content(fact, 'indian_diet'))
        for value in [-1, '20g', float('nan'), True]:
            food['protein_g'] = value
            self.assertFalse(validate_wellness_content(fact, 'indian_diet'))
        food['protein_g'] = 0
        self.assertTrue(validate_wellness_content(fact, 'indian_diet'))

    def test_practical_fields_keep_only_known_source_ids(self):
        fact = {'sources': [{'id': 's1', 'title': 'Source', 'url': 'https://example.org'}],
                'training_guide': {'exercises': [{'source_ids': ['s1', 'missing']}]},
                'nutrition_guide': {'food_items': [{'source_ids': ['s1', 'missing']}]}}
        normalize_evidence(fact)
        self.assertEqual(fact['training_guide']['exercises'][0]['source_ids'], ['s1'])
        self.assertEqual(fact['nutrition_guide']['food_items'][0]['source_ids'], ['s1'])

    def test_prompts_preserve_dedup_and_require_portion_and_evidence_context(self):
        from src.facts import prompts
        with patch.object(prompts, 'cfg', types.SimpleNamespace(FACTS_DEDUP_LIMIT=20)):
            diet = prompts._build_wellness_prompt('indian_diet', ['Already covered topic'])
            self.assertIn('Already covered topic', diet)
            self.assertIn('cooked/raw', diet)
            self.assertIn('Use null for unknown', diet)
            myth = prompts._build_wellness_prompt('nutrition_myths', [])
            self.assertIn('Do not assume all food claims are false.', ' '.join(myth.split()))
            self.assertIn('CATEGORY: nutrition_myths', myth)


class WellnessGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_category_selects_the_matching_schema(self):
        from test_fact_evidence_lifecycle import generator_module
        from src.facts.schemas import MYTHBUSTER_RESPONSE_SCHEMA
        for category, schema in [('fitness', FITNESS_RESPONSE_SCHEMA), ('home_workouts', FITNESS_RESPONSE_SCHEMA),
                                 ('indian_diet', INDIAN_DIET_RESPONSE_SCHEMA), ('nutrition_myths', MYTHBUSTER_RESPONSE_SCHEMA)]:
            generator = generator_module()
            generator.FITNESS_RESPONSE_SCHEMA = FITNESS_RESPONSE_SCHEMA
            generator.INDIAN_DIET_RESPONSE_SCHEMA = INDIAN_DIET_RESPONSE_SCHEMA
            generator.MYTHBUSTER_RESPONSE_SCHEMA = MYTHBUSTER_RESPONSE_SCHEMA
            generator.validate_wellness_content = validate_wellness_content
            response = example(schema)
            response['headline_fact'] = 'A structured guide'
            create = AsyncMock(return_value=types.SimpleNamespace(parsed=response))
            generator.genai.Client.return_value.aio.models.generate_content = create
            result = await generator.generate_daily_fact(category)
            self.assertEqual(result['category'], category)
            self.assertIs(create.call_args.kwargs['config']['response_schema'], schema)

    async def test_missing_practical_fields_trigger_provider_retry(self):
        from test_fact_evidence_lifecycle import generator_module
        generator = generator_module()
        generator.validate_wellness_content = validate_wellness_content
        invalid = {'headline_fact': 'An incomplete workout'}
        valid = example(FITNESS_RESPONSE_SCHEMA)
        valid['headline_fact'] = 'A complete workout'
        create = AsyncMock(side_effect=[types.SimpleNamespace(parsed=invalid), types.SimpleNamespace(parsed=valid)])
        generator.genai.Client.return_value.aio.models.generate_content = create
        with patch.object(generator.asyncio, 'sleep', new=AsyncMock()):
            result = await generator.generate_daily_fact('fitness')
        self.assertIn('training_guide', result)
        self.assertEqual(create.call_count, 2)


if __name__ == '__main__':
    unittest.main()
