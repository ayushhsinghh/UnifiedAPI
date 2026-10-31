"""India topic contracts and photo lifecycle; no paid calls or production writes."""
import copy
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
APP=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(APP))
package=types.ModuleType('src.facts');package.__path__=[str(APP/'src/facts')]
sys.modules.setdefault('src.facts',package)
from src.facts.india import validate_india_content,prepare_india_media,india_photo_entries,build_india_prompt
from src.facts.image_policy import validate_image_plan
from src.facts.lifecycle import fact_image_keys
from test_fact_evidence_lifecycle import routes_module

def fixture():return json.loads((Path(__file__).parent/'fixtures/india_lesson.json').read_text())

class IndiaContractTests(unittest.TestCase):
    def test_root_bridge_subject_match_rejects_a_regional_river(self):
        from src.facts.india import india_carousel_matches,india_carousel_searches
        f={'topic':'Meghalaya Living Root Bridges','india_lesson':{'region':'Meghalaya, Northeast India','case_study':{'place':'Nongriat Village, Sohra, Meghalaya'}}}
        q='Living root bridge Meghalaya'
        self.assertFalse(india_carousel_matches({'title':'Umngot river in Meghalaya','description':'Boats on a river in India'},q,f))
        self.assertTrue(india_carousel_matches({'title':'Living root bridges in Meghalaya','description':'A root bridge in India'},q,f))
        searches=india_carousel_searches(q,f)
        self.assertEqual(searches[:2],[q,'Living root bridge'])
        self.assertIn('Meghalaya bridge',searches);self.assertIn('root bridge',searches)
        self.assertIn('Meghalaya',searches)
        self.assertLessEqual(len(searches),5)
        tagged={'title':'A misty scene','description':'Morning in India','tags':['India','Meghalaya','bridge','root']}
        self.assertTrue(india_carousel_matches(tagged,'Meghalaya bridge',f))
        tagged['tags']=['India','Meghalaya','river']
        self.assertFalse(india_carousel_matches(tagged,'Meghalaya bridge',f))
    def test_carousel_searches_stay_topic_specific_and_bounded(self):
        from src.facts.india import india_carousel_queries,india_carousel_keys
        f=fixture();f['india_lesson']['carousel_queries']=['Gujarat stepwell','Adalaj stepwell','Rani ki Vav']
        self.assertTrue(validate_india_content(f));prepare_india_media(f)
        self.assertEqual(india_carousel_queries(f)[:3],['Gujarat stepwell','Adalaj stepwell','Rani ki Vav'])
        self.assertLessEqual(len(india_carousel_keys(f)),18)
        f['india_lesson']['carousel_queries']=['India']
        self.assertFalse(validate_india_content(f))

    def test_one_topic_contract_and_exact_two_image_budget(self):
        f=fixture();self.assertTrue(validate_india_content(f));self.assertTrue(validate_image_plan(f))
        f['visual_suggestions']['how_it_works']='An unrequested extra image'
        self.assertFalse(validate_image_plan(f));self.assertFalse(validate_india_content(f))

    def test_incomplete_topics_bad_sources_and_unbound_photos_are_rejected(self):
        for mutate in (lambda l:l['chapters'][0].update(source_ids=['missing']),
            lambda l:l['photos'][0].update(section_id='missing'),
            lambda l:l['photos'][1].update(section_id='route'),
            lambda l:l['chapters'][0].update(details=['One fragment']),
            lambda l:l['case_study'].update(story=''),
            lambda l:l['chapters'][0].update(id='background')):
            f=fixture();mutate(f['india_lesson']);self.assertFalse(validate_india_content(f))

    def test_server_owns_media_metadata_and_photo_slots_are_polled(self):
        f=fixture();f['images']={'cover':'model-authored'};f['india_media']={'generated_limit':100}
        prepare_india_media(f)
        self.assertEqual(f['images'],{});self.assertEqual(f['india_media']['generated_limit'],2)
        keys=set(fact_image_keys(f))
        self.assertTrue({'cover','overview','india_photo_0','india_photo_1'}<=keys)
        self.assertEqual(len([k for k in keys if k.startswith('india_scene_')]),9)
        self.assertIn('ONE rich, specific topic',build_india_prompt(['recent topic']))

class IndiaWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_multiple_searches_each_contribute_three_popular_fallback_photos(self):
        r=routes_module();f=fixture();prepare_india_media(f)
        async def search(country,query,**kwargs):
            return [dict(provider='unsplash',provider_id=f'{query}-{n}',url=f'https://images.unsplash.com/{query}-{n}',
                source_url=f'https://unsplash.com/photos/{query}-{n}',title='A river',description='A river in India',
                detail_fetched=True,selection_mode='popular_fallback') for n in range(3)]
        self.stock.side_effect=search;r.track_selection=AsyncMock(return_value=True)
        await r._background_image_task({},'hash',article=f)
        from collections import Counter
        scenes=[c.kwargs['credit'] for c in r.set_fact_image_state.call_args_list if (c.kwargs.get('credit') or {}).get('india_carousel')]
        counts=Counter(p['scene_query'] for p in scenes)
        self.assertGreaterEqual(len(counts),3)
        self.assertTrue(all(count==3 for count in counts.values()))
        self.assertTrue(all(c.kwargs.get('popular_fallback') for c in self.stock.call_args_list))
        r.generate_and_save_image.assert_not_awaited()

    async def test_bad_saved_scene_is_replaced_by_commons_without_paid_generation(self):
        r=routes_module();f=fixture();prepare_india_media(f)
        f['india_lesson']['carousel_queries']=['Gujarat stepwell']
        f['image_credits']={'india_scene_0':{'title':'River in Gujarat','description':'A river in India'}}
        r.find_subject_photo=AsyncMock(return_value=[dict(provider='wikimedia',url='https://upload.wikimedia.org/stepwell',
            source_url='https://commons.wikimedia.org/wiki/File:Stepwell',title='Gujarat stepwell',description='Rani ki Vav stepwell India')])
        await r._background_image_task({},'hash',existing_images={'india_scene_0':'https://images.unsplash.com/river',
            'india_photo_0':'https://example.org/inline0','india_photo_1':'https://example.org/inline1'},article=f)
        r.generate_and_save_image.assert_not_awaited()
        self.assertTrue(any(c.kwargs.get('clear') for c in r.set_fact_image_state.call_args_list))
        scenes=[c.kwargs['credit'] for c in r.set_fact_image_state.call_args_list if (c.kwargs.get('credit') or {}).get('india_carousel')]
        self.assertTrue(scenes);self.assertTrue(all(p['provider']=='wikimedia' for p in scenes))

    async def asyncSetUp(self):
        self.stock_patch=patch('src.facts.unsplash_photos.search',new=AsyncMock(return_value=[]))
        self.stock=self.stock_patch.start();self.addCleanup(self.stock_patch.stop)

    async def test_unsplash_carousel_uses_multiple_queries_and_never_generates_ai(self):
        r=routes_module();f=fixture();prepare_india_media(f)
        from src.facts.india import india_carousel_queries
        async def search(country,query,**kwargs):
            return [dict(provider='unsplash',url=f'https://images.unsplash.com/{query}-{n}',
                source_url=f'https://unsplash.com/photos/{query}-{n}',title=query,
                description=f'{query} stepwell unique{n} token{len(query)}') for n in range(2)]
        self.stock.side_effect=search;r.track_selection=AsyncMock(return_value=True)
        await r._background_image_task({},'hash',article=f)
        phrases=[c.args[1].casefold() for c in self.stock.await_args_list]
        self.assertEqual(len(phrases),len(set(phrases)))
        self.assertGreaterEqual(len(phrases),len(india_carousel_queries(f)))
        r.generate_and_save_image.assert_not_awaited()
        credits=[c.kwargs.get('credit') for c in r.set_fact_image_state.call_args_list if (c.kwargs.get('credit') or {}).get('india_carousel')]
        self.assertGreaterEqual(len(credits),2)
        self.assertTrue(all(c['provider']=='unsplash' for c in credits))
    async def test_scene_photos_use_stock_tracking_and_keep_only_topic_matches(self):
        r=routes_module();f=fixture();f['india_lesson']['photos']=f['india_lesson']['photos'][:1]
        f['india_lesson']['photos'][0].update(kind='scene',subject='Pottery',query='Rajasthan pottery')
        unrelated=dict(url='https://images.unsplash.com/unrelated',source_url='https://unsplash.com/photos/unrelated',provider='unsplash',title='A beach in India',description='India')
        matching=dict(url='https://images.unsplash.com/pottery',source_url='https://unsplash.com/photos/pottery',provider='unsplash',title='Pottery in Rajasthan',description='A pottery workshop in India')
        r.find_country_photos=AsyncMock(return_value=[unrelated,matching]);r.find_subject_photo=AsyncMock()
        r.track_selection=AsyncMock(return_value=True)
        await r._background_image_task({},'hash',article=f)
        r.generate_and_save_image.assert_not_awaited();r.find_subject_photo.assert_not_awaited()
        r.track_selection.assert_awaited_once_with(matching)
        self.assertEqual(r.set_fact_image_state.call_args.kwargs['credit']['url'],matching['url'])

    async def test_generation_uses_the_india_schema_and_rejects_an_extra_ai_image(self):
        from test_fact_evidence_lifecycle import generator_module
        from src.facts.india import INDIA_RESPONSE_SCHEMA
        r=generator_module();r.validate_image_plan=validate_image_plan
        invalid=fixture();invalid['visual_suggestions']['how_it_works']='Extra AI image'
        valid=fixture();valid['india_validation']={'source_verification':'invented claim'}
        create=AsyncMock(side_effect=[types.SimpleNamespace(parsed=invalid),types.SimpleNamespace(parsed=valid)])
        r.genai.Client.return_value.aio.models.generate_content=create
        with patch.object(r.asyncio,'sleep',new=AsyncMock()):result=await r.generate_daily_fact('india')
        self.assertEqual(create.await_count,2)
        self.assertIs(create.call_args.kwargs['config']['response_schema'],INDIA_RESPONSE_SCHEMA)
        self.assertEqual(result['india_validation']['source_verification'],'not_performed')
        self.assertEqual(set(result['visual_suggestions']),{'cover','overview'})

    async def test_exactly_two_generated_images_and_exact_subject_photo_routing(self):
        r=routes_module();f=fixture();prepare_india_media(f)
        f['visual_suggestions']['explanation_6']='Must never generate this'
        r.generate_and_save_image=AsyncMock(return_value='https://example.org/illustration.jpg')
        r.find_subject_photo=AsyncMock(return_value=[])
        await r._background_image_task(f['visual_suggestions'],'hash',article=f)
        self.assertEqual(r.generate_and_save_image.await_count,2)
        self.assertEqual(len([c for c in r.find_subject_photo.await_args_list if c.args[2]=='places']),2)
        r.find_country_photos.assert_not_awaited()
        self.assertEqual(r.find_subject_photo.await_args_list[0].args,('India','Rani ki Vav','places'))

    async def test_photo_credits_keep_section_binding_and_failed_photos_do_not_generate(self):
        r=routes_module();f=fixture();f['india_lesson']['photos'][0].update(kind='person',subject='A named person')
        r.find_subject_photo=AsyncMock(side_effect=[[dict(url='https://upload.wikimedia.org/a.jpg',provider='wikimedia',
            title='A portrait',description='A portrait',source_url='https://commons.wikimedia.org/wiki/File:A.jpg')],[]])
        await r._background_image_task({},'hash',article=f)
        r.generate_and_save_image.assert_not_awaited()
        self.assertEqual(r.find_subject_photo.await_args_list[0].args,('India','A named person','people'))
        credits=[c.kwargs.get('credit') for c in r.set_fact_image_state.call_args_list if c.kwargs.get('credit')]
        self.assertEqual(credits[0]['section_id'],'route');self.assertEqual(credits[0]['photo_id'],'route-photo')
