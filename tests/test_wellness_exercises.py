"""Offline contract and HTTP regressions for wellness and MuscleWiki integration.

Run with: python -m unittest discover -s tests
Dependencies: fastapi, httpx, slowapi. No provider key, MongoDB or LLM required.
"""
import copy
import importlib
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
            self.assertIn('without assuming', CATEGORY_HINTS['nutrition_myths'])
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


try:
    import httpx
    from fastapi import FastAPI
    from src.facts import exercises
    from src.routes import exercise_routes
except ImportError:
    httpx = None


@unittest.skipUnless(httpx, 'Install fastapi, httpx and slowapi for HTTP integration tests')
class ExerciseRoutesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        exercises._CACHE.clear()
        self.app = FastAPI()
        self.app.include_router(exercise_routes.router)
        from commons import limiter
        limiter.enabled = False
        self.app.state.limiter = limiter
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')
        self.key_patch = patch.object(exercises, 'get_config', return_value=types.SimpleNamespace(MUSCLEWIKI_API_KEY='test-secret'))
        self.key_patch.start()
        self.client_class = httpx.AsyncClient
        self.calls = []
        self.item = {'id': 1, 'name': 'Squat', 'primary_muscles': ['Quads'], 'category': 'Bodyweight',
                     'difficulty': 'Beginner', 'steps': ['Stand.'],
                     'videos': [{'angle': 'front', 'gender': 'male', 'url': 'https://api.musclewiki.com/stream/videos/branded/squat.mp4'},
                                {'url': 'https://attacker.example/video.mp4'}, {'url': None}]}

    async def asyncTearDown(self):
        self.key_patch.stop()
        await self.client.aclose()
        from commons import limiter
        limiter.enabled = True

    def provider(self, handler):
        return patch.object(httpx, 'AsyncClient', side_effect=lambda *a, **kw: self.client_class(*a, transport=httpx.MockTransport(handler), **kw))

    async def test_search_normalizes_and_caches_without_exposing_credentials(self):
        def handler(request):
            self.calls.append(request)
            self.assertEqual(request.headers['X-API-Key'], 'test-secret')
            self.assertEqual(request.url.params['q'], 'squat')
            return httpx.Response(200, json=[self.item])
        with self.provider(handler):
            first = await self.client.get('/api/exercises?q=squat')
            second = await self.client.get('/api/exercises?q=squat')
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(len(self.calls), 1)
        video = first.json()['results'][0]['videos']
        self.assertEqual(len(video), 1)
        self.assertEqual(video[0]['path'], '/api/exercises/1/videos/0')
        self.assertNotIn('test-secret', first.text)
        self.assertNotIn('attacker', first.text)

    async def test_provider_failures_and_missing_key_are_readable(self):
        for status, expected in [(401, 503), (403, 503), (429, 429), (500, 502), (404, 404), (302, 502)]:
            exercises._CACHE.clear()
            with self.provider(lambda request: httpx.Response(status, json={'detail': 'private provider detail'})):
                response = await self.client.get('/api/exercises?q=squat')
            self.assertEqual(response.status_code, expected)
            self.assertNotIn('private provider detail', response.text)
        with patch.object(exercises, 'get_config', return_value=types.SimpleNamespace(MUSCLEWIKI_API_KEY='')):
            response = await self.client.get('/api/exercises?q=squat')
        self.assertEqual(response.status_code, 503)

    async def test_invalid_queries_ids_and_video_urls(self):
        for url in ['/api/exercises?q=a', '/api/exercises?q=%20%20', '/api/exercises/-1', '/api/exercises/1/videos/-1']:
            response = await self.client.get(url)
            self.assertEqual(response.status_code, 422)
        for url in ['https://api.musclewiki.com/stream/videos/branded/../secret.mp4', '//evil.example/a.mp4',
                    'https://[', 'https://api.musclewiki.com/stream/videos/branded/a.mp4?token=secret',
                    'http://api.musclewiki.com/stream/videos/branded/a.mp4']:
            self.assertIsNone(exercises.video_path(url))
        with self.provider(lambda request: httpx.Response(200, json=self.item)):
            response = await self.client.get('/api/exercises/1/videos/1')
        self.assertEqual(response.status_code, 404)

    async def test_video_stream_preserves_range_and_no_store(self):
        class Bytes(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'test'
        def handler(request):
            if request.url.path.startswith('/exercises/'):
                return httpx.Response(200, json=self.item)
            self.assertEqual(request.headers['Range'], 'bytes=0-3')
            self.assertEqual(request.headers['X-API-Key'], 'test-secret')
            return httpx.Response(206, stream=Bytes(), headers={'Content-Type': 'video/mp4',
                'Content-Range': 'bytes 0-3/4', 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store', 'Content-Length': '4'})
        with self.provider(handler):
            response = await self.client.get('/api/exercises/1/videos/0', headers={'Range': 'bytes=0-3'})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, b'test')
        self.assertEqual(response.headers['content-range'], 'bytes 0-3/4')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertNotIn('x-api-key', response.headers)

    async def test_timeout_is_sanitized(self):
        def handler(request):
            raise httpx.ReadTimeout('secret provider data')
        with self.provider(handler):
            response = await self.client.get('/api/exercises?q=squat')
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('secret', response.text)


if __name__ == '__main__':
    unittest.main()
