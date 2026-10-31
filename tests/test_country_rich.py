"""Richer country content and cached, strictly photo-only archive upgrades."""
import copy
import types
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import AsyncMock,Mock,patch
from test_country import fixture
from test_fact_evidence_lifecycle import routes_module
from src.facts.country import validate_country_content
from src.facts.country_media_plan import country_photo_entries,subject_queries
from src.facts.country_photos import _lookup_subject

class CountryDepthTests(unittest.TestCase):
    def test_topic_photo_search_rejects_incidental_mentions_and_diagnostic_scans(self):
        import json
        from test_country import candidate
        for title,subject,kind,description in [('Books about Costa Rica','Gallo Pinto','culture','Gallo Pinto in Costa Rica'),
            ('Coffee output graph','Coffee','products','Coffee in Costa Rica'),
            ('CT catheter scan','catheter','products','A diagnostic CT scan with a catheter')]:
            data=candidate();page=data['query']['pages']['1'];page['title']='File:'+title+'.jpg'
            page['imageinfo'][0]['extmetadata']['ImageDescription']['value']=description
            class Response:
                status_code=200
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def iter_content(self,size):return iter([json.dumps(data).encode()])
            with patch('requests.get',return_value=Response()):self.assertEqual(_lookup_subject('Costa Rica',subject,kind),[])

    def test_main_topics_require_supporting_details_example_and_photo_searches(self):
        self.assertTrue(validate_country_content(fixture()))
        for field in ('everyday_life','global_contributions','products_and_industries','notable_places','notable_people'):
            for key in ('details','example','photo_queries'):
                f=fixture();f['country_profile'][field][0].pop(key)
                self.assertFalse(validate_country_content(f))
        f=fixture();f['country_profile']['everyday_life'][0]['details']=['One fragment']
        self.assertFalse(validate_country_content(f))

    def test_archived_headlines_become_concrete_queries(self):
        title,queries=subject_queries({'title':'Gallo Pinto and Daily Cuisine'})
        self.assertEqual(queries[0],'Gallo Pinto')
        title,queries=subject_queries({'title':"The Meaning of 'Pura Vida'"})
        self.assertEqual(queries[0],'Pura Vida')
        _,queries=subject_queries({'title':"Healthcare ('La Caja')",'explanation':'The Caja Costarricense de Seguro Social (CCSS) provides care.'})
        self.assertEqual(queries[0],'CCSS')
        kinds={p['kind'] for p in country_photo_entries(fixture()['country_profile'])}
        self.assertEqual(kinds,{'culture','people','places','cities','products','contributions'})

class CountryPhotoBackfillTests(unittest.IsolatedAsyncioTestCase):
    async def test_twelve_scene_topics_keep_two_unique_photos_and_never_generate(self):
        r=routes_module();f=fixture();f['country_media']={'version':2,'photo_layout':'contextual_v2'}
        async def scenes(country,query,**kwargs):
            return [dict(provider='unsplash',url=f'https://images.unsplash.com/{query}-{n}',
                source_url=f'https://unsplash.com/photos/{query}-{n}',author='Same photographer',
                description=f'{query.replace(" ", "_")}_image{n}') for n in range(2)]
        r.find_country_photos=AsyncMock(side_effect=scenes)
        r.find_subject_photo=AsyncMock(return_value=[]);r.track_selection=AsyncMock(return_value=True)
        await r._background_image_task({},'hash',article=f,photos_only=True)
        scenes=[c for c in r.set_fact_image_state.call_args_list if c.args[1].startswith('explanation_') or c.args[1].startswith('country_scene_')]
        self.assertEqual(len(scenes),12)
        self.assertEqual(sum(len(c.kwargs['gallery']) for c in scenes),24)
        r.generate_and_save_image.assert_not_awaited()

    def test_previous_photo_cache_requires_the_expanded_scene_upgrade(self):
        r=routes_module()
        self.assertEqual(r._country_photo_payload({'full_response':fixture(),
            'country_photo_enrichment':{'version':2,'status':'completed'}})['status'],'not_started')

    async def test_another_worker_claim_prevents_duplicate_photo_jobs(self):
        r=routes_module();f=fixture();f.pop('country_media',None)
        initial={'full_response':f}
        busy={'full_response':f,'country_photo_enrichment':{'version':4,'status':'processing','started_at':datetime.now(timezone.utc)}}
        r.get_fact_by_hash.side_effect=[initial,busy];r.claim_country_photo_enrichment.return_value=False
        background=types.SimpleNamespace(add_task=Mock())
        self.assertEqual((await r.ensure_country_photos(None,'hash',background))['status'],'processing')
        background.add_task.assert_not_called()
    async def test_existing_articles_queue_only_photo_work_once(self):
        r=routes_module();f=fixture();f.pop('country_media',None)
        doc={'full_response':f,'images':{'cover':'https://example.org/existing.jpg'}}
        r.get_fact_by_hash.return_value=doc;r.claim_country_photo_enrichment.return_value=True
        background=types.SimpleNamespace(add_task=Mock())
        result=await r.ensure_country_photos(None,'hash',background)
        self.assertEqual(result['status'],'processing')
        self.assertTrue(background.add_task.call_args.kwargs['photos_only'])
        self.assertEqual(background.add_task.call_args.kwargs['article']['country_media']['photo_ranking_version'],1)
        self.assertEqual(result['country_media']['photo_ranking_version'],1)
        self.assertEqual(background.add_task.call_args.args[1],{})
        doc['country_photo_enrichment']={'version':4,'status':'completed'}
        background.add_task.reset_mock()
        result=await r.ensure_country_photos(None,'hash',background)
        background.add_task.assert_not_called();self.assertEqual(result['status'],'completed')

    async def test_photo_only_worker_searches_twelve_scenes_without_image_generation(self):
        r=routes_module();f=fixture();f['country_media']={'version':2,'photo_layout':'contextual_v2'}
        r.find_subject_photo=AsyncMock(return_value=[])
        await r._background_image_task(f['visual_suggestions'],'hash',article=f,photos_only=True)
        r.generate_and_save_image.assert_not_awaited()
        self.assertEqual(r.find_country_photos.await_count,12)
        self.assertEqual(r.find_subject_photo.await_count,len(country_photo_entries(f['country_profile'])))
        r.finish_country_photo_enrichment.assert_not_called()

    def test_stale_photo_worker_can_recover_without_stalling_the_reader(self):
        r=routes_module();doc={'full_response':fixture(),'country_photo_enrichment':{
            'version':4,'status':'processing','started_at':datetime.now(timezone.utc)-timedelta(minutes=16)}}
        self.assertEqual(r._country_photo_payload(doc)['status'],'failed')

if __name__=='__main__':unittest.main()
