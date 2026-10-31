"""Fashion reader contracts, exact scene binding and bounded media without live calls."""
import json
import sys
import types
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import AsyncMock
APP=Path(__file__).resolve().parents[1]/'app';sys.path.insert(0,str(APP))
package=types.ModuleType('src.facts');package.__path__=[str(APP/'src/facts')];sys.modules.setdefault('src.facts',package)
from src.facts.fashion import validate_fashion_content,prepare_fashion_media,build_fashion_prompt
from src.facts.photo_ranking import select_fashion_photos,rank_photos,PhotoRankingUnavailable
from src.facts.lifecycle import fact_image_keys,image_generation_state
from test_fact_evidence_lifecycle import routes_module,generator_module

def fixture():return json.loads((Path(__file__).parent/'fixtures/fashion_lesson.json').read_text())
def photo(i=0,provider='wikimedia'):
    return dict(provider=provider,provider_id=f'{provider}_{i}',url=f'https://upload.wikimedia.org/denim{i}.jpg',
        source_url=f'https://commons.wikimedia.org/wiki/File:Denim{i}.jpg',title='Denim fabric',description='A denim fabric sample',
        author='Photographer',license='CC BY-SA 4.0',license_url='https://creativecommons.org/licenses/by-sa/4.0/')

class FashionContractTests(unittest.TestCase):
    def test_global_contract_and_server_owned_budget(self):
        f=fixture();self.assertTrue(validate_fashion_content(f))
        f['images']={'cover':'untrusted'};f['fashion_media']={'generated_limit':100}
        prepare_fashion_media(f)
        self.assertEqual(f['images'],{});self.assertEqual(f['fashion_media']['generated_limit'],2)
        self.assertEqual(set(fact_image_keys(f)),{'cover','overview','fashion_photo_0','fashion_photo_1',*[f'fashion_scene_{n}' for n in range(6)]})
        state=image_generation_state({'full_response':f,'image_started_at':datetime.now(timezone.utc)-timedelta(seconds=400),
            'image_status':dict.fromkeys(fact_image_keys(f),'processing')},300)
        self.assertEqual(state['status'],'processing');self.assertEqual(state['timeout_seconds'],720)
        self.assertIn('across the world',build_fashion_prompt(['previous topic']))

    def test_technique_can_omit_irrelevant_wearing_care_and_variations(self):
        f=fixture();l=f['fashion_lesson'];l.update(subject_type='technique',practical_guide=None,wearing_properties=[],care=[],variations=[])
        self.assertTrue(validate_fashion_content(f))
        l['subject_type']='garment';self.assertFalse(validate_fashion_content(f))

    def test_invalid_sources_features_and_inactive_photo_requests_fail(self):
        for mutate in (lambda l:l['recognition_guide'][0].update(source_ids=['missing']),
            lambda l:l['recognition_guide'][1].update(id='diagonal'),
            lambda l:l['photos'][0].update(feature_id='not-a-feature'),
            lambda l:l['photos'][1].update(feature_id='diagonal'),
            lambda l:l['photos'][0].update(section_id='practical'),
            lambda l:l['materials'][0].update(material_type='unknown'),
            lambda l:l['recognition_guide'][0].update(where_to_look='')):
            f=fixture();mutate(f['fashion_lesson']);self.assertFalse(validate_fashion_content(f))
        f=fixture();f['visual_suggestions']['how_it_works']='Unrequested generated image'
        self.assertFalse(validate_fashion_content(f))

class FashionAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_ranker_uses_only_text_and_binds_valid_fashion_request_ids(self):
        p=photo();payload={'selected':[dict(photo_id=p['provider_id'],score=90,scene='recognition',reason='The metadata supports the requested feature.') ]}
        create=AsyncMock(return_value=types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps(payload)))]))
        client=types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
        selected=await rank_photos(fixture(),[p],client=client)
        self.assertEqual(selected[0]['fashion_request_ids'],['recognition'])
        request=create.call_args.kwargs;self.assertEqual(request['model'],'gpt-6-luna')
        texts=json.loads(request['messages'][1]['content'])
        self.assertIn('recognition_guide',texts['lesson']);self.assertNotIn('https://',json.dumps(texts['photos']))

    async def test_historical_objects_never_use_stock_even_after_cross_request_ranking(self):
        f=fixture();f['fashion_lesson']['photos'][0]['kind']='historical_object'
        stock=photo(1,'unsplash');common=photo()
        fetch=AsyncMock(return_value=[stock]);commons=AsyncMock(return_value=[common])
        rank=AsyncMock(return_value=[{**stock,'fashion_request_ids':['recognition']},{**common,'fashion_request_ids':['recognition']}])
        selected=await select_fashion_photos(f,fetch=fetch,commons=commons,rank=rank)
        self.assertEqual(fetch.await_count,1);self.assertEqual(commons.await_count,2)
        self.assertEqual(len(selected),1);self.assertEqual(selected[0]['provider'],'wikimedia')

    async def test_fallback_keeps_only_metadata_matched_request_ids(self):
        result=await select_fashion_photos(fixture(),fetch=AsyncMock(return_value=[photo()]),commons=AsyncMock(return_value=[]),
            rank=AsyncMock(side_effect=PhotoRankingUnavailable()))
        self.assertEqual(len(result),1);self.assertEqual(result[0]['fashion_request_ids'],['materials'])

    async def test_worker_keeps_ai_labels_two_image_limit_and_photo_bindings(self):
        r=routes_module();f=fixture();prepare_fashion_media(f)
        r.generate_and_save_image=AsyncMock(return_value='https://example.org/illustration.jpg')
        r.track_selection=AsyncMock(return_value=True)
        r.select_fashion_photos=AsyncMock(return_value=[{**photo(),'fashion_request_ids':['recognition']}])
        await r._background_image_task({**f['visual_suggestions'],'how_it_works':'Ignore extra'},'hash',article=f)
        self.assertEqual(r.generate_and_save_image.await_count,2);r.track_selection.assert_not_awaited()
        credits=[c for c in r.set_fact_image_state.call_args_list if c.kwargs.get('credit')]
        self.assertEqual(sum(c.kwargs['credit'].get('kind')=='generated' for c in credits),2)
        bound=next(c.kwargs['credit'] for c in credits if c.args[1]=='fashion_photo_0')
        self.assertEqual(bound['feature_id'],'diagonal');self.assertEqual(bound['section_id'],'recognition')
        self.assertEqual(r.set_fact_photo_selection.call_args.args[1]['status'],'completed')
        r=routes_module();r.generate_and_save_image=AsyncMock()
        await r._background_image_task(f['visual_suggestions'],'hash',{'cover':'https://example.org/old'},article=f,photos_only=True)
        r.generate_and_save_image.assert_not_awaited()

    async def test_generation_uses_global_fashion_contract(self):
        r=generator_module();f=fixture()
        r.genai.Client.return_value.aio.models.generate_content=AsyncMock(return_value=types.SimpleNamespace(parsed=f))
        result=await r.generate_daily_fact('fashion',[])
        self.assertIsNotNone(result);self.assertEqual(result['fashion_media']['generated_limit'],2)
        prompt=r.genai.Client.return_value.aio.models.generate_content.call_args.kwargs['contents']
        self.assertIn('across the world',prompt);self.assertNotIn('INDIA-FIRST RULE',prompt)

if __name__=='__main__':unittest.main()
