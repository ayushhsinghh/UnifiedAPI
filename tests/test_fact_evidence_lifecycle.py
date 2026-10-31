"""Offline regression tests. Provider SDKs and MongoDB are replaced at import time."""
import asyncio
import importlib.util
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

APP = Path(__file__).resolve().parents[1] / 'app'
CFG = types.SimpleNamespace(FACT_REQUEST_TIMEOUT_SECONDS=0.01, FACT_JOB_TIMEOUT_SECONDS=270,
    FACT_IMAGE_TIMEOUT_SECONDS=330, FACT_JOBS_COLLECTION='jobs', DAILY_FACTS_COLLECTION='facts',
    GEMINI_MODEL_NAME='gemini-primary', OPENAI_MODEL_NAME='openai-fallback',
    GEMINI_API_KEY='unused', OPENAI_API_KEY='unused')


def module(name, **values):
    value = types.ModuleType(name)
    value.__dict__.update(values)
    return value


def load(name, path, imports=None):
    spec = importlib.util.spec_from_file_location(name, APP / path)
    value = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, imports or {}):
        spec.loader.exec_module(value)
    return value


evidence = load('evidence_test', 'src/facts/evidence.py')
lifecycle = load('lifecycle_test', 'src/facts/lifecycle.py')
visual_prompts = load('visual_prompts_test', 'src/facts/visual_prompts.py')
learning = load('learning_test', 'src/facts/learning.py')
image_policy = load('image_policy_test', 'src/facts/image_policy.py')
config_import = {'configs.config': module('configs.config', get_config=lambda: CFG)}


def generator_module():
    from src.facts import india as india_contract
    from src.facts import image_policy as image_policy_contract
    value = load('fact_test.generator', 'src/facts/fact_generator.py', {
        **config_import,
        'openai': module('openai', AsyncOpenAI=Mock()),
        'google': module('google', genai=types.SimpleNamespace(Client=Mock())),
        'fact_test': module('fact_test', __path__=[]),
        'fact_test.constants': module('fact_test.constants', CATEGORY_HINTS={}, SUPPORTED_CATEGORIES=[], CLICHED_FACTS=[]),
        'fact_test.schemas': module('fact_test.schemas', FACT_RESPONSE_SCHEMA={}, MYTHBUSTER_RESPONSE_SCHEMA={}, FITNESS_RESPONSE_SCHEMA={}, INDIAN_DIET_RESPONSE_SCHEMA={}, validate_wellness_content=lambda *args: True),
        'fact_test.evidence': evidence,
        'fact_test.prompts': module('fact_test.prompts', _build_prompt=lambda *args: 'prompt', _build_mythbuster_prompt=lambda *args: 'prompt', _build_wellness_prompt=lambda *args: 'prompt'),
        'fact_test.physics': module('fact_test.physics', PHYSICS_RESPONSE_SCHEMA={}, build_physics_prompt=lambda *args: 'physics prompt', validate_physics_content=lambda *args: True),
        'fact_test.biology': module('fact_test.biology', BIOLOGY_RESPONSE_SCHEMA={}, build_biology_prompt=lambda *args: 'biology prompt', validate_biology_content=lambda *args: True),
        'fact_test.psychology': module('fact_test.psychology', PSYCHOLOGY_RESPONSE_SCHEMA={}, build_psychology_prompt=lambda *args: 'psychology prompt', validate_psychology_content=lambda *args: True),
        'fact_test.learning': learning,
        'fact_test.image_policy': image_policy_contract,
        'fact_test.constitution': module('fact_test.constitution', CONSTITUTION_RESPONSE_SCHEMA={}, build_constitution_prompt=lambda *args: 'constitution prompt', validate_constitution_content=lambda *args: True),
        'fact_test.constitution_sources': module('fact_test.constitution_sources', enrich_constitution_text=AsyncMock(side_effect=lambda fact: fact)),
        'fact_test.indian_laws': module('fact_test.indian_laws', INDIAN_LAWS_RESPONSE_SCHEMA={}, build_indian_laws_prompt=lambda *args: 'Indian laws prompt', validate_indian_laws_content=lambda *args: True),
        'fact_test.country': module('fact_test.country', COUNTRY_RESPONSE_SCHEMA={}, COUNTRY_IMAGE_INSTRUCTIONS='Country image rules', build_country_prompt=lambda *args: 'Country prompt', validate_country_content=lambda *args: True, enrich_country_identity=lambda fact:fact),
        'fact_test.india': india_contract,
        'fact_test.food': __import__('src.facts.food',fromlist=['food']),
    })

    value.logger = Mock()
    return value


def routes_module():
    photo_plan = load('photo_plan_test', 'src/facts/country_photos.py', {})
    class Router:
        def __init__(self, **kwargs): pass
        def get(self, *args, **kwargs): return lambda fn: fn
        post = delete = get
    class HTTPException(Exception):
        def __init__(self, status_code, detail): self.status_code, self.detail = status_code, detail
    repo_names = ['get_facts_list', 'get_random_cached_fact', 'get_recent_topic_keys', 'store_fact',
        'update_fact_images', 'delete_fact', 'get_fact_by_hash', '_compute_content_hash',
        'start_fact_images', 'set_fact_image_state', 'finish_fact_images', 'claim_country_photo_enrichment', 'finish_country_photo_enrichment','set_fact_photo_selection']
    value = load('routes_test', 'src/routes/facts_routes.py', {
        **config_import,
        'fastapi': module('fastapi', APIRouter=Router, BackgroundTasks=object, Header=lambda *a, **k: None,
            HTTPException=HTTPException, Query=lambda *a, **k: None, Request=object, Depends=lambda *a: None),
        'fastapi.responses': module('fastapi.responses', JSONResponse=object),
        'commons': module('commons', limiter=types.SimpleNamespace(limit=lambda *a: lambda fn: fn)),
        'security': module('security', safe_error_response=Mock(), validate_category=lambda x: x, require_facts_api_key=Mock()),
        'src.database.fact_jobs_repository': module('src.database.fact_jobs_repository', **{n: Mock(return_value=True) for n in ['create_fact_job','get_fact_job','update_fact_job']}),
        'src.database.facts_repository': module('src.database.facts_repository', **{n: Mock() for n in repo_names}),
        'src.facts.fact_generator': module('src.facts.fact_generator', SUPPORTED_CATEGORIES=[], generate_daily_fact=AsyncMock()),
        'src.facts.lifecycle': lifecycle,
        'src.facts.visual_prompts': visual_prompts,
        'src.facts.country_photos': module('src.facts.country_photos', find_country_photos=AsyncMock(return_value=[]),
            find_subject_photo=AsyncMock(return_value=[]), country_scene_queries=photo_plan.country_scene_queries,
            country_scene_plan=photo_plan.country_scene_plan),
        'src.facts.image_generator': module('src.facts.image_generator', generate_and_save_image=AsyncMock()),
        'src.facts.photo_ranking': module('src.facts.photo_ranking',select_india_photos=AsyncMock(side_effect=RuntimeError('Offline ranking fixture')),
            select_country_photos=AsyncMock(side_effect=RuntimeError('Offline ranking fixture')),
            select_food_photos=AsyncMock(return_value=[]),PhotoRankingUnavailable=RuntimeError),
    })
    value.logger = Mock()
    return value


class EvidenceTests(unittest.TestCase):
    def test_links_and_ids_are_normalized_without_rewriting_legacy_text(self):
        fact = {'sources_or_references': ['A book'], 'sources': [
            {'id':'s1','title':'Source','url':'https://example.org/paper'},
            {'id':'s1','title':'Duplicate','url':'https://wrong.example'},
            {'id':'s2','title':'Unsafe','url':'javascript:alert(1)'}],
            'claim_citations':[{'claim':'A claim','source_ids':['s1','missing','s1']}, {'claim':'No source','source_ids':['missing']}],
            'quote': {'source_ids':['missing','s2']}}
        evidence.normalize_evidence(fact)
        self.assertEqual(fact['sources_or_references'], ['A book'])
        self.assertEqual(len(fact['sources']), 2)
        self.assertEqual(fact['sources'][1]['url'], '')
        self.assertEqual(fact['claim_citations'], [{'claim':'A claim','source_ids':['s1']}])
        self.assertEqual(fact['quote']['source_ids'], ['s2'])

    def test_url_credentials_controls_and_invalid_hosts_are_rejected(self):
        for url in ['//example.org', 'https://user:pass@example.org', 'https://[', 'https://example.org/\nx', 'https://example.org:bad', None]:
            self.assertEqual(evidence.safe_source_url(url), '')


class LifecycleTests(unittest.TestCase):
    def test_partial_images_keep_polling_until_remaining_work_ends(self):
        doc = {'full_response': {'visual_suggestions': {'cover':'a','overview':'b'}},
            'images':{'cover':'https://example.org/cover'}, 'image_status':{'overview':'processing'},
            'image_started_at': datetime.now(timezone.utc)}
        self.assertEqual(lifecycle.image_generation_state(doc, 330)['status'], 'processing')
        doc['image_status']['overview'] = 'failed'
        self.assertEqual(lifecycle.image_generation_state(doc, 330)['status'], 'partial')
        doc['images']['overview'] = 'https://example.org/overview'
        self.assertEqual(lifecycle.image_generation_state(doc, 330)['status'], 'completed')

    def test_interrupted_image_jobs_and_legacy_history_prompt_are_terminal(self):
        doc = {'full_response': {'visual_suggestions': {'history':'a'}}, 'image_status':{'overview':'processing'},
            'image_started_at':datetime.now(timezone.utc)-timedelta(seconds=331)}
        state = lifecycle.image_generation_state(doc, 330)
        self.assertEqual(state['status'], 'failed')
        self.assertEqual(state['expected'], ['overview'])
        self.assertEqual(lifecycle.image_generation_state({'full_response':{}}, 330)['status'], 'not_requested')


class GenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_timeout_falls_through_and_reports_actual_openai_model(self):
        gen = generator_module()
        async def hang(**kwargs): await asyncio.Event().wait()
        gen.genai.Client.return_value = types.SimpleNamespace(aio=types.SimpleNamespace(models=types.SimpleNamespace(generate_content=hang)))
        from image_fixtures import add_image_plan
        import json
        create = AsyncMock(return_value=types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps(add_image_plan({'headline_fact':'Headline','difficulty_level':'beginner'}))))]))
        gen.openai.AsyncOpenAI.return_value = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
        gen._BACKOFF_SECONDS = [0,0,0]
        metadata = {}
        fact = await asyncio.wait_for(gen.generate_daily_fact('space', generation_metadata=metadata), 1)
        self.assertEqual(fact['category'], 'space')
        self.assertEqual(metadata, {'provider':'openai','model':'openai-fallback'})
        self.assertEqual(create.await_count, 1)

    async def test_cache_metadata_and_existing_images_are_preserved_without_restoring(self):
        routes = routes_module()
        routes.generate_daily_fact.return_value = None
        routes.get_random_cached_fact.return_value = {
            'full_response':{'headline_fact':'Cached'},'content_hash':'hash',
            'images':{'cover':'https://example.org/cover'},'generation_metadata':{'provider':'openai','model':'old-model'}}
        await routes.process_fact_generation_task('job','space',[])
        payload = routes.update_fact_job.call_args.kwargs['fact_data']
        self.assertEqual(payload['meta']['source'], 'cache')
        self.assertEqual(payload['meta']['provider'], 'openai')
        self.assertEqual(payload['meta']['model'], 'old-model')
        self.assertTrue(payload['meta']['cached'])
        self.assertEqual(payload['fact']['images']['cover'], 'https://example.org/cover')
        routes.store_fact.assert_not_called()

    async def test_fresh_provider_metadata_is_stored_and_reported(self):
        routes = routes_module()
        async def generate(category, blocklist, generation_metadata):
            generation_metadata.update(provider='openai', model='actual-model')
            return {'headline_fact':'A new fact'}
        routes.generate_daily_fact.side_effect = generate
        routes.store_fact.return_value = 'hash'
        routes.get_fact_by_hash.return_value = {'full_response':{'headline_fact':'A new fact'}}
        await routes.process_fact_generation_task('job','space',[])
        payload = routes.update_fact_job.call_args.kwargs['fact_data']
        self.assertEqual(payload['meta']['source'], 'openai')
        self.assertFalse(payload['meta']['cached'])
        self.assertEqual(routes.store_fact.call_args.kwargs['generation_metadata'],
            {'provider':'openai','model':'actual-model'})

    async def test_overall_generation_deadline_uses_cache_fallback(self):
        routes = routes_module()
        async def hang(*args, **kwargs): await asyncio.Event().wait()
        routes.generate_daily_fact.side_effect = hang
        routes.get_random_cached_fact.return_value = None
        with patch.object(CFG, 'FACT_JOB_TIMEOUT_SECONDS', 5.01):
            await asyncio.wait_for(routes.process_fact_generation_task('job','space',[]), 1)
        self.assertEqual(routes.update_fact_job.call_args.args, ('job','failed'))

    async def test_status_refreshes_partial_images_on_every_poll(self):
        routes = routes_module()
        payload = {'fact':{'images':{'cover':'old'}},'content_hash':'hash'}
        routes.get_fact_job.return_value = {'status':'completed','fact_data':payload}
        routes.get_fact_by_hash.return_value = {'full_response':{'visual_suggestions':{'cover':'x','overview':'y'}},'images':{'cover':'new','overview':'new2'}}
        result = await routes.get_fact_job_status('job')
        self.assertEqual(result['data']['fact']['images'], {'cover':'new','overview':'new2'})
        self.assertEqual(result['data']['image_generation']['status'], 'completed')

    async def test_image_worker_passes_section_content_and_preserves_legacy_history(self):
        routes = routes_module()
        routes.generate_and_save_image.return_value = 'https://example.org/image'
        article = {'topic': 'A water wheel', 'summary': 'A wheel uses flowing water.',
            'core_mechanics': 'Flow turns the paddles.', 'visual_suggestions': {'history':'A water wheel scene'}}
        await routes._background_image_task(article['visual_suggestions'], 'hash', article=article)
        call = routes.generate_and_save_image.call_args
        self.assertEqual(call.args[:2], ('A water wheel scene', 'hash_overview.jpg'))
        self.assertEqual(call.kwargs['aspect_ratio'], '4:3')
        self.assertIn('A wheel uses flowing water.', call.kwargs['extra_context'])
        self.assertNotIn('Flow turns the paddles.', call.kwargs['extra_context'])

    async def test_image_retry_receives_the_stored_article(self):
        routes = routes_module()
        article = {'topic':'A water wheel', 'visual_suggestions':{'cover':'A wheel'}}
        routes.get_fact_by_hash.return_value = {'full_response':article, 'images':{}}
        background = Mock()
        await routes.retry_image_generation(Mock(), background, 'hash')
        self.assertIs(background.add_task.call_args.kwargs['article'], article)

    async def test_image_failures_do_not_hide_successful_images(self):
        routes = routes_module()
        async def image(prompt, *args, **kwargs):
            if prompt == 'fail': raise RuntimeError('Provider failed')
            return 'https://example.org/cover'
        routes.generate_and_save_image.side_effect = image
        await routes._background_image_task({'cover':'good','overview':'fail'}, 'hash')
        calls = [call.args for call in routes.set_fact_image_state.call_args_list]
        self.assertIn(('hash','cover','ready','https://example.org/cover'), calls)
        self.assertIn(('hash','overview','failed'), calls)


class JobTests(unittest.TestCase):
    def test_stale_job_expires_and_late_worker_cannot_overwrite_it(self):
        collection = Mock()
        stale = {'job_id':'job','status':'processing','created_at':datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(seconds=300)}
        collection.find_one.side_effect = [stale, {**stale,'status':'failed'}]
        db = {'jobs':collection}
        repo = load('jobs_test','src/database/fact_jobs_repository.py', {
            **config_import,'src.database.connection':module('src.database.connection',get_db=lambda:db)})
        repo.logger = Mock()
        self.assertEqual(repo.get_fact_job('job')['status'], 'failed')
        self.assertEqual(collection.update_one.call_args.args[0], {'job_id':'job','status':'processing'})
        collection.update_one.return_value.modified_count = 0
        self.assertFalse(repo.update_fact_job('job','completed',fact_data={}))
        self.assertEqual(collection.update_one.call_args.args[0], {'job_id':'job','status':'processing'})


if __name__ == '__main__': unittest.main()
