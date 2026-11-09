"""Offline Culture contract, generation, media isolation and retry checks."""
import json,sys,types,unittest
from pathlib import Path
from unittest.mock import AsyncMock,Mock
APP=Path(__file__).resolve().parents[1]/'app';sys.path.insert(0,str(APP))
pkg=types.ModuleType('src.facts');pkg.__path__=[str(APP/'src/facts')];sys.modules.setdefault('src.facts',pkg)
from src.facts.culture import validate_culture_content,ensure_culture_photo_plan,prepare_culture_media,build_culture_prompt
from src.facts.lifecycle import fact_image_keys,image_generation_state
from src.facts.image_policy import validate_image_plan
from src.facts.photo_ranking import select_culture_photos,PhotoRankingResult
from src.facts.visual_prompts import build_section_image_context
from test_fact_evidence_lifecycle import generator_module,routes_module,load,config_import,module
from test_agriculture import photo
from test_photo_ranking import photo as stock

def fixture():return json.loads((Path(__file__).parent/'fixtures/culture_lesson.json').read_text())

class CultureTests(unittest.TestCase):
 def test_repaired_plan_save_compares_previous_plan_without_changing_text_or_images(self):
  collection=Mock();collection.update_one.return_value.matched_count=1
  repo=load('culture_repo_test','src/database/facts_repository.py',{**config_import,
   'pymongo.errors':module('pymongo.errors',DuplicateKeyError=RuntimeError),
   'src.database.connection':module('src.database.connection',get_db=lambda:{'facts':collection})})
  f=fixture();previous=f['culture_lesson']['photos'][:2]
  self.assertTrue(repo.save_culture_photo_plan('hash',f,previous_photos=previous))
  query,update=collection.update_one.call_args.args
  self.assertEqual(query['full_response.culture_lesson.photos'],previous)
  self.assertEqual(set(update['$set']),{'full_response.culture_lesson.photos','full_response.culture_media.photo_plan_version','full_response.culture_media.photo_plan_source'})
  collection.update_one.return_value.matched_count=0
  self.assertFalse(repo.save_culture_photo_plan('hash',f,previous_photos=previous))
 def test_contract_has_all_learning_sections_and_exactly_three_ai_slots(self):
  f=fixture();self.assertTrue(validate_culture_content(f));self.assertTrue(validate_image_plan(f))
  prepare_culture_media(f);self.assertEqual(f['culture_media']['generated_slots'],['cover','overview','how_it_works'])
  self.assertEqual(f['visual_suggestions']['how_it_works'],f['culture_lesson']['why_custom']['infographic_prompt'])
  self.assertEqual(len(fact_image_keys(f)),3+len(f['culture_lesson']['photos'])+12)
  self.assertEqual(image_generation_state({'full_response':f},30)['timeout_seconds'],720)
 def test_rejects_missing_markers_invalid_sources_and_photo_references(self):
  for mutate in [lambda l:l['markers'].pop(),lambda l:l['opening'].update(source_ids=['missing']),lambda l:l['photos'][0].update(entry_id='missing'),lambda l:l['india_connections']['connections'][0].update(relationship='same_culture'),lambda l:l.update(content_version=2),lambda l:l['why_custom'].update(drivers=[]),lambda l:l['daily_life'].update(comparisons=[])]:
   f=fixture();mutate(f['culture_lesson']);self.assertFalse(validate_culture_content(f))
 def test_repairs_partial_photo_bindings_and_is_idempotent(self):
  f=fixture();l=f['culture_lesson'];l['photos']=[p for p in l['photos'] if p['section_id']!='markers'];retained=list(l['photos'])
  self.assertTrue(ensure_culture_photo_plan(f));self.assertEqual(l['photos'][:len(retained)],retained)
  self.assertTrue(validate_culture_content(f));self.assertFalse(ensure_culture_photo_plan(f))
  l['photos']=[];self.assertTrue(ensure_culture_photo_plan(f));self.assertTrue(validate_culture_content(f))
 def test_no_forced_india_contact_and_diagram_labels_are_supported(self):
  f=fixture();f['culture_lesson']['india_connections']['connections']=[]
  f['culture_lesson']['photos']=[p for p in f['culture_lesson']['photos'] if p['section_id']!='india']
  self.assertTrue(validate_culture_content(f))
  context=build_section_image_context('how_it_works',f)
  self.assertIn('short accurate educational labels',context)
  self.assertIn('shared',context.lower())
  prompt=build_culture_prompt([])
  self.assertIn('comparison',prompt);self.assertIn('not proof of historical contact',prompt)

class CultureAsyncTests(unittest.IsolatedAsyncioTestCase):
 async def test_photo_retry_persists_partial_plan_and_preserves_ready_assets(self):
  r=routes_module();f=fixture();f['culture_lesson']['photos']=f['culture_lesson']['photos'][:2]
  ready={'cover':'https://example.org/cover','culture_photo_0':'https://example.org/ready'}
  r.get_fact_by_hash.return_value={'full_response':f,'images':ready}
  bg=Mock();await r.retry_image_generation(Mock(),bg,'hash',photos_only=True)
  r.save_culture_photo_plan.assert_called_once()
  self.assertEqual(r.save_culture_photo_plan.call_args.kwargs['previous_photos'],f['culture_lesson']['photos'])
  self.assertTrue(all(key.startswith(('culture_photo_','culture_scene_')) for key in r.start_fact_images.call_args.args[1]))
  args=bg.add_task.call_args
  await args.args[0](*args.args[1:],**args.kwargs)
  r.generate_and_save_image.assert_not_awaited()
  self.assertFalse(any(c.args[1] in ready and c.args[2]=='not_requested' for c in r.set_fact_image_state.call_args_list))
 async def test_worker_generates_only_cover_overview_and_explanation(self):
  r=routes_module();f=fixture()
  await r._background_image_task(f['visual_suggestions'],'hash',article=f)
  self.assertEqual(r.generate_and_save_image.await_count,3)
  prompts=[c.args[0] for c in r.generate_and_save_image.await_args_list]
  self.assertIn(f['visual_suggestions']['how_it_works'],prompts)
 async def test_gemini_json_mode_generates_and_prepares_culture(self):
  r=generator_module();generate=AsyncMock(return_value=types.SimpleNamespace(parsed=None,text=json.dumps(fixture())))
  r.genai.Client.return_value.aio.models.generate_content=generate
  f=await r.generate_daily_fact('culture',[]);self.assertIsNotNone(f)
  self.assertEqual(f['culture_media']['generated_limit'],3)
  self.assertNotIn('response_schema',generate.call_args.kwargs['config'])
  self.assertIn('culture_lesson',generate.call_args.kwargs['contents'])
 async def test_section_and_stock_pools_are_independent(self):
  f=fixture();commons=AsyncMock(return_value=[photo(1)]);fetch=AsyncMock(return_value=[stock(1)])
  async def rank(fact,photos,**kwargs):
   return PhotoRankingResult([{**p,'culture_request_ids':[fact['culture_lesson']['photos'][0]['id']]} for p in photos])
  chosen=await select_culture_photos(f,commons=commons,fetch=fetch,rank=rank)
  self.assertTrue(commons.await_count>0);self.assertTrue(fetch.await_count>0)
  self.assertTrue(any(p.get('provider')=='wikimedia' and not p.get('culture_gallery_only') for p in chosen))
  self.assertTrue(any(p.get('provider')=='unsplash' and p.get('culture_gallery_only') and p['culture_request_ids']==[] for p in chosen))
 async def test_worker_keeps_stock_in_carousel_and_binds_commons_to_section(self):
  r=routes_module();r.track_selection=AsyncMock(return_value=True)
  f=fixture();p=f['culture_lesson']['photos'][0]
  r.select_culture_photos=AsyncMock(return_value=[{**photo(1),'culture_request_ids':[p['id']]},{**stock(1),'culture_gallery_only':True,'culture_request_ids':[]}])
  await r._background_image_task({},'hash',article=f,photos_only=True)
  ready=[c for c in r.set_fact_image_state.call_args_list if c.args[2]=='ready']
  self.assertEqual({c.args[1] for c in ready},{'culture_photo_0','culture_scene_0'})
  self.assertTrue(all(c.kwargs['credit']['provider']=='wikimedia' for c in ready if c.args[1].startswith('culture_photo_')))
