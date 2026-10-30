"""Offline Unsplash contract and provider failure checks. No real API calls."""
import copy
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from test_country import fixture
from src.facts import unsplash_photos as u
from src.facts.country_photos import find_country_photos
from src.facts.country_photos import _lookup_subject, country_scene_queries
from src.facts.lifecycle import fact_image_keys, image_generation_state


def payload():
    return {'results': [{'id':'sample', 'width':2400, 'height':1600,
        'description':'Kyoto street in Japan', 'alt_description':'Japan street',
        'urls':{'regular':'https://images.unsplash.com/photo-sample?ixid=retained&w=1080'},
        'links':{'html':'https://unsplash.com/photos/sample',
            'download_location':'https://api.unsplash.com/photos/sample/download?ixid=retained'},
        'user':{'name':'Photographer', 'links':{'html':'https://unsplash.com/@photographer'}}}]}


class UnsplashTests(unittest.TestCase):
    def test_scene_searches_cover_different_facets(self):
        queries=country_scene_queries(fixture()['country_profile'])
        self.assertEqual(len(set(queries)),4)
        self.assertIn('local market daily life',queries)

    def test_exact_subject_lookup_rejects_unrelated_country_fallback_and_statues(self):
        from test_country import candidate
        data=candidate();page=data['query']['pages']['1']
        page['title']='File:Katsushika Hokusai portrait.jpg'
        class Response:
            status_code=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def iter_content(self,size):
                import json
                return iter([json.dumps(data).encode()])
        with patch('requests.get',return_value=Response()):
            self.assertEqual(len(_lookup_subject('Japan','Katsushika Hokusai','people')),1)
            self.assertEqual(_lookup_subject('Japan','Yasunari Kawabata','people'),[])
            page['title']='File:Katsushika Hokusai statue.jpg'
            self.assertEqual(_lookup_subject('Japan','Katsushika Hokusai','people'),[])
            page['title']='File:Kabukicho Japan.jpg'
            self.assertEqual(_lookup_subject('Japan','Kabuki','culture'),[])

    def test_subject_assets_remain_pending_after_the_cover_loads(self):
        from datetime import datetime,timezone
        f=fixture();f['country_media']={'version':2,'photo_layout':'contextual_v1'}
        keys=fact_image_keys(f)
        self.assertIn('country_people_0',keys)
        state=image_generation_state({'full_response':f,'images':{'cover':'https://example.org/cover.jpg'},
            'image_started_at':datetime.now(timezone.utc),'image_status':{k:'processing' for k in keys}},120)
        self.assertIn('country_people_0',state['pending'])

    def test_access_key_alias_and_provider_specific_precedence(self):
        with patch.dict(os.environ, {'ACCESS_KEY':'alias-only', 'UNSPLASH_ACCESS_KEY':''}):
            self.assertEqual(u.access_key(),'alias-only')
        with patch.dict(os.environ, {'ACCESS_KEY':'alias-only', 'UNSPLASH_ACCESS_KEY':'specific'}):
            self.assertEqual(u.access_key(),'specific')

    def test_metadata_hotlinks_and_attribution(self):
        item = u.candidates(payload(), 'Japan')[0]
        self.assertIn('ixid=retained', item['url'])
        self.assertIn('utm_source=the_curiosity_archive', item['author_url'])
        self.assertEqual(item['license'], 'Unsplash License')
        self.assertEqual(u.candidates(payload(), 'Costa Rica'), [])
        for field, value in [('width',200), ('urls',{'regular':'https://evil.example/photo'}),
                ('user',{}), ('links',{'html':'https://unsplash.com/photos/sample',
                'download_location':'https://api.unsplash.com.evil.example/photos/sample/download'})]:
            data=payload();data['results'][0][field]=value
            self.assertEqual(u.candidates(data,'Japan'),[])

    def test_missing_key_and_provider_errors_fail_closed(self):
        with patch.dict(os.environ, {'UNSPLASH_ACCESS_KEY':'','ACCESS_KEY':''}), patch('requests.get') as get:
            self.assertEqual(u._search('Japan','Kyoto'),[]);get.assert_not_called()
        for status in (401,403,429,500):
            with patch.dict(os.environ, {'UNSPLASH_ACCESS_KEY':'test-only'}), patch('requests.get',return_value=Mock(status_code=status)):
                self.assertEqual(u._search('Japan','Kyoto'),[])

    def test_tracking_only_valid_provider_endpoint(self):
        with patch.dict(os.environ, {'UNSPLASH_ACCESS_KEY':'test-only'}), patch('requests.get',return_value=Mock(status_code=200)) as get:
            self.assertTrue(u._track(u.candidates(payload(),'Japan')[0]))
            self.assertFalse(u._track({'download_location':'https://evil.example/download'}))
            self.assertEqual(get.call_count,1)
            self.assertFalse(get.call_args.kwargs['allow_redirects'])


class ProviderRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_scene_fallback_keeps_its_theme_and_country(self):
        photo=u.candidates(payload(),'Japan')[0]
        photo['description']='Mountain landscape in Japan'
        with patch.object(u,'search',new=AsyncMock(side_effect=[[],[photo]])) as search:
            self.assertEqual(await find_country_photos('Japan','landscape nature',scene_only=True),[photo])
            self.assertEqual(search.await_args_list[1].args,('Japan','landscape'))

    async def test_contextual_worker_attaches_subjects_and_preserves_generation_budget(self):
        from test_fact_evidence_lifecycle import routes_module
        from test_country import candidate,photo_candidates
        routes=routes_module();f=fixture();f['country_media']={'version':2,'photo_layout':'contextual_v1'}
        routes.find_subject_photo=AsyncMock(side_effect=lambda country,subject,kind,**kwargs:[{
            **photo_candidates(candidate())[0], 'source_url':f'https://commons.wikimedia.org/wiki/File:{kind}-{subject}',
            'provider':'wikimedia','subject':subject,'subject_kind':kind}])
        routes.generate_and_save_image=AsyncMock(return_value='https://example.org/generated.jpg')
        await routes._background_image_task(f['visual_suggestions'],'hash',article=f)
        self.assertLessEqual(routes.generate_and_save_image.await_count,4)
        states={call.args[1]:call for call in routes.set_fact_image_state.call_args_list}
        self.assertEqual(states['country_people_0'].kwargs['credit']['subject'],f['country_profile']['notable_people'][0]['name'])
        self.assertEqual(routes.find_country_photos.await_count,4)
        self.assertTrue(all(call.kwargs['scene_only'] for call in routes.find_country_photos.call_args_list))

    async def test_named_people_never_use_stock(self):
        with patch('src.facts.country_photos._lookup',return_value=[]), patch.object(u,'search',new=AsyncMock()) as search:
            await find_country_photos('Japan','Japan Katsushika Hokusai', ['Katsushika Hokusai'])
            search.assert_not_awaited()

    async def test_tracking_failure_keeps_commons_and_does_not_publish_stock(self):
        from test_fact_evidence_lifecycle import routes_module
        from test_country import candidate, photo_candidates
        routes=routes_module();stock=u.candidates(payload(),'Japan')[0]
        routes.find_country_photos=AsyncMock(return_value=[stock,photo_candidates(candidate())[0]])
        routes.track_selection=AsyncMock(return_value=False)
        f=fixture();f.pop('country_media',None)
        await routes._background_image_task({'cover':'Japan Kyoto'},'hash',article=f)
        saved=routes.set_fact_image_state.call_args.kwargs
        self.assertEqual(len(saved['gallery']),1)
        self.assertNotEqual(saved['credit'].get('provider'),'unsplash')


if __name__ == '__main__': unittest.main()
