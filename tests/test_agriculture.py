"""Agriculture contract, diagram/data provenance and shared asynchronous media checks."""
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock,Mock
APP=Path(__file__).resolve().parents[1]/'app';sys.path.insert(0,str(APP))
package=types.ModuleType('src.facts');package.__path__=[str(APP/'src/facts')];sys.modules.setdefault('src.facts',package)
from src.facts.agriculture import validate_agriculture_content,valid_agriculture_diagram,prepare_agriculture_media,ensure_agriculture_photo_plan,ensure_agriculture_science_image
from src.facts.photo_ranking import select_agriculture_photos,rank_photos,PhotoRankingResult
from src.facts.lifecycle import fact_image_keys
from test_fact_evidence_lifecycle import routes_module,generator_module,load,module,config_import
from test_photo_ranking import photo as unsplash_photo
def fixture():return json.loads((Path(__file__).parent/'fixtures/agriculture_lesson.json').read_text())
def fixture_v2():
    f=fixture();ensure_agriculture_science_image(f);ensure_agriculture_photo_plan(f,expand=True);return f
def photo(i=0):
    return dict(provider='wikimedia',provider_id=f'commons_{i}',url=f'https://upload.wikimedia.org/straw{i}.jpg',
        source_url=f'https://commons.wikimedia.org/wiki/File:Straw{i}.jpg',title='Straw mulch',description='Straw mulch cover',
        author='Photographer',license='CC BY-SA 4.0',license_url='https://creativecommons.org/licenses/by-sa/4.0/')
class AgricultureContractTests(unittest.TestCase):
    def test_science_image_and_dense_photo_plan_have_separate_bounded_slots(self):
        f=fixture_v2();self.assertTrue(validate_agriculture_content(f));prepare_agriculture_media(f)
        self.assertEqual(f['agriculture_media']['generated_slots'],['cover','overview','how_it_works'])
        self.assertEqual(f['agriculture_media']['generated_limit'],3)
        self.assertIn('how_it_works',fact_image_keys(f));self.assertIn('agriculture_scene_11',fact_image_keys(f))
        f['visual_suggestions']['explanation_2']='Extra';self.assertFalse(validate_agriculture_content(f))
    def test_expansion_preserves_request_indexes_and_links_each_process_step(self):
        f=fixture();old=list(f['agriculture_lesson']['photos'])
        self.assertTrue(ensure_agriculture_photo_plan(f,expand=True))
        self.assertEqual(f['agriculture_lesson']['photos'][:len(old)],old)
        steps={p['step_id'] for p in f['agriculture_lesson']['photos'] if p['section_id']=='process'}
        self.assertEqual(steps,{p['id'] for p in f['agriculture_lesson']['process_steps']})
        self.assertFalse(ensure_agriculture_photo_plan(f,expand=True));self.assertTrue(validate_agriculture_content(f))
    def test_valid_contract_server_owned_budget_and_optional_fields(self):
        f=fixture();self.assertTrue(validate_agriculture_content(f));prepare_agriculture_media(f)
        self.assertEqual(f['agriculture_media']['generated_limit'],2)
        self.assertEqual(f['agriculture_validation']['agronomic_verification'],'not_performed')
        self.assertEqual(set(fact_image_keys(f)),{'cover','overview','agriculture_photo_0',*[f'agriculture_scene_{n}' for n in range(12)]})
        f['agriculture_lesson'].update(diagram=None,photos=[],measurements=[],optional_depth=[],key_terms=[])
        f['agriculture_lesson']['field_context'].update(crops=[],growing_conditions=[],when_it_matters=None)
        self.assertFalse(validate_agriculture_content(f))
        self.assertTrue(ensure_agriculture_photo_plan(f));self.assertTrue(validate_agriculture_content(f))
    def test_invalid_sources_references_conditions_and_extra_generated_images_fail(self):
        for mutate in (lambda l:l['identity'].update(source_ids=['missing']),
            lambda l:l['process_steps'][0].update(id='surface'),
            lambda l:l['process_steps'][0].update(conditions=[]),
            lambda l:l['diagram']['connections'][0].update(to_id='missing'),
            lambda l:l['photos'][0].update(step_id='missing'),
            lambda l:l['photos'][0].update(section_id='case'),
            lambda l:l.update(indian_case_study=None)):
            f=fixture();mutate(f['agriculture_lesson']);self.assertFalse(validate_agriculture_content(f))
        f=fixture();f['visual_suggestions']['how_it_works']='Extra paid image';self.assertFalse(validate_agriculture_content(f))
    def test_process_season_and_comparison_diagrams_are_meaningfully_linked(self):
        l=fixture()['agriculture_lesson'];d=l['diagram']
        d.update(type='process',layers=[],connections=[],process_step_ids=['cover','surface','observe'])
        self.assertTrue(valid_agriculture_diagram(d,l['process_steps']))
        d['process_step_ids'].reverse();self.assertFalse(valid_agriculture_diagram(d,l['process_steps']))
        d.update(type='seasonal',process_step_ids=[],season_stages=[dict(id='early',title='Early',timing='Relevant crop stage',process_step_ids=['cover'],what_to_notice='The material'),dict(id='later',title='Later',timing='Later in the local season',process_step_ids=['surface','observe'],what_to_notice='The result in context')])
        self.assertTrue(valid_agriculture_diagram(d,l['process_steps']))
        d['season_stages'][1]['process_step_ids']=['cover'];self.assertFalse(valid_agriculture_diagram(d,l['process_steps']))
        d.update(type='comparison',season_stages=[],comparison_basis='Comparable plot context',comparisons=[dict(name=n,approach='Approach',benefit='Benefit',limitation='Limit',conditions='Conditions') for n in ('A','B')])
        self.assertTrue(valid_agriculture_diagram(d,l['process_steps']));d['comparison_basis']=None;self.assertFalse(valid_agriculture_diagram(d,l['process_steps']))
    def test_reported_measurements_require_finite_values_basis_and_dated_context(self):
        f=fixture();m=dict(id='count',label='Demonstration count',value=2,unit='plots',basis='Illustrative layout count',kind='illustrative',explanation='Not a field result',place=None,period=None,as_of=None,source_ids=['s1'])
        f['agriculture_lesson']['measurements']=[m];self.assertTrue(validate_agriculture_content(f))
        m['kind']='reported';self.assertFalse(validate_agriculture_content(f))
        m.update(place='Example region',period='2020',as_of='2020-12-31');self.assertTrue(validate_agriculture_content(f))
        for invalid in ('2020-02-30','9999-01-01'):
            m['as_of']=invalid;self.assertFalse(validate_agriculture_content(f))
        m['as_of']='2020-12-31';m['value']=True;self.assertFalse(validate_agriculture_content(f))
class AgricultureAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_independent_gallery_is_stock_only_and_never_binds_inline(self):
        async def rank(fact,pool,**kwargs):return [{**p,'agriculture_request_ids':['residue']} for p in pool]
        result=await select_agriculture_photos(fixture(),commons=AsyncMock(return_value=[photo()]),fetch=AsyncMock(return_value=[unsplash_photo(1)]),rank=rank)
        section=[p for p in result if not p.get('agriculture_gallery_only')]
        gallery=[p for p in result if p.get('agriculture_gallery_only')]
        self.assertTrue(section);self.assertTrue(gallery)
        self.assertTrue(all(p['provider']=='wikimedia' for p in section))
        self.assertTrue(all(p['provider']=='unsplash' and p['agriculture_request_ids']==[] for p in gallery))
    async def test_ranker_sends_text_context_and_binds_request_ids(self):
        p=photo();payload={'selected':[dict(photo_id=p['provider_id'],score=90,scene='residue',reason='The metadata identifies straw mulch.')],'retry_queries':[]}
        create=AsyncMock(return_value=types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps(payload)))]))
        client=types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
        result=await rank_photos(fixture(),[p],client=client)
        self.assertEqual(result[0]['agriculture_request_ids'],['residue'])
        data=json.loads(create.call_args.kwargs['messages'][1]['content']);self.assertIn('field_context',data['lesson'])
        self.assertNotIn('https://',json.dumps(data['photos']))
    async def test_agriculture_uses_one_recovery_and_keeps_popular_views_at_the_end(self):
        photos=[{**unsplash_photo(i),'likes':i} for i in range(3)];p=photo()
        calls={'commons':0,'stock':0}
        async def rank(fact,pool,**kwargs):
            group='commons' if pool and pool[0]['provider']=='wikimedia' else 'stock';calls[group]+=1
            if calls[group]==1:return PhotoRankingResult([], [{'scene':'residue','query':'mulch'}])
            return [{**v,'agriculture_request_ids':['residue']} for v in pool]
        result=await select_agriculture_photos(fixture(),fetch=AsyncMock(return_value=photos),commons=AsyncMock(return_value=[p]),rank=rank)
        self.assertEqual(calls,{'commons':2,'stock':2});self.assertEqual(result[0]['provider'],'wikimedia')
        self.assertTrue(all(p['popular_pick'] and p['agriculture_request_ids']==[] for p in result[-3:]))
    async def test_empty_plan_triggers_searches_instead_of_silently_skipping(self):
        f=fixture();f['agriculture_lesson']['photos']=[];fetch=AsyncMock(return_value=[]);commons=AsyncMock(return_value=[]);rank=AsyncMock(return_value=[])
        self.assertEqual(await select_agriculture_photos(f,fetch=fetch,commons=commons,rank=rank),[])
        self.assertTrue(fetch.await_count);self.assertTrue(commons.await_count);self.assertEqual(rank.await_count,2)
        self.assertTrue(f['agriculture_lesson']['photos'])
        # Exact named places never go to stock providers.
        place=f['agriculture_lesson']['indian_case_study']['place']
        self.assertNotIn(place,[c.args[0] for c in fetch.call_args_list])
    async def test_worker_caps_ai_images_and_preserves_step_binding(self):
        r=routes_module();f=fixture_v2();prepare_agriculture_media(f)
        r.generate_and_save_image=AsyncMock(return_value='https://example.org/illustration.jpg')
        r.select_agriculture_photos=AsyncMock(return_value=[{**photo(),'agriculture_request_ids':['residue']}])
        await r._background_image_task({**f['visual_suggestions'],'explanation_2':'Ignore'},'hash',article=f)
        self.assertEqual(r.generate_and_save_image.await_count,3)
        calls=[c for c in r.set_fact_image_state.call_args_list if c.kwargs.get('credit')]
        self.assertEqual(sum(c.kwargs['credit'].get('kind')=='generated' for c in calls),3)
        bound=next(c.kwargs['credit'] for c in calls if c.args[1]=='agriculture_photo_0')
        self.assertEqual(bound['step_id'],'cover');self.assertEqual(bound['section_id'],'process')
    async def test_generator_selects_indian_concept_prompt_and_prepares_media(self):
        r=generator_module();r.genai.Client.return_value.aio.models.generate_content=AsyncMock(return_value=types.SimpleNamespace(parsed=fixture_v2()))
        result=await r.generate_daily_fact('agriculture',[])
        self.assertIsNotNone(result);self.assertEqual(result['agriculture_media']['generated_limit'],3)
        prompt=r.genai.Client.return_value.aio.models.generate_content.call_args.kwargs['contents']
        self.assertIn('rooted in Indian agriculture',prompt);self.assertIn('no single growing season',prompt)


class AgriculturePhotoPlanTests(unittest.TestCase):
    def test_missing_null_empty_plans_are_bounded_and_existing_plans_stay_intact(self):
        for missing in ('missing',None,[]):
            f=fixture();l=f['agriculture_lesson'];l['photos']=missing
            if missing=='missing':l.pop('photos')
            l['identity']['name']='Apatani rice–fish farming';l['field_context']['crops']=['Rice'];l['indian_case_study']['place']='Ziro valley'
            self.assertTrue(ensure_agriculture_photo_plan(f));self.assertTrue(validate_agriculture_content(f))
            photos=l['photos'];self.assertTrue({'overview','context','process','case','tradeoffs','limits'}<={p['section_id'] for p in photos});self.assertLessEqual(len(photos),18)
            self.assertIn('Apatani rice fish farming',photos[0]['queries'])
            case=next(p for p in photos if p['section_id']=='case');self.assertEqual(case['kind'],'named_place');self.assertEqual(case['subject'],'Ziro valley')
            self.assertFalse(ensure_agriculture_photo_plan(f));self.assertIs(l['photos'],photos)
        f=fixture();photos=f['agriculture_lesson']['photos'];self.assertFalse(ensure_agriculture_photo_plan(f));self.assertIs(f['agriculture_lesson']['photos'],photos)
    def test_fallback_does_not_invent_missing_context_or_hide_invalid_plans(self):
        f=fixture();l=f['agriculture_lesson'];l['photos']=[];l['identity']['name']=' ';f['topic']='Seed storage';l['field_context']['crops']=[];l['indian_case_study'].pop('place')
        ensure_agriculture_photo_plan(f);self.assertTrue(all(p['section_id']!='case' for p in l['photos']));self.assertEqual(l['photos'][0]['subject'],'Seed storage')
        f=fixture();f['agriculture_lesson']['photos']=[{'invalid':'request'}];self.assertFalse(ensure_agriculture_photo_plan(f));self.assertFalse(validate_agriculture_content(f))
        f=fixture();l=f['agriculture_lesson'];l['photos']=[];l['identity']['name']='x'*400;l['field_context']['crops']=['y'*400];l['indian_case_study']['place']='z'*400
        ensure_agriculture_photo_plan(f);self.assertTrue(all(1<=len(q)<=160 for p in l['photos'] for q in p['queries']))
    def test_repository_patch_is_atomic_and_only_updates_missing_plan_fields(self):
        collection=Mock();collection.update_one.return_value.matched_count=1
        repo=load('agriculture_repo_test','src/database/facts_repository.py',{**config_import,
            'pymongo.errors':module('pymongo.errors',DuplicateKeyError=RuntimeError),
            'src.database.connection':module('src.database.connection',get_db=lambda:{'facts':collection})})
        f=fixture();f['agriculture_lesson']['photos']=[];ensure_agriculture_photo_plan(f)
        self.assertTrue(repo.save_agriculture_photo_plan('hash',f))
        query,update=collection.update_one.call_args.args;self.assertEqual(query['content_hash'],'hash')
        self.assertEqual(query['$or'],[{'full_response.agriculture_lesson.photos':[]},{'full_response.agriculture_lesson.photos':None}])
        self.assertEqual(set(update['$set']),{'full_response.agriculture_lesson.photos','full_response.agriculture_media'})
        collection.update_one.return_value.matched_count=0;self.assertFalse(repo.save_agriculture_photo_plan('hash',f))

class AgriculturePhotoRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_legacy_retry_persists_the_third_image_before_scheduling(self):
        r=routes_module();f=fixture();r.get_fact_by_hash.return_value={'full_response':f,'images':{'cover':'https://example.org/cover'}}
        bg=Mock();await r.retry_image_generation(Mock(),bg,'hash',photos_only=False)
        saved=r.save_agriculture_photo_plan.call_args.args[1]
        self.assertTrue(saved['visual_suggestions']['how_it_works'])
        self.assertEqual(saved['agriculture_media']['generated_limit'],3)
        self.assertIn('how_it_works',r.start_fact_images.call_args.args[1])
        self.assertNotIn('cover',r.start_fact_images.call_args.args[1])
        self.assertEqual(bg.add_task.call_args.args[1]['how_it_works'],saved['visual_suggestions']['how_it_works'])
    async def test_new_generation_fills_empty_plan_before_validation_without_retrying_article(self):
        r=generator_module();f=fixture();f['agriculture_lesson']['photos']=[]
        generate=AsyncMock(return_value=types.SimpleNamespace(parsed=f));r.genai.Client.return_value.aio.models.generate_content=generate
        result=await r.generate_daily_fact('agriculture',[])
        self.assertTrue(result['agriculture_lesson']['photos']);self.assertEqual(result['agriculture_media']['photo_plan_source'],'fallback');generate.assert_awaited_once()
    async def test_legacy_retry_persists_before_search_and_photo_only_never_calls_ai(self):
        r=routes_module();f=fixture();f['agriculture_lesson']['photos']=[]
        r.get_fact_by_hash.return_value={'full_response':f,'images':{'cover':'https://example.org/cover'}}
        bg=Mock();await r.retry_image_generation(Mock(),bg,'hash',photos_only=True)
        r.save_agriculture_photo_plan.assert_called_once();planned=r.save_agriculture_photo_plan.call_args.args[1]
        args=bg.add_task.call_args;article=args.kwargs['article'];self.assertEqual(article['agriculture_lesson']['photos'],planned['agriculture_lesson']['photos'])
        self.assertTrue(args.kwargs['photos_only']);self.assertTrue(all(k.startswith(('agriculture_photo_','agriculture_scene_')) for k in r.start_fact_images.call_args.args[1]))
        first=article['agriculture_lesson']['photos'][0];r.select_agriculture_photos=AsyncMock(return_value=[{**photo(),'agriculture_request_ids':[first['id']]}])
        await args.args[0](*args.args[1:],**args.kwargs)
        r.generate_and_save_image.assert_not_awaited();r.save_agriculture_photo_plan.assert_called_once()
        credit=next(c.kwargs['credit'] for c in r.set_fact_image_state.call_args_list if c.args[1]=='agriculture_photo_0' and c.kwargs.get('credit'))
        self.assertEqual(credit['photo_id'],first['id']);self.assertEqual(credit['section_id'],'overview')
    async def test_failed_plan_save_does_not_start_unbound_searches(self):
        r=routes_module();f=fixture();f['agriculture_lesson']['photos']=[]
        r.get_fact_by_hash.return_value={'full_response':f,'images':{}};r.save_agriculture_photo_plan.return_value=False
        bg=Mock()
        with self.assertRaises(r.HTTPException) as error:await r.retry_image_generation(Mock(),bg,'hash',photos_only=True)
        self.assertEqual(error.exception.status_code,503);bg.add_task.assert_not_called();r.start_fact_images.assert_not_called()
    async def test_concurrent_repair_adopts_the_stored_plan(self):
        r=routes_module();f=fixture();f['agriculture_lesson']['photos']=[]
        current=fixture();r.save_agriculture_photo_plan.return_value=False;r.get_fact_by_hash.return_value={'full_response':current}
        self.assertIs(r._with_article_photo_plan(f,'hash'),current)
    async def test_retry_preserves_ready_photos_even_when_new_search_is_empty(self):
        r=routes_module();f=fixture();f['image_credits']={'agriculture_photo_0':photo(),'agriculture_scene_0':photo(1)}
        existing={'cover':'https://example.org/cover','agriculture_photo_0':photo()['url'],'agriculture_scene_0':photo(1)['url']}
        await r._background_image_task(f['visual_suggestions'],'hash',existing,article=f,photos_only=True)
        r.generate_and_save_image.assert_not_awaited()
        self.assertTrue(all(c.args[1] not in ('agriculture_photo_0','agriculture_scene_0') for c in r.set_fact_image_state.call_args_list))
        self.assertEqual(r.set_fact_photo_selection.call_args.args[1]['selected_count'],2)
        self.assertEqual(r.select_agriculture_photos.call_args.kwargs['excluded'],{photo()['source_url'],photo(1)['source_url']})
    async def test_polling_merges_the_repaired_plan_with_its_photo_credits(self):
        r=routes_module();old=fixture();old['agriculture_lesson']['photos']=[];current=fixture();current['agriculture_lesson']['photos']=[];ensure_agriculture_photo_plan(current)
        r.get_fact_job.return_value={'status':'completed','fact_data':{'fact':old,'content_hash':'hash'}}
        r.get_fact_by_hash.return_value={'full_response':current,'images':{},'image_credits':{}}
        result=await r.get_fact_job_status('job');self.assertEqual(result['data']['fact']['agriculture_lesson']['photos'],current['agriculture_lesson']['photos'])
    async def test_empty_search_outcome_is_distinct_from_no_search_plan(self):
        r=routes_module();f=fixture();await r._background_image_task({},'hash',article=f,photos_only=True)
        state=r.set_fact_photo_selection.call_args.args[1];self.assertEqual(state['status'],'insufficient');self.assertEqual(state['reason'],'no_usable_photos');self.assertGreater(state['request_count'],1)
        f={'article_type':'food_lesson','food_lesson':{'photos':[]}};await r._background_image_task({},'hash',article=f,photos_only=True)
        state=r.set_fact_photo_selection.call_args.args[1];self.assertEqual(state['status'],'skipped');self.assertEqual(state['reason'],'no_photo_requests')
