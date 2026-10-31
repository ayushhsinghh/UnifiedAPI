"""Metadata-only ranking, bounded retry policy and asynchronous article delivery."""
import asyncio
import json
import sys
import types
import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import AsyncMock,Mock,patch
from test_india import fixture
from test_fact_evidence_lifecycle import routes_module
from src.facts.india import prepare_india_media
from src.facts.photo_ranking import rank_photos,validate_ranking,select_india_photos,PhotoRankingUnavailable
from src.facts.lifecycle import image_generation_state,fact_image_keys
from test_country import fixture as country_fixture
from src.facts.country import enrich_country_identity
from src.facts.photo_ranking import ranking_input,country_ranking_queries,select_country_photos

def photo(index):
    return dict(provider='unsplash',provider_id=f'p{index}',url=f'https://images.unsplash.com/p{index}',
        source_url=f'https://unsplash.com/photos/p{index}',author_url='https://unsplash.com/@author',
        license='Unsplash License',license_url='https://unsplash.com/license',author='Photographer',
        title='A root bridge',description='A living root bridge in Meghalaya',alt_description='People crossing a root bridge',
        search_query='Meghalaya root bridge')

def response(photos):
    selected=[dict(photo_id=p['provider_id'],score=90,scene='Root bridge',reason='The metadata identifies a bridge.') for p in photos]
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps({'selected':selected})))])

class RankTests(unittest.IsolatedAsyncioTestCase):
    async def test_country_uses_the_shared_text_ranker_and_country_specific_brief(self):
        fact=country_fixture();queries=country_ranking_queries(fact)
        self.assertGreaterEqual(len(queries),6)
        self.assertTrue(all(q.startswith('Japan ') for q in queries))
        brief=ranking_input(fact,[photo(0)])
        self.assertEqual(brief['lesson']['name'],'Japan')
        self.assertIn('everyday_life',brief['lesson']);self.assertIn('places',brief['lesson'])
        counter=iter(range(100));fetch=AsyncMock(side_effect=lambda query:[photo(next(counter)),photo(next(counter))])
        rank=AsyncMock(side_effect=lambda fact,photos,**kwargs:photos[:10])
        self.assertEqual(len(await select_country_photos(fact,fetch=fetch,rank=rank)),10)
        self.assertEqual(rank.await_count,1)
    async def test_failure_has_one_initial_attempt_and_five_retries_with_no_sdk_retries(self):
        create=AsyncMock(side_effect=TimeoutError('offline'))
        client=types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)),close=AsyncMock())
        constructor=Mock(return_value=client);report=Mock()
        modules={'openai':types.SimpleNamespace(AsyncOpenAI=constructor),
            'configs.config':types.SimpleNamespace(get_config=lambda:types.SimpleNamespace(OPENAI_API_KEY='test-only'))}
        with patch.dict(sys.modules,modules),patch('src.facts.photo_ranking.asyncio.sleep',new=AsyncMock()) as sleep:
            with self.assertRaises(PhotoRankingUnavailable):await rank_photos(fixture(),[photo(0)],report=report)
        self.assertEqual(create.await_count,6);self.assertEqual(sleep.await_count,5)
        self.assertEqual(constructor.call_args.kwargs['max_retries'],0)
        self.assertEqual([c.args[0]['attempt'] for c in report.call_args_list],[1,2,3,4,5,6])
        client.close.assert_awaited_once()

    async def test_retry_recovers_and_request_contains_only_text_metadata_with_exact_model(self):
        photos=[photo(i) for i in range(10)]
        create=AsyncMock(side_effect=[RuntimeError('temporary'),response(photos),response(photos)])
        client=types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
        with patch('src.facts.photo_ranking.asyncio.sleep',new=AsyncMock()):
            self.assertEqual(len(await rank_photos(fixture(),photos,client=client)),10)
            self.assertEqual(len(await rank_photos(fixture(),photos,client=client)),10)
        self.assertEqual(create.await_count,3) # The second run is not a cached ranking.
        request=create.call_args.kwargs
        self.assertEqual(request['model'],'gpt-6-luna');self.assertFalse(request['store'])
        self.assertTrue(all(isinstance(m['content'],str) for m in request['messages']))
        payload=json.loads(request['messages'][1]['content'])
        self.assertEqual(set(payload['photos'][0]),{'photo_id','description','alt_description'})
        self.assertNotIn('https://',json.dumps(payload['photos']))

    async def test_wider_search_runs_when_first_ranking_cannot_supply_ten(self):
        f=fixture();f['india_lesson']['carousel_queries']=[f'root bridge location{i}' for i in range(6)]
        counter=iter(range(100))
        fetch=AsyncMock(side_effect=lambda query:[photo(next(counter)),photo(next(counter))])
        async def rank(fact,photos,**kwargs):return photos[:5] if len(photos)<20 else photos[:10]
        ranked=AsyncMock(side_effect=rank)
        result=await select_india_photos(f,fetch=fetch,rank=ranked)
        self.assertEqual(len(result),10);self.assertEqual(ranked.await_count,2)
        self.assertEqual(fetch.await_count,12)

    async def test_successful_but_irrelevant_ranking_does_not_pad_with_popular_photos(self):
        counter=iter(range(100));fetch=AsyncMock(side_effect=lambda query:[photo(next(counter)),photo(next(counter))])
        self.assertEqual(await select_india_photos(fixture(),fetch=fetch,rank=AsyncMock(return_value=[])),[])

    def test_unknown_duplicate_and_invalid_scores_are_rejected(self):
        for rows in ([{'photo_id':'unknown','score':90,'scene':'Scene','reason':'Reason'}],
            [dict(photo_id='p0',score=True,scene='Scene',reason='Reason')],
            [dict(photo_id='p0',score=90,scene='Scene',reason='Reason')]*2):
            with self.assertRaises(ValueError):validate_ranking({'selected':rows},[photo(0)])

class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_country_photo_only_upgrade_publishes_ten_ranked_photos_without_genai(self):
        r=routes_module();f=enrich_country_identity(country_fixture())
        r.select_country_photos=AsyncMock(return_value=[photo(i) for i in range(10)])
        r.track_selection=AsyncMock(return_value=True)
        await r._background_image_task({},'hash',existing_images={'cover':'https://example.org/existing'},article=f,photos_only=True)
        r.generate_and_save_image.assert_not_awaited();r.find_country_photos.assert_not_awaited()
        scenes=[c for c in r.set_fact_image_state.call_args_list if (c.kwargs.get('credit') or {}).get('country_carousel')]
        self.assertEqual(len(scenes),10)
        self.assertTrue(all(len(c.kwargs['gallery'])==1 for c in scenes))
        self.assertEqual(r.set_fact_photo_selection.call_args.args[1]['selected_count'],10)
        r.finish_country_photo_enrichment.assert_called_once_with('hash')

    async def test_country_ranker_failure_uses_legacy_search_and_shortage_never_pads(self):
        r=routes_module();f=enrich_country_identity(country_fixture())
        await r._background_image_task({},'hash',article=f,photos_only=True)
        self.assertEqual(r.find_country_photos.await_count,12)
        self.assertEqual(r.set_fact_photo_selection.call_args.args[1]['mode'],'legacy_fallback')
        r=routes_module();r.select_country_photos=AsyncMock(return_value=[photo(i) for i in range(9)])
        r.track_selection=AsyncMock(return_value=True)
        await r._background_image_task({},'hash',article=f,photos_only=True)
        r.find_country_photos.assert_not_awaited();r.generate_and_save_image.assert_not_awaited()
        self.assertEqual(r.set_fact_photo_selection.call_args.args[1]['status'],'insufficient')

    def test_country_ranked_slots_keep_the_shared_async_timeout_and_generated_cap(self):
        f=enrich_country_identity(country_fixture());keys=fact_image_keys(f)
        self.assertEqual(len([k for k in keys if k.startswith('country_ranked_')]),18)
        self.assertNotIn('explanation_3',keys)
        self.assertEqual(f['country_media']['generated_limit'],4)
        state=image_generation_state({'full_response':f,'image_started_at':datetime.now(timezone.utc)-timedelta(seconds=400),
            'image_status':dict.fromkeys(keys,'processing')},300)
        self.assertEqual(state['status'],'processing');self.assertEqual(state['timeout_seconds'],720)
    async def test_article_completes_before_media_is_scheduled(self):
        r=routes_module();f=fixture();prepare_india_media(f)
        r.generate_daily_fact=AsyncMock(return_value=f);r.store_fact.return_value='hash'
        r.get_fact_by_hash.return_value={'full_response':f,'images':{}}
        def schedule(coroutine):
            self.assertEqual(r.update_fact_job.call_args.args[:2],('job','completed'))
            coroutine.close()
        with patch.object(r.asyncio,'create_task',side_effect=schedule) as create:
            await r.process_fact_generation_task('job','india',[])
        create.assert_called_once();r.select_india_photos.assert_not_awaited()

    async def test_ten_ranked_photos_publish_without_legacy_search_and_optional_slots_finish(self):
        r=routes_module();f=fixture();prepare_india_media(f)
        r.select_india_photos=AsyncMock(return_value=[photo(i) for i in range(10)])
        r.track_selection=AsyncMock(return_value=True)
        await r._background_image_task({},'hash',article=f)
        r.find_country_photos.assert_not_awaited();r.generate_and_save_image.assert_not_awaited()
        scenes=[c.kwargs['credit'] for c in r.set_fact_image_state.call_args_list if (c.kwargs.get('credit') or {}).get('selection_mode')=='llm_ranked']
        self.assertEqual(len(scenes),10)
        self.assertEqual(len([c for c in r.set_fact_image_state.call_args_list if c.args[2]=='not_requested']),8)
        self.assertEqual(r.set_fact_photo_selection.call_args.args[1]['selected_count'],10)

    async def test_less_than_ten_ranked_photos_are_not_published_or_padded(self):
        r=routes_module();f=fixture();prepare_india_media(f)
        r.select_india_photos=AsyncMock(return_value=[photo(i) for i in range(9)])
        r.track_selection=AsyncMock(return_value=True)
        await r._background_image_task({},'hash',article=f)
        scenes=[c for c in r.set_fact_image_state.call_args_list if (c.kwargs.get('credit') or {}).get('india_carousel')]
        self.assertEqual(scenes,[])
        self.assertEqual(r.set_fact_photo_selection.call_args.args[1]['status'],'insufficient')
        r.find_country_photos.assert_not_awaited()

    def test_ranked_media_keeps_polling_beyond_normal_image_timeout(self):
        f=fixture();prepare_india_media(f);keys=fact_image_keys(f)
        state=image_generation_state({'full_response':f,'image_started_at':datetime.now(timezone.utc)-timedelta(seconds=400),
            'image_status':dict.fromkeys(keys,'processing')},300)
        self.assertEqual(state['status'],'processing');self.assertEqual(state['timeout_seconds'],720)
