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
def fixture_v2():return json.loads((Path(__file__).parent/'fixtures/drinks_lesson_v2.json').read_text())
class DrinksTests(unittest.TestCase):
 def test_opening_hook_requires_complete_fields_and_resolving_sources(self):
  f=fixture_v2();self.assertTrue(validate_drinks_content(f))
  f['drinks_lesson']['opening_hook']={'heading':'Why does this glass lose its fizz?','introduction':'A Mojito combines citrus, mint and soda.','intriguing_detail':'Soda releases dissolved carbon dioxide after opening.','bridge_question':'How does gentle mixing help preserve bubbles?','source_ids':[f['sources'][0]['id']]}
  self.assertTrue(validate_drinks_content(f))
  f['drinks_lesson']['opening_hook']['source_ids']=['missing'];self.assertFalse(validate_drinks_content(f))
  f['drinks_lesson']['opening_hook']['source_ids']=[f['sources'][0]['id']]
  del f['drinks_lesson']['opening_hook']['bridge_question'];self.assertFalse(validate_drinks_content(f))
 def test_second_edition_requires_section_searches_and_three_generated_images(self):
  f=fixture_v2();self.assertTrue(validate_drinks_content(f));prepare_drinks_media(f)
  self.assertEqual(f['drinks_media']['generated_slots'],['cover','overview','how_it_works'])
  self.assertTrue({'cover','overview','how_it_works'}<=set(fact_image_keys(f)))
  for mutate in [lambda x:x['visual_suggestions'].update(cover=None),lambda x:x['drinks_lesson']['photos'].pop(),lambda x:x['drinks_lesson']['photos'][0].update(queries=['one']),lambda x:x['drinks_lesson']['production_evolution']['modern'].update(steps=[]),lambda x:x['drinks_lesson'].update(science_focus_id=None)]:
   bad=fixture_v2();mutate(bad);self.assertFalse(validate_drinks_content(bad))
  f=fixture_v2();f['drinks_lesson']['photos']=[];self.assertTrue(ensure_drinks_photo_plan(f));self.assertTrue(validate_drinks_content(f))
 def test_science_diagram_context_allows_educational_labels(self):
  from src.facts.visual_prompts import build_section_image_context
  context=build_section_image_context('how_it_works',fixture_v2())
  self.assertIn('short accurate educational labels',context);self.assertNotIn('Include no text',context)
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
 async def test_new_edition_searches_commons_sections_and_separate_stock_gallery(self):
  f=fixture_v2();commons=AsyncMock(return_value=[]);fetch=AsyncMock(return_value=[])
  await select_drinks_photos(f,commons=commons,fetch=fetch,rank=AsyncMock(return_value=[]))
  self.assertEqual(commons.await_count,16);self.assertEqual(fetch.await_count,12)
 async def test_new_gallery_is_ranked_separately_and_cannot_bind_inline(self):
  f=fixture_v2();request=f['drinks_lesson']['photos'][0]['id']
  async def rank(fact,pool,**kwargs):
   return [{**p,'drinks_request_ids':[request],'ranking_score':90} for p in pool]
  pixabay={**stock(2),'provider':'pixabay','provider_id':'pixabay:2'}
  result=await select_drinks_photos(f,commons=AsyncMock(return_value=[photo()]),fetch=AsyncMock(return_value=[stock(1),pixabay]),rank=rank)
  sections=[p for p in result if not p.get('drinks_gallery_only')]
  gallery=[p for p in result if p.get('drinks_gallery_only')]
  self.assertEqual({p['provider'] for p in sections},{'wikimedia'})
  self.assertEqual({p['provider'] for p in gallery},{'unsplash','pixabay'})
  self.assertTrue(all(p['drinks_request_ids']==[] for p in gallery))
 async def test_failed_commons_search_does_not_remove_stock_gallery(self):
  f=fixture_v2();request=f['drinks_lesson']['photos'][0]['id']
  async def rank(fact,pool,**kwargs):return [{**p,'drinks_request_ids':[request]} for p in pool]
  result=await select_drinks_photos(f,commons=AsyncMock(side_effect=TimeoutError),fetch=AsyncMock(return_value=[stock(1)]),rank=rank)
  self.assertTrue(result);self.assertTrue(all(p.get('drinks_gallery_only') for p in result))
 async def test_worker_stores_stock_only_in_carousel_and_commons_only_inline(self):
  r=routes_module();f=fixture_v2();request=f['drinks_lesson']['photos'][0]['id']
  r.select_drinks_photos=AsyncMock(return_value=[{**photo(),'drinks_request_ids':[request]},{**stock(1),'drinks_request_ids':[request],'drinks_gallery_only':True}])
  await r._background_image_task(f['visual_suggestions'],'hash',article=f,photos_only=True)
  ready={c.args[1]:c.kwargs['credit'] for c in r.set_fact_image_state.call_args_list if c.args[2]=='ready'}
  self.assertEqual(ready['drinks_photo_0']['provider'],'wikimedia')
  self.assertEqual(ready['drinks_scene_0']['provider'],'unsplash')
  self.assertTrue(ready['drinks_scene_0']['drinks_carousel'])
  r.generate_and_save_image.assert_not_awaited()
 async def test_new_worker_generates_cover_overview_science_without_photo_overwrite(self):
  r=routes_module();f=fixture_v2();p=f['drinks_lesson']['photos'][0]
  r.generate_and_save_image=AsyncMock(return_value='https://example.org/diagram')
  r.select_drinks_photos=AsyncMock(return_value=[{**photo(),'drinks_request_ids':[p['id']]}])
  await r._background_image_task(f['visual_suggestions'],'hash',article=f)
  self.assertEqual(r.generate_and_save_image.await_count,3)
  for key in ('cover','overview'):
   calls=[c for c in r.set_fact_image_state.call_args_list if c.args[1]==key and c.args[2]=='ready']
   self.assertEqual(len(calls),1);self.assertEqual(calls[0].args[3],'https://example.org/diagram')
 async def test_photo_retry_never_changes_generated_cover_or_overview(self):
  r=routes_module();f=fixture_v2();f['image_credits']={'drinks_photo_0':photo()}
  r.select_drinks_photos=AsyncMock(return_value=[])
  await r._background_image_task(f['visual_suggestions'],'hash',existing_images={'drinks_photo_0':photo()['url']},article=f,photos_only=True)
  r.generate_and_save_image.assert_not_awaited()
  for key in ('cover','overview'):
   self.assertFalse(any(c.args[1]==key for c in r.set_fact_image_state.call_args_list))
   self.assertFalse(any(c.args[1]==key and c.args[2]=='not_requested' for c in r.set_fact_image_state.call_args_list))
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
