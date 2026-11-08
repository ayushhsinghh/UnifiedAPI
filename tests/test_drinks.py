import json,sys,types,unittest
from pathlib import Path
from unittest.mock import AsyncMock,Mock
APP=Path(__file__).resolve().parents[1]/'app';sys.path.insert(0,str(APP))
pkg=types.ModuleType('src.facts');pkg.__path__=[str(APP/'src/facts')];sys.modules.setdefault('src.facts',pkg)
from src.facts.drinks import validate_drinks_content,ensure_drinks_photo_plan,prepare_drinks_media,DRINKS_LESSON_SCHEMA,build_drinks_prompt
from src.facts.photo_ranking import select_drinks_photos,rank_photos,PhotoRankingResult
from src.facts.lifecycle import fact_image_keys
from test_fact_evidence_lifecycle import routes_module,generator_module
from test_agriculture import photo
from test_photo_ranking import photo as stock

def fixture():return json.loads((Path(__file__).parent/'fixtures/drinks_lesson.json').read_text())
def fixture_v2():return json.loads((Path(__file__).parent/'fixtures/drinks_lesson_v2.json').read_text())
def fixture_v3():return json.loads((Path(__file__).parent/'fixtures/drinks_lesson_v3.json').read_text())
class DrinksTests(unittest.TestCase):
 def test_popular_pixabay_score_uses_all_three_metrics_and_keeps_provider_picks_at_end(self):
  from src.facts.photo_ranking import PopularDrinksPhotos
  bank=PopularDrinksPhotos()
  candidates=[{**stock(i),'likes':i} for i in range(5)]
  for i in range(5):
   candidates.append({**stock(20+i),'provider':'pixabay','provider_id':'pixabay_'+str(i),
    'source_url':'https://pixabay.com/photos/'+str(i),'likes':100-i,'views':i*1000,'downloads':i*100})
  bank.add(candidates[:6]);bank.add(candidates[6:])
  result=bank.include([candidates[0]],request_key='drinks_request_ids',limit=12)
  self.assertFalse(result[0].get('popular_pick'))
  self.assertEqual([p['provider_id'] for p in result[-3:]],['pixabay_4','pixabay_3','pixabay_2'])
  self.assertTrue(all(p['selection_mode']=='popular_pixabay' and p['ranking_model'] is None and p['drinks_request_ids']==[] for p in result[-3:]))
  self.assertEqual(len({p['source_url'] for p in result}),len(result))
  self.assertEqual(len(bank.photos),6)
 def test_partial_photo_plan_repairs_missing_method_bindings_without_replacing_queries(self):
  f=fixture_v3();l=f['drinks_lesson']
  l['photos']=[p for p in l['photos'] if p['section_id']!='method']
  retained=json.loads(json.dumps(l['photos']))
  self.assertTrue(ensure_drinks_photo_plan(f));self.assertTrue(validate_drinks_content(f))
  self.assertEqual(l['photos'][:len(retained)],retained)
  self.assertEqual({p['id'] for p in l['making']['stages']},{p['entry_id'] for p in l['photos'] if p['section_id']=='method'})
  self.assertEqual(f['drinks_media']['photo_plan_source'],'repaired')
  self.assertFalse(ensure_drinks_photo_plan(f))
 def test_full_photo_plan_reserves_missing_bindings_with_unique_request_ids(self):
  f=fixture_v3();l=f['drinks_lesson']
  l['photos']=[p for p in l['photos'] if p['section_id']!='method']
  p=l['photos'][0]
  while len(l['photos'])<30:l['photos'].append({**p,'id':'fallback_'+str(len(l['photos']))})
  self.assertTrue(ensure_drinks_photo_plan(f));self.assertTrue(validate_drinks_content(f))
  self.assertEqual(len(l['photos']),30)
  self.assertEqual(len({p['id'] for p in l['photos']}),30)
  self.assertFalse(ensure_drinks_photo_plan(f))
 def test_provider_schema_has_no_numeric_enums_and_keeps_integer_version(self):
  from src.facts.drinks import DRINKS_RESPONSE_SCHEMA,VERSION2_DRINKS_RESPONSE_SCHEMA
  def check(schema):
   self.assertTrue(all(isinstance(v,str) for v in schema.get('enum',[])))
   for child in schema.get('properties',{}).values():check(child)
   if 'items' in schema:check(schema['items'])
  for schema in (DRINKS_RESPONSE_SCHEMA,VERSION2_DRINKS_RESPONSE_SCHEMA):check(schema)
  self.assertEqual(DRINKS_LESSON_SCHEMA['properties']['content_version']['type'],'INTEGER')
  f=fixture_v3();f['drinks_lesson']['content_version']=4
  self.assertFalse(validate_drinks_content(f))
 def test_validation_reports_field_paths_and_semantic_rules(self):
  f=fixture_v3();del f['drinks_lesson']['opening']['introduction'];errors=[]
  self.assertFalse(validate_drinks_content(f,errors=errors))
  self.assertIn('$.drinks_lesson.opening.introduction',errors[0])
  f=fixture_v3();f['drinks_lesson']['recipe']['steps'][0]['ingredient_ids']=['missing'];errors=[]
  self.assertFalse(validate_drinks_content(f,errors=errors))
  self.assertIn('ingredient references',errors[0])
 def test_third_edition_has_distinct_content_and_one_science_image(self):
  f=fixture_v3();self.assertTrue(validate_drinks_content(f));prepare_drinks_media(f)
  self.assertEqual(f['drinks_media']['version'],3);self.assertEqual(f['drinks_media']['generated_limit'],3)
  l=f['drinks_lesson'];self.assertEqual(len(l['explore_drinks']),6);self.assertEqual(len(l['science']),1)
  self.assertNotIn('production_evolution',l);self.assertNotIn('introduction',l)
  for mutate in [lambda l:l['making']['stages'][0].update(id='missing'),lambda l:l['making'].update(evolution_kind='progress'),lambda l:l['explore_drinks'][0].update(source_ids=['missing']),lambda l:l['explore_drinks'][0].update(relationship='descendant'),lambda l:l['explore_drinks'][1].update(name=l['explore_drinks'][0]['name']),lambda l:l['photos'][0].update(entry_id='missing')]:
   bad=fixture_v3();mutate(bad['drinks_lesson']);self.assertFalse(validate_drinks_content(bad))
 def test_third_edition_repairs_photos_for_every_ingredient_stage_and_related_drink(self):
  f=fixture_v3();f['drinks_lesson']['photos']=[];self.assertTrue(ensure_drinks_photo_plan(f));self.assertTrue(validate_drinks_content(f))
  l=f['drinks_lesson']
  for section,records in [('ingredients',l['ingredients']),('method',l['making']['stages']),('explore',l['explore_drinks'])]:
   self.assertEqual({p['id'] for p in records},{p['entry_id'] for p in l['photos'] if p['section_id']==section})
  p=l['photos'][0]
  while len(l['photos'])<30:l['photos'].append({**p,'id':'extra_'+str(len(l['photos']))})
  self.assertTrue(validate_drinks_content(f));self.assertIn('drinks_photo_29',fact_image_keys(f))
  l['photos'].append({**p,'id':'overflow'});self.assertFalse(validate_drinks_content(f))
 def test_optional_editorial_notes_do_not_require_filler_or_break_saved_lessons(self):
  for factory in (fixture,fixture_v2):
   for value in (None,'omitted'):
    f=factory();l=f['drinks_lesson']
    blocks=[(l['identity'],'strength_context'),(l['origin'],'evidence_and_uncertainty'),*[(p,'limits') for p in l['science']],*[(p,'evidence_and_uncertainty') for p in l['variations']]]
    for block,key in blocks:
     if value=='omitted':block.pop(key,None)
     else:block[key]=value
    self.assertTrue(validate_drinks_content(f))
   bad=factory();bad['drinks_lesson']['science'][0]['limits']=123;self.assertFalse(validate_drinks_content(bad))
  for block,key in [(DRINKS_LESSON_SCHEMA['properties']['origin'],'evidence_and_uncertainty'),(DRINKS_LESSON_SCHEMA['properties']['science']['items'],'limits')]:
   self.assertNotIn(key,block['required']);self.assertTrue(block['properties'][key]['nullable'])
 def test_editorial_prompt_preserves_accuracy_and_visible_preparation_cautions(self):
  prompt=build_drinks_prompt([])
  self.assertIn('Omit them or return null',prompt)
  self.assertIn('Do not hide relevant uncertainty or make unsupported positive claims',prompt)
  self.assertIn('Keep actual allergen, alcohol-content and preparation cautions',prompt)
  self.assertIn('keep the primary India recipe alcoholic',prompt)
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
 async def test_pixabay_fallback_survives_ranking_rejection_and_candidate_cap(self):
  unsplash=[{**stock(i),'likes':i} for i in range(250)]
  pix=[{**stock(300+i),'provider':'pixabay','provider_id':'pixabay_'+str(i),
   'source_url':'https://pixabay.com/photos/'+str(i),'likes':1,'views':100+i,'downloads':10+i} for i in range(5)]
  result=await select_drinks_photos(fixture_v3(),commons=AsyncMock(return_value=[]),
   fetch=AsyncMock(return_value=unsplash+pix),rank=AsyncMock(return_value=PhotoRankingResult()))
  self.assertEqual(len(result),6)
  self.assertEqual([p['provider_id'] for p in result[-3:]],['pixabay_4','pixabay_3','pixabay_2'])
  self.assertTrue(all(p['popular_pick'] and p['drinks_gallery_only'] for p in result))
 async def test_pixabay_popular_fallback_publishes_at_end_of_same_drinks_gallery(self):
  from unittest.mock import patch
  from src.facts.photo_ranking import PopularDrinksPhotos
  r=routes_module();r.track_selection=AsyncMock(return_value=True)
  bank=PopularDrinksPhotos();pix=[]
  for i in range(3):
   pix.append({**stock(20+i),'provider':'pixabay','provider_id':'pixabay_'+str(i),
    'source_url':'https://pixabay.com/photos/'+str(i),'likes':i+1,'views':100*i,'downloads':10*i})
  bank.add([{**stock(i),'likes':i} for i in range(3)]+pix)
  ranked=[{**stock(100+i),'drinks_gallery_only':True} for i in range(10)]
  r.select_drinks_photos=AsyncMock(return_value=bank.include(ranked,request_key='drinks_request_ids'))
  persist=AsyncMock(side_effect=lambda p:'https://objectstorage.ap-mumbai-1.oraclecloud.com/photos/'+p['provider_id'])
  with patch('src.facts.pixabay_photos.persist_selected',new=persist):
   await r._background_image_task({},'hash',article=fixture_v3(),photos_only=True)
  ready=[c for c in r.set_fact_image_state.call_args_list if c.args[2]=='ready' and c.args[1].startswith('drinks_scene_')]
  credits=[c.kwargs['credit'] for c in ready]
  self.assertEqual(len(credits),12)
  self.assertTrue(all(not p.get('popular_pick') for p in credits[:6]))
  self.assertTrue(all(p['popular_pick'] for p in credits[-6:]))
  self.assertTrue(all(p['selection_mode']=='popular_pixabay' and p['ranking_model'] is None for p in credits[-3:]))
  self.assertEqual(persist.await_count,3)
 async def test_gemini_drinks_json_mode_repairs_partial_plan_and_validates_content(self):
  r=generator_module();f=fixture_v3()
  f['drinks_lesson']['photos']=[p for p in f['drinks_lesson']['photos'] if p['section_id']!='method']
  generate=AsyncMock(return_value=types.SimpleNamespace(parsed=None,text=json.dumps(f)))
  r.genai.Client.return_value.aio.models.generate_content=generate
  result=await r.generate_daily_fact('drinks',[])
  self.assertIsNotNone(result);self.assertTrue(validate_drinks_content(result))
  request=generate.call_args.kwargs
  self.assertNotIn('response_schema',request['config'])
  self.assertEqual(request['config']['response_mime_type'],'application/json')
  self.assertIn('"drinks_lesson"',request['contents'])
  self.assertIn('"content_version"',request['contents'])
 async def test_openai_valid_article_survives_missing_method_photo_bindings(self):
  from unittest.mock import patch
  r=generator_module();f=fixture_v3()
  f['drinks_lesson']['photos']=[p for p in f['drinks_lesson']['photos'] if p['section_id']!='method']
  r.genai.Client.return_value.aio.models.generate_content=AsyncMock(side_effect=ValueError('provider unavailable'))
  response=types.SimpleNamespace(choices=[types.SimpleNamespace(finish_reason='stop',message=types.SimpleNamespace(content=json.dumps(f),refusal=None))])
  r.openai.AsyncOpenAI.return_value.chat.completions.create=AsyncMock(return_value=response)
  with patch.object(r.asyncio,'sleep',new=AsyncMock()):
   result=await r.generate_daily_fact('drinks',[])
  self.assertIsNotNone(result);self.assertTrue(validate_drinks_content(result))
 async def test_openai_incomplete_response_is_not_accepted_as_a_fact(self):
  from unittest.mock import patch
  r=generator_module()
  r.genai.Client.return_value.aio.models.generate_content=AsyncMock(side_effect=ValueError('old schema failure'))
  response=types.SimpleNamespace(choices=[types.SimpleNamespace(finish_reason='length',message=types.SimpleNamespace(content=json.dumps(fixture_v3()),refusal=None))])
  r.openai.AsyncOpenAI.return_value.chat.completions.create=AsyncMock(return_value=response)
  with patch.object(r.asyncio,'sleep',new=AsyncMock()):
   self.assertIsNone(await r.generate_daily_fact('drinks',[]))
  self.assertIn('finish_reason=length',str(r.logger.warning.call_args.args[-1]))
 async def test_openai_rejection_replaces_prior_gemini_exception(self):
  from unittest.mock import patch
  r=generator_module()
  import logging
  r.logger=logging.getLogger('drinks_validation_regression')
  r.genai.Client.return_value.aio.models.generate_content=AsyncMock(side_effect=ValueError('old Gemini schema error'))
  bad=fixture_v3();del bad['drinks_lesson']['opening']['introduction']
  response=types.SimpleNamespace(choices=[types.SimpleNamespace(finish_reason='stop',message=types.SimpleNamespace(content=json.dumps(bad)))])
  r.openai.AsyncOpenAI.return_value.chat.completions.create=AsyncMock(return_value=response)
  with patch.object(r.asyncio,'sleep',new=AsyncMock()),self.assertLogs(r.logger,level='WARNING') as logs:
   self.assertIsNone(await r.generate_daily_fact('drinks',[]))
  self.assertIn('$.drinks_lesson.opening.introduction',logs.output[-1])
  self.assertNotIn('old Gemini schema error',logs.output[-1])
  self.assertTrue(any('finish_reason=stop' in line for line in logs.output))
 async def test_third_edition_ranker_accepts_thirty_metadata_matches(self):
  f=fixture_v3();request=f['drinks_lesson']['photos'][0]['id'];photos=[photo(i) for i in range(30)]
  payload={'selected':[dict(photo_id=p['provider_id'],score=90,scene=request,reason='Metadata matches the requested subject.') for p in photos],'retry_queries':[]}
  create=AsyncMock(return_value=types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps(payload)))]))
  result=await rank_photos(f,photos,client=types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create))))
  self.assertEqual(len(result),30)
 async def test_third_edition_generation_uses_new_contract_without_paid_calls(self):
  r=generator_module();r.genai.Client.return_value.aio.models.generate_content=AsyncMock(return_value=types.SimpleNamespace(parsed=fixture_v3()))
  f=await r.generate_daily_fact('drinks',[]);self.assertIsNotNone(f);self.assertEqual(f['drinks_media']['generated_limit'],3)
  self.assertEqual(f['drinks_lesson']['content_version'],3)
 async def test_third_edition_selects_thirty_commons_without_stock_consuming_slots(self):
  f=fixture_v3();request=f['drinks_lesson']['photos'][0]['id']
  async def rank(fact,pool,**kwargs):return [{**p,'drinks_request_ids':[request]} for p in pool]
  commons=AsyncMock(return_value=[photo(i) for i in range(30)]);stock_fetch=AsyncMock(return_value=[stock(1)])
  selected=await select_drinks_photos(f,commons=commons,fetch=stock_fetch,rank=rank)
  self.assertEqual(len([p for p in selected if p.get('provider')=='wikimedia']),30)
  self.assertTrue(any(p.get('drinks_gallery_only') for p in selected))
  queries={q.casefold() for p in f['drinks_lesson']['photos'] for q in p['queries']}
  self.assertEqual(commons.await_count,len(queries))
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
