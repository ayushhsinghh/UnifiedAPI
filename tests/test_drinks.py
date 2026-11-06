import json,sys,types,unittest
from pathlib import Path
from unittest.mock import AsyncMock,Mock
APP=Path(__file__).resolve().parents[1]/'app';sys.path.insert(0,str(APP))
pkg=types.ModuleType('src.facts');pkg.__path__=[str(APP/'src/facts')];sys.modules.setdefault('src.facts',pkg)
from src.facts.drinks import validate_drinks_content,ensure_drinks_photo_plan,prepare_drinks_media
from src.facts.photo_ranking import select_drinks_photos,rank_photos,PhotoRankingResult
from src.facts.lifecycle import fact_image_keys
from test_fact_evidence_lifecycle import routes_module,generator_module
from test_agriculture import photo
from test_photo_ranking import photo as stock

def fixture():return json.loads((Path(__file__).parent/'fixtures/drinks_lesson.json').read_text())
class DrinksTests(unittest.TestCase):
 def test_contract_science_budget_and_optional_science(self):
  f=fixture();self.assertTrue(validate_drinks_content(f));prepare_drinks_media(f);self.assertEqual(f['drinks_media']['generated_limit'],3)
  self.assertIn('how_it_works',fact_image_keys(f));self.assertIn('drinks_photo_7',fact_image_keys(f));self.assertIn('drinks_scene_11',fact_image_keys(f))
  f['drinks_lesson'].update(science=[],science_focus_id=None);f['visual_suggestions']['how_it_works']=None;f['image_details']=f['image_details'][:1]
  self.assertTrue(validate_drinks_content(f));prepare_drinks_media(f);self.assertEqual(f['drinks_media']['generated_limit'],2)
 def test_rejects_incomplete_recipe_wrong_bindings_sources_and_alcohol(self):
  for mutate in [lambda l:l['recipe']['ingredients'][0].update(amount=0),lambda l:l['recipe']['ingredients'][0].update(contains_alcohol=True),lambda l:l['recipe']['steps'][0].update(ingredient_ids=['unknown']),lambda l:l['photos'][0].update(entry_id='unknown'),lambda l:l.update(science_focus_id='unknown'),lambda l:l['origin'].update(source_ids=['unknown']),lambda l:l['recipe']['ingredients'][0].update(contains_alcohol=1)]:
   f=fixture();mutate(f['drinks_lesson']);self.assertFalse(validate_drinks_content(f))
 def test_fallback_is_nonempty_bounded_multi_section_and_preserves_model_plan(self):
  f=fixture();f['drinks_lesson']['photos']=[];self.assertTrue(ensure_drinks_photo_plan(f));self.assertTrue(validate_drinks_content(f));plan=f['drinks_lesson']['photos']
  self.assertGreaterEqual(len({p['section_id'] for p in plan}),3);self.assertFalse(ensure_drinks_photo_plan(f));self.assertIs(plan,f['drinks_lesson']['photos'])
class DrinksAsyncTests(unittest.IsolatedAsyncioTestCase):
 async def test_generator_selects_drinks_contract_and_repairs_empty_photo_plan(self):
  r=generator_module();f=fixture();f['drinks_lesson']['photos']=[];r.genai.Client.return_value.aio.models.generate_content=AsyncMock(return_value=types.SimpleNamespace(parsed=f))
  result=await r.generate_daily_fact('drinks',[]);self.assertIsNotNone(result);self.assertEqual(result['drinks_media']['generated_limit'],3)
  self.assertTrue(result['drinks_lesson']['photos']);self.assertIn('wine',r.genai.Client.return_value.aio.models.generate_content.call_args.kwargs['contents'])
 async def test_ranker_includes_exact_request_context(self):
  f=fixture();request=f['drinks_lesson']['photos'][0];p=photo();payload={'selected':[dict(photo_id=p['provider_id'],score=95,scene=request['id'],reason='Matches the drink.')],'retry_queries':[]}
  create=AsyncMock(return_value=types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps(payload)))]));client=types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
  result=await rank_photos(f,[p],client=client);self.assertEqual(result[0]['drinks_request_ids'],[request['id']]);self.assertIn('Wikimedia',create.call_args.kwargs['messages'][0]['content'])
 async def test_four_queries_are_searched_and_commons_is_preferred(self):
  f=fixture();f['drinks_lesson']['photos']=f['drinks_lesson']['photos'][:1];p=f['drinks_lesson']['photos'][0];p['queries']=['mojito','mojito glass','mojito mint','mojito ingredients']
  commons=AsyncMock(return_value=[photo()]);fetch=AsyncMock(return_value=[])
  rank=AsyncMock(return_value=[{**stock(1),'drinks_request_ids':[p['id']]},{**photo(),'drinks_request_ids':[p['id']]}])
  result=await select_drinks_photos(f,commons=commons,fetch=fetch,rank=rank);self.assertEqual(commons.await_count,4);self.assertEqual(result[0]['provider'],'wikimedia')
 async def test_worker_binds_each_entry_and_limits_generated_images(self):
  r=routes_module();f=fixture();p=next(p for p in f['drinks_lesson']['photos'] if p['section_id']=='ingredients');index=f['drinks_lesson']['photos'].index(p)
  r.generate_and_save_image=AsyncMock(return_value='https://example.org/illustration');r.select_drinks_photos=AsyncMock(return_value=[{**photo(),'drinks_request_ids':[p['id']]}])
  await r._background_image_task({**f['visual_suggestions'],'explanation_2':'extra'},'hash',article=f)
  self.assertEqual(r.generate_and_save_image.await_count,3);credit=next(c.kwargs['credit'] for c in r.set_fact_image_state.call_args_list if c.args[1]==f'drinks_photo_{index}' and c.kwargs.get('credit'))
  self.assertEqual(credit['entry_id'],p['entry_id']);self.assertEqual(credit['section_id'],'ingredients')
 async def test_photo_only_retry_saves_missing_plan_and_keeps_ready_photos(self):
  r=routes_module();f=fixture();f['drinks_lesson']['photos']=[];r.get_fact_by_hash.return_value={'full_response':f,'images':{'cover':'https://example.org/cover'}};bg=Mock()
  await r.retry_image_generation(Mock(),bg,'hash',photos_only=True);r.save_drinks_photo_plan.assert_called_once();args=bg.add_task.call_args;await args.args[0](*args.args[1:],**args.kwargs);r.generate_and_save_image.assert_not_awaited()
 async def test_recovery_is_single_round_and_popular_photos_are_tail_only(self):
  f=fixture();p=f['drinks_lesson']['photos'][0];raw=[{**stock(i),'likes':i} for i in range(3)]
  rank=AsyncMock(side_effect=[PhotoRankingResult([], [{'scene':p['id'],'query':'mint drink'}]),[{**photo(),'drinks_request_ids':[p['id']]}]])
  result=await select_drinks_photos(f,fetch=AsyncMock(return_value=raw),commons=AsyncMock(return_value=[photo()]),rank=rank)
  self.assertEqual(rank.await_count,2);self.assertTrue(all(v['popular_pick'] and v['drinks_request_ids']==[] for v in result[-3:]))
 async def test_named_subjects_are_commons_only(self):
  f=fixture();f['drinks_lesson']['photos']=f['drinks_lesson']['photos'][:1];p=f['drinks_lesson']['photos'][0];p['kind']='named_place';fetch=AsyncMock();commons=AsyncMock(return_value=[])
  await select_drinks_photos(f,fetch=fetch,commons=commons,rank=AsyncMock(return_value=[]));fetch.assert_not_awaited()
