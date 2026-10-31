"""Global food contracts, scene-bound ranking and the asynchronous image budget."""
import copy
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
APP=Path(__file__).resolve().parents[1]/'app';sys.path.insert(0,str(APP))
package=types.ModuleType('src.facts');package.__path__=[str(APP/'src/facts')];sys.modules.setdefault('src.facts',package)
from src.facts.food import validate_food_content,prepare_food_media,build_food_prompt
from src.facts.lifecycle import fact_image_keys
from src.facts.photo_ranking import select_food_photos,validate_ranking,PhotoRankingUnavailable,ranking_input
from test_fact_evidence_lifecycle import routes_module,generator_module

def fixture():return json.loads((Path(__file__).parent/'fixtures/food_lesson.json').read_text())
def photo(i=0):
    return {'provider':'wikimedia','provider_id':f'commons_{i}','url':f'https://upload.wikimedia.org/hummus{i}.jpg',
        'source_url':f'https://commons.wikimedia.org/wiki/File:Hummus{i}.jpg','title':'Hummus','description':'Hummus served in a bowl',
        'author':'Photographer','license':'CC BY-SA 4.0','license_url':'https://creativecommons.org/licenses/by-sa/4.0/'}

class FoodContractTests(unittest.TestCase):
    def test_global_food_contract_and_server_owned_two_image_budget(self):
        f=fixture();self.assertTrue(validate_food_content(f))
        f['images']={'cover':'untrusted'};f['food_media']={'generated_limit':100}
        prepare_food_media(f)
        self.assertEqual(f['images'],{});self.assertEqual(f['food_media']['generated_limit'],2)
        self.assertEqual(set(fact_image_keys(f)),{'cover','overview','food_photo_0','food_photo_1','food_photo_2',*[f'food_scene_{n}' for n in range(6)]})
        self.assertIn('across continents',build_food_prompt(['old food']))
        self.assertIn('old food',build_food_prompt(['old food']))

    def test_incomplete_recipe_bad_source_and_invented_precision_are_rejected(self):
        for mutate in (lambda l:l['recipe']['ingredients'][0].update(amount=0),
            lambda l:l['recipe'].update(servings=1.5),
            lambda l:l['recipe']['steps'][0].update(ingredient_ids=['not-in-recipe']),
            lambda l:l['recipe']['substitutions'][0].update(ingredient_id='missing'),
            lambda l:l['recipe'].update(source_ids=['missing']),
            lambda l:l['recipe']['steps'][0].update(doneness_cue=''),
            lambda l:l['nutrition_context'].update(estimate_status='estimated',nutrients=[]),
            lambda l:l['photos'][0].update(section_id='missing')):
            f=fixture();mutate(f['food_lesson']);self.assertFalse(validate_food_content(f))
        f=fixture();f['visual_suggestions']['how_it_works']='Extra paid image'
        self.assertFalse(validate_food_content(f))

    def test_model_photo_assignments_cannot_invent_recipe_scenes(self):
        p=photo();row={'photo_id':p['provider_id'],'score':90,'scene':'dish','reason':'The metadata names hummus.'}
        result=validate_ranking({'selected':[row]},[p],request_ids={'dish'})
        self.assertEqual(result[0]['food_request_ids'],['dish'])
        row['scene']='made-up-step'
        with self.assertRaises(ValueError):validate_ranking({'selected':[row]},[p],request_ids={'dish'})
        self.assertIn('sensory_profile',ranking_input(fixture(),[p])['lesson'])

class FoodAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_photo_pool_combines_sources_deduplicates_and_keeps_scene_requests(self):
        p=photo();fetch=AsyncMock(return_value=[p]);commons=AsyncMock(return_value=[p])
        rank=AsyncMock(side_effect=lambda f,photos,**kw:photos)
        result=await select_food_photos(fixture(),fetch=fetch,commons=commons,rank=rank)
        self.assertEqual(len(result),1);self.assertEqual(len(result[0]['food_request_ids']),3)
        rank.assert_awaited_once();self.assertEqual(fetch.await_count,3);self.assertEqual(commons.await_count,3)

    async def test_model_failure_uses_conservative_subject_match(self):
        result=await select_food_photos(fixture(),fetch=AsyncMock(return_value=[photo()]),commons=AsyncMock(return_value=[]),
            rank=AsyncMock(side_effect=PhotoRankingUnavailable()))
        self.assertEqual(len(result),1);self.assertEqual(result[0]['food_request_ids'],['dish'])
        result=await select_food_photos(fixture(),fetch=AsyncMock(return_value=[{**photo(),'title':'Restaurant','description':'A dining room'}]),
            commons=AsyncMock(return_value=[]),rank=AsyncMock(side_effect=PhotoRankingUnavailable()))
        self.assertEqual(result,[])

    async def test_photo_only_worker_binds_photos_preserves_cover_and_never_generates(self):
        r=routes_module();f=fixture();prepare_food_media(f)
        r.track_selection=AsyncMock(return_value=True)
        r.select_food_photos=AsyncMock(return_value=[{**photo(),'food_request_ids':['dish']},{**photo(1),'food_request_ids':['dish']}])
        await r._background_image_task({},'hash',{'cover':'https://example.org/existing'},article=f,photos_only=True)
        r.generate_and_save_image.assert_not_awaited();r.track_selection.assert_not_awaited()
        ready=[c for c in r.set_fact_image_state.call_args_list if c.args[2]=='ready']
        self.assertEqual([c.args[1] for c in ready],['food_photo_0','food_scene_0'])
        self.assertEqual(ready[0].kwargs['credit']['section_id'],'overview')
        self.assertEqual(r.set_fact_photo_selection.call_args.args[1]['status'],'completed')

    async def test_food_generates_only_cover_overview_and_keeps_ai_labels(self):
        r=routes_module();f=fixture();prepare_food_media(f)
        r.generate_and_save_image=AsyncMock(return_value='https://example.org/generated.jpg')
        await r._background_image_task({**f['visual_suggestions'],'how_it_works':'Unrequested extra'},'hash',article=f)
        self.assertEqual(r.generate_and_save_image.await_count,2)
        generated=[c for c in r.set_fact_image_state.call_args_list if (c.kwargs.get('credit') or {}).get('kind')=='generated']
        self.assertEqual({c.args[1] for c in generated},{'cover','overview'})

    async def test_generation_routes_food_to_dedicated_prompt_and_contract(self):
        module=generator_module();f=fixture()
        module.genai.Client.return_value.aio.models.generate_content=AsyncMock(return_value=types.SimpleNamespace(parsed=f))
        result=await module.generate_daily_fact('food',[])
        self.assertIsNotNone(result);self.assertEqual(result['food_media']['generated_limit'],2)
        prompt=module.genai.Client.return_value.aio.models.generate_content.call_args.kwargs['contents']
        self.assertIn('across continents',prompt);self.assertNotIn('INDIA-FIRST RULE',prompt)

if __name__=='__main__':unittest.main()
