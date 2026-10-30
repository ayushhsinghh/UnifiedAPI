"""All categories share a non-expert audience contract and reject advanced labels."""
import json
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch
from test_fact_evidence_lifecycle import generator_module, learning, load, module
from image_fixtures import add_image_plan


class AudienceTests(unittest.TestCase):
    def test_only_beginner_and_intermediate_labels_are_accepted(self):
        for value in ('Beginner', ' intermediate ', 'INTERMEDIATE'):
            fact = {'difficulty_level': value}
            self.assertTrue(learning.normalize_learning_level(fact))
            self.assertIn(fact['difficulty_level'], ('beginner', 'intermediate'))
        for value in ('advanced', 'expert', '', None, 1):
            self.assertFalse(learning.normalize_learning_level({'difficulty_level': value}))

    def test_schemas_do_not_offer_advanced_topics(self):
        schemas = load('learning_schemas', 'src/facts/schemas.py')
        for name in ('FACT_RESPONSE_SCHEMA', 'MYTHBUSTER_RESPONSE_SCHEMA', 'FITNESS_RESPONSE_SCHEMA', 'INDIAN_DIET_RESPONSE_SCHEMA'):
            levels = getattr(schemas, name)['properties']['difficulty_level']['enum']
            self.assertEqual({value.lower() for value in levels}, {'beginner', 'intermediate'})

    def test_emergency_cache_cannot_select_advanced_or_unlabelled_articles(self):
        collection = Mock()
        collection.aggregate.return_value = []
        repository = load('learning_repository', 'src/database/facts_repository.py', {
            'configs.config': module('configs.config', get_config=lambda: types.SimpleNamespace(DAILY_FACTS_COLLECTION='facts')),
            'pymongo.errors': module('pymongo.errors', DuplicateKeyError=type('DuplicateKeyError', (Exception,), {})),
            'src.database.connection': module('src.database.connection', get_db=lambda: {'facts': collection}),
        })
        self.assertIsNone(repository.get_random_cached_fact('physics'))
        match = collection.aggregate.call_args.args[0][0]['$match']
        self.assertEqual(match['category'], 'physics')
        allowed = match['full_response.difficulty_level']['$in']
        self.assertEqual({level.lower() for level in allowed}, {'beginner', 'intermediate'})


class AudienceGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_category_branch_receives_the_same_audience_rules(self):
        for category in ('space', 'physics', 'biology', 'psychology', 'indian_constitution', 'mythbusters', 'fitness', 'indian_diet'):
            generator = generator_module()
            fact = {'headline_fact': 'One useful idea', 'difficulty_level': 'Intermediate',
                    'physics_lesson': {'worked_example': {'calculations': []}},
                    'visual_suggestions': {'cover': 'A relevant illustration'}}
            add_image_plan(fact, myth=category == 'mythbusters')
            create = AsyncMock(return_value=types.SimpleNamespace(parsed=fact))
            generator.genai.Client.return_value.aio.models.generate_content = create
            result = await generator.generate_daily_fact(category)
            self.assertIsNotNone(result, (category, generator.logger.exception.call_args_list))
            self.assertEqual(result['difficulty_level'], 'intermediate')
            self.assertEqual(create.call_args.kwargs['contents'].count(learning.LEARNER_INSTRUCTIONS), 1)

    async def test_advanced_response_retries_and_openai_keeps_the_audience_rules(self):
        generator = generator_module()
        responses = [types.SimpleNamespace(parsed=add_image_plan({'headline_fact': 'Too technical', 'difficulty_level': 'advanced'})),
                     types.SimpleNamespace(parsed=add_image_plan({'headline_fact': 'Accessible', 'difficulty_level': 'beginner'}))]
        create = AsyncMock(side_effect=responses)
        generator.genai.Client.return_value.aio.models.generate_content = create
        with patch.object(generator.asyncio, 'sleep', new=AsyncMock()):
            result = await generator.generate_daily_fact('space')
        self.assertEqual(create.call_count, 2)
        self.assertEqual(result['headline_fact'], 'Accessible')

        generator = generator_module()
        generator.cfg = types.SimpleNamespace(GEMINI_MODEL_NAME='openai-primary', OPENAI_MODEL_NAME='fallback', OPENAI_API_KEY='unused')
        response = json.dumps(add_image_plan({'headline_fact': 'Accessible', 'difficulty_level': 'beginner'}))
        create = AsyncMock(return_value=types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=response))]))
        generator.openai.AsyncOpenAI.return_value.chat.completions.create = create
        await generator.generate_daily_fact('space')
        self.assertIn(learning.LEARNER_INSTRUCTIONS, create.call_args.kwargs['messages'][0]['content'])


if __name__ == '__main__':
    unittest.main()
