"""Offline History chronology, evidence, photo binding and generation regression checks."""
import json,sys,types,unittest
from pathlib import Path
from unittest.mock import AsyncMock,Mock
APP=Path(__file__).resolve().parents[1]/'app';sys.path.insert(0,str(APP))
pkg=types.ModuleType('src.facts');pkg.__path__=[str(APP/'src/facts')];sys.modules.setdefault('src.facts',pkg)
from src.facts.history import validate_history_content,valid_period,ensure_history_photo_plan,prepare_history_media,build_history_prompt
from src.facts.lifecycle import fact_image_keys,image_generation_state
from src.facts.image_policy import validate_image_plan
from src.facts.photo_ranking import select_history_photos,PhotoRankingResult
from src.facts.visual_prompts import build_section_image_context
from test_fact_evidence_lifecycle import generator_module,routes_module,load,config_import,module
from test_agriculture import photo
from test_photo_ranking import photo as stock
def fixture():return json.loads((Path(__file__).parent/'fixtures/history_lesson.json').read_text())
class HistoryTests(unittest.TestCase):
 def test_contract_and_exact_three_ai_slots(self):
  f=fixture();self.assertTrue(validate_history_content(f));self.assertTrue(validate_image_plan(f))
  prepare_history_media(f);self.assertEqual(f['history_media']['generated_limit'],3)
  self.assertEqual(f['visual_suggestions']['how_it_works'],f['history_lesson']['mechanism']['diagram_prompt'])
  self.assertEqual(len(fact_image_keys(f)),3+len(f['history_lesson']['photos'])+12)
  self.assertEqual(image_generation_state({'full_response':f},30)['timeout_seconds'],720)
 def test_rejects_false_chronology_India_overlap_and_broken_references(self):
  for mutate in [lambda l:l['chronology'].reverse(),lambda l:l['chronology'][0].update(start_year=0),lambda l:l['chronology'][0].update(figure_ids=['unknown']),lambda l:l['decisions'][0].update(chronology_id='unknown'),lambda l:l['india']['connections'][0].update(start_year=1700,end_year=1701),lambda l:l['india']['connections'][0].update(relationship='documented_impact'),lambda l:l['evidence']['records'][0].update(source_ids=['unknown']),lambda l:l['photos'][0].update(entry_id='unknown')]:
   f=fixture();mutate(f['history_lesson']);self.assertFalse(validate_history_content(f))
 def test_bce_ranges_and_no_year_zero(self):
  self.assertTrue(valid_period({'start_year':-500,'end_year':-400}))
  self.assertTrue(valid_period({'start_year':-1,'end_year':1}))
  for p in ({'start_year':0,'end_year':1},{'start_year':True,'end_year':1},{'start_year':2020,'end_year':2010},{'start_year':2000,'end_year':9999}):self.assertFalse(valid_period(p))
 def test_sparse_modern_research_is_valid_without_fabricated_discoveries(self):
  f=fixture();self.assertEqual(f['history_lesson']['evidence']['updates'],[]);self.assertTrue(validate_history_content(f))
  self.assertIn('never\ninvent an archaeological discovery',build_history_prompt([]))
 def test_repairs_partial_and_empty_plans_preserving_existing_requests(self):
  f=fixture();l=f['history_lesson'];l['photos']=[p for p in l['photos'] if p['section_id']!='chronology'];existing=list(l['photos'])
  self.assertTrue(ensure_history_photo_plan(f));self.assertEqual(l['photos'][:len(existing)],existing)
  self.assertTrue(validate_history_content(f));self.assertFalse(ensure_history_photo_plan(f))
  l['photos']=[];self.assertTrue(ensure_history_photo_plan(f));self.assertTrue(validate_history_content(f))
 def test_ancient_fallback_never_requests_archival_event_photographs(self):
  f=fixture();f['history_lesson']['identity']['end_year']=-100;f['history_lesson']['photos']=[]
  self.assertTrue(ensure_history_photo_plan(f))
  self.assertFalse(any(p['kind']=='archival_photo' for p in f['history_lesson']['photos']))
 def test_diagram_context_allows_explanatory_labels_not_fake_archives(self):
  context=build_section_image_context('how_it_works',fixture())
  self.assertIn('short accurate educational labels',context);self.assertIn('never authentic documents',context)
 def test_photo_plan_save_is_compare_and_swap_only(self):
  collection=Mock();collection.update_one.return_value.matched_count=1
  repo=load('history_repo_test','src/database/facts_repository.py',{**config_import,'pymongo.errors':module('pymongo.errors',DuplicateKeyError=RuntimeError),'src.database.connection':module('src.database.connection',get_db=lambda:{'facts':collection})})
  f=fixture();previous=f['history_lesson']['photos'][:2]
  self.assertTrue(repo.save_history_photo_plan('hash',f,previous_photos=previous))
  query,update=collection.update_one.call_args.args;self.assertEqual(query['full_response.history_lesson.photos'],previous)
  self.assertEqual(set(update['$set']),{'full_response.history_lesson.photos','full_response.history_media.photo_plan_version','full_response.history_media.photo_plan_source'})
class HistoryAsyncTests(unittest.IsolatedAsyncioTestCase):
 async def test_generation_uses_json_mode_and_prepares_history(self):
  r=generator_module();generate=AsyncMock(return_value=types.SimpleNamespace(parsed=None,text=json.dumps(fixture())))
  r.genai.Client.return_value.aio.models.generate_content=generate
  f=await r.generate_daily_fact('history',[]);self.assertIsNotNone(f)
  self.assertNotIn('response_schema',generate.call_args.kwargs['config']);self.assertEqual(f['history_media']['generated_limit'],3)
 async def test_archival_sections_and_modern_context_gallery_use_separate_pools(self):
  f=fixture();seen=[]
  async def rank(fact,photos,**kwargs):
   seen.extend(photos)
   request=next(p for p in fact['history_lesson']['photos'] if p['kind']=='modern_context')
   return PhotoRankingResult([{**p,'history_request_ids':[request['id']]} for p in photos])
  chosen=await select_history_photos(f,commons=AsyncMock(return_value=[photo(1)]),fetch=AsyncMock(return_value=[stock(1)]),rank=rank)
  self.assertTrue(any(p['provider']=='wikimedia' and not p.get('history_gallery_only') for p in chosen))
  self.assertTrue(any(p['provider']=='unsplash' and p.get('history_gallery_only') for p in chosen))
  self.assertTrue(all(p['history_request_ids']==[] for p in chosen if p.get('history_gallery_only')))
 async def test_worker_keeps_source_bindings_and_generates_only_three_images(self):
  r=routes_module();f=fixture();p=f['history_lesson']['photos'][0]
  r.select_history_photos=AsyncMock(return_value=[{**photo(1),'history_request_ids':[p['id']]},{**stock(1),'history_gallery_only':True,'history_request_ids':[]}]);r.track_selection=AsyncMock(return_value=True)
  await r._background_image_task(f['visual_suggestions'],'hash',article=f)
  self.assertEqual(r.generate_and_save_image.await_count,3)
  ready=[c for c in r.set_fact_image_state.call_args_list if c.args[2]=='ready' and c.args[1].startswith('history_')]
  self.assertEqual({c.args[1] for c in ready},{'history_photo_0','history_scene_0'})
 async def test_photo_retry_saves_repaired_plan_without_paid_generation(self):
  r=routes_module();f=fixture();f['history_lesson']['photos']=f['history_lesson']['photos'][:2]
  r.get_fact_by_hash.return_value={'full_response':f,'images':{'cover':'https://example.org/cover'}}
  bg=Mock();await r.retry_image_generation(Mock(),bg,'hash',photos_only=True)
  r.save_history_photo_plan.assert_called_once();self.assertTrue(all(k.startswith(('history_photo_','history_scene_')) for k in r.start_fact_images.call_args.args[1]))
  args=bg.add_task.call_args;await args.args[0](*args.args[1:],**args.kwargs)
  r.generate_and_save_image.assert_not_awaited()
