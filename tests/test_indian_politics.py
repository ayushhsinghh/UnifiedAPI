"""Offline Politics chronology, evidence, photo binding and generation regression checks."""
import json,sys,types,unittest
from pathlib import Path
from unittest.mock import AsyncMock,Mock
APP=Path(__file__).resolve().parents[1]/'app';sys.path.insert(0,str(APP))
pkg=types.ModuleType('src.facts');pkg.__path__=[str(APP/'src/facts')];sys.modules.setdefault('src.facts',pkg)
from src.facts.indian_politics import validate_politics_content,valid_politics_date,ensure_politics_photo_plan,prepare_politics_media,build_politics_prompt
from src.facts.lifecycle import fact_image_keys,image_generation_state
from src.facts.image_policy import validate_image_plan
from src.facts.photo_ranking import select_politics_photos,PhotoRankingResult
from src.facts.visual_prompts import build_section_image_context
from test_fact_evidence_lifecycle import generator_module,routes_module,load,config_import,module
from test_agriculture import photo
from test_photo_ranking import photo as stock
def fixture():return json.loads((Path(__file__).parent/'fixtures/indian_politics_lesson.json').read_text())
class PoliticsTests(unittest.TestCase):
 def test_contract_and_exact_three_ai_slots(self):
  f=fixture();self.assertTrue(validate_politics_content(f));self.assertTrue(validate_image_plan(f))
  prepare_politics_media(f);self.assertEqual(f['indian_politics_media']['generated_limit'],3)
  self.assertEqual(f['visual_suggestions']['how_it_works'],f['indian_politics_lesson']['diagram_prompt'])
  self.assertEqual(len(fact_image_keys(f)),3+len(f['indian_politics_lesson']['photos'])+12)
  self.assertEqual(image_generation_state({'full_response':f},30)['timeout_seconds'],720)
 def test_rejects_broken_references_and_dates(self):
  for mutate in [lambda l:l['process']['steps'][0].update(actor_ids=['unknown']),lambda l:l['process']['steps'][0].update(rule_ids=['unknown']),lambda l:l['worked_example']['steps'][0].update(process_step_id='unknown'),lambda l:l['actors'][0].update(source_ids=['unknown']),lambda l:l['photos'][0].update(entry_id='unknown'),lambda l:l['worked_example'].update(date='2024-01-01'),lambda l:l['worked_example'].update(kind='dated_real'),lambda l:l['identity'].update(as_of='9999-01-01')]:
   f=fixture();mutate(f['indian_politics_lesson']);self.assertFalse(validate_politics_content(f))
 def test_calendar_bounds(self):
  self.assertTrue(valid_politics_date('2024-02-29'))
  for p in ('2023-02-29','9999-01-01','2024-2-01',None):self.assertFalse(valid_politics_date(p))
 def test_sparse_chronology_does_not_force_invented_dates(self):
  f=fixture();self.assertEqual(f['indian_politics_lesson']['changes'],[]);self.assertTrue(validate_politics_content(f))
  self.assertIn('No forced chronology',build_politics_prompt([]))
 def test_real_examples_and_changes_share_a_bounded_context_date(self):
  f=fixture();l=f['indian_politics_lesson'];l['identity']['as_of']='2024-12-31'
  l['worked_example'].update(kind='dated_real',date='2024-01-01')
  l['changes']=[dict(id='change-one',date='2024-01-01',title='Synthetic change for validation',change='A structural test entry.',why_it_matters='Exercises date and photo bindings.',source_ids=['rules'])]
  ensure_politics_photo_plan(f);self.assertTrue(validate_politics_content(f))
  l['worked_example']['date']='2025-01-01';self.assertFalse(validate_politics_content(f))
  l['worked_example']['date']='2024-01-01';l['changes'][0]['date']='2025-01-01';self.assertFalse(validate_politics_content(f))
 def test_category_and_sources_are_not_interchangeable(self):
  f=fixture();f['category']='history';self.assertFalse(validate_politics_content(f))
  f=fixture();f['sources'].append(f['sources'][0]);self.assertFalse(validate_politics_content(f))
 def test_repairs_partial_and_empty_plans_preserving_existing_requests(self):
  f=fixture();l=f['indian_politics_lesson'];l['photos']=[p for p in l['photos'] if p['section_id']!='process'];existing=list(l['photos'])
  self.assertTrue(ensure_politics_photo_plan(f));self.assertEqual(l['photos'][:len(existing)],existing)
  self.assertTrue(validate_politics_content(f));self.assertFalse(ensure_politics_photo_plan(f))
  l['photos']=[];self.assertTrue(ensure_politics_photo_plan(f));self.assertTrue(validate_politics_content(f))
 def test_diagram_context_is_neutral_not_fake_election_evidence(self):
  context=build_section_image_context('how_it_works',fixture())
  self.assertIn('educational labels',context);self.assertIn('politician',context)
 def test_photo_plan_save_is_compare_and_swap_only(self):
  collection=Mock();collection.update_one.return_value.matched_count=1
  repo=load('politics_repo_test','src/database/facts_repository.py',{**config_import,'pymongo.errors':module('pymongo.errors',DuplicateKeyError=RuntimeError),'src.database.connection':module('src.database.connection',get_db=lambda:{'facts':collection})})
  f=fixture();previous=f['indian_politics_lesson']['photos'][:2]
  self.assertTrue(repo.save_politics_photo_plan('hash',f,previous_photos=previous))
  query,update=collection.update_one.call_args.args;self.assertEqual(query['full_response.indian_politics_lesson.photos'],previous)
  self.assertEqual(set(update['$set']),{'full_response.indian_politics_lesson.photos','full_response.indian_politics_media.photo_plan_version','full_response.indian_politics_media.photo_plan_source'})
class PoliticsAsyncTests(unittest.IsolatedAsyncioTestCase):
 async def test_generation_uses_json_mode_and_prepares_politics(self):
  r=generator_module();generate=AsyncMock(return_value=types.SimpleNamespace(parsed=None,text=json.dumps(fixture())))
  r.genai.Client.return_value.aio.models.generate_content=generate
  f=await r.generate_daily_fact('indian_politics',[]);self.assertIsNotNone(f)
  self.assertNotIn('response_schema',generate.call_args.kwargs['config']);self.assertEqual(f['indian_politics_media']['generated_limit'],3)
 async def test_institutional_sections_and_stock_gallery_use_separate_pools(self):
  f=fixture();seen=[]
  async def rank(fact,photos,**kwargs):
   seen.extend(photos)
   request=next(p for p in fact['indian_politics_lesson']['photos'] if p['kind']=='modern_context')
   return PhotoRankingResult([{**p,'indian_politics_request_ids':[request['id']]} for p in photos])
  chosen=await select_politics_photos(f,commons=AsyncMock(return_value=[photo(1)]),fetch=AsyncMock(return_value=[stock(1)]),rank=rank)
  self.assertTrue(any(p['provider']=='wikimedia' and not p.get('indian_politics_gallery_only') for p in chosen))
  self.assertTrue(any(p['provider']=='unsplash' and p.get('indian_politics_gallery_only') for p in chosen))
  self.assertTrue(all(p['indian_politics_request_ids']==[] for p in chosen if p.get('indian_politics_gallery_only')))
 async def test_worker_keeps_source_bindings_and_generates_only_three_images(self):
  r=routes_module();f=fixture();p=f['indian_politics_lesson']['photos'][0]
  r.select_politics_photos=AsyncMock(return_value=[{**photo(1),'indian_politics_request_ids':[p['id']]},{**stock(1),'indian_politics_gallery_only':True,'indian_politics_request_ids':[]}]);r.track_selection=AsyncMock(return_value=True)
  await r._background_image_task(f['visual_suggestions'],'hash',article=f)
  self.assertEqual(r.generate_and_save_image.await_count,3)
  ready=[c for c in r.set_fact_image_state.call_args_list if c.args[2]=='ready' and c.args[1].startswith('indian_politics_')]
  self.assertEqual({c.args[1] for c in ready},{'indian_politics_photo_0','indian_politics_scene_0'})
 async def test_photo_retry_saves_repaired_plan_without_paid_generation(self):
  r=routes_module();f=fixture();f['indian_politics_lesson']['photos']=f['indian_politics_lesson']['photos'][:2]
  r.get_fact_by_hash.return_value={'full_response':f,'images':{'cover':'https://example.org/cover'}}
  bg=Mock();await r.retry_image_generation(Mock(),bg,'hash',photos_only=True)
  r.save_politics_photo_plan.assert_called_once();self.assertTrue(all(k.startswith(('indian_politics_photo_','indian_politics_scene_')) for k in r.start_fact_images.call_args.args[1]))
  args=bg.add_task.call_args;await args.args[0](*args.args[1:],**args.kwargs)
  r.generate_and_save_image.assert_not_awaited()
