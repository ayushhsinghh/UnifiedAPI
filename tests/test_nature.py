"""Nature contract, diagram/data provenance and shared asynchronous media checks."""
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock,Mock
APP=Path(__file__).resolve().parents[1]/'app';sys.path.insert(0,str(APP))
package=types.ModuleType('src.facts');package.__path__=[str(APP/'src/facts')];sys.modules.setdefault('src.facts',package)
from src.facts.nature import validate_nature_content,valid_nature_diagram,prepare_nature_media,ensure_nature_photo_plan
from src.facts.photo_ranking import select_nature_photos,rank_photos,PhotoRankingResult
from src.facts.lifecycle import fact_image_keys
from test_fact_evidence_lifecycle import routes_module,generator_module,load,module,config_import
from test_photo_ranking import photo as unsplash_photo
def fixture():return json.loads((Path(__file__).parent/'fixtures/nature_lesson.json').read_text())
def photo(i=0):
    return dict(provider='wikimedia',provider_id=f'commons_{i}',url=f'https://upload.wikimedia.org/straw{i}.jpg',
        source_url=f'https://commons.wikimedia.org/wiki/File:Straw{i}.jpg',title='Straw mulch',description='Straw mulch cover',
        author='Photographer',license='CC BY-SA 4.0',license_url='https://creativecommons.org/licenses/by-sa/4.0/')
class NatureContractTests(unittest.TestCase):
    def test_valid_contract_server_owned_budget_and_optional_fields(self):
        f=fixture();self.assertTrue(validate_nature_content(f));prepare_nature_media(f)
        self.assertEqual(f['nature_media']['generated_limit'],2)
        self.assertEqual(f['nature_validation']['species_verification'],'not_performed')
        self.assertEqual(set(fact_image_keys(f)),{'cover','overview','nature_photo_0',*[f'nature_scene_{n}' for n in range(6)]})
        f['nature_lesson'].update(diagram=None,photos=[],measurements=[],optional_depth=[],key_terms=[])
        f['nature_lesson'].update(recognition_features=[],natural_connections=[],notice_it_yourself=None)
        self.assertFalse(validate_nature_content(f))
        self.assertTrue(ensure_nature_photo_plan(f));self.assertTrue(validate_nature_content(f))
    def test_invalid_sources_references_scale_and_extra_generated_images_fail(self):
        for mutate in (lambda l:l['identity'].update(source_ids=['missing']),lambda l:l['explanation_steps'][0].update(conditions=[]),lambda l:l['diagram']['nodes'][0].update(ref_id='missing'),lambda l:l['photos'][0].update(feature_id='missing'),lambda l:l['recognition_features'][0].update(viewing_scale='invisible')):
            f=fixture();mutate(f['nature_lesson']);self.assertFalse(validate_nature_content(f))
        f=fixture();f['visual_suggestions']['how_it_works']='Extra';self.assertFalse(validate_nature_content(f))
    def test_diagram_graph_integrity(self):
        l=fixture()['nature_lesson'];d=l['diagram'];self.assertTrue(valid_nature_diagram(d,l))
        d['edges'].pop();self.assertFalse(valid_nature_diagram(d,l))
        d['type']='relationships';self.assertFalse(valid_nature_diagram(d,l))
        d.update(type='labelled_structure',edges=[],nodes=[dict(id='f'+str(i),ref_type='feature',ref_id=f['id'],explanation=f['meaning']) for i,f in enumerate(l['recognition_features'])]);self.assertTrue(valid_nature_diagram(d,l))
        d.update(type='comparison',nodes=[],comparison_basis='Visible condition',comparisons=[dict(name=n,observation='Visible condition',explanation='A clue only',conditions='Same photo') for n in ('Whole','Fragmented')]);self.assertTrue(valid_nature_diagram(d,l))
    def test_dated_context_and_species_requirements(self):
        f=fixture();l=f['nature_lesson'];l['real_world_example'].update(kind='organism',scientific_name=None);self.assertFalse(validate_nature_content(f))
        l['real_world_example'].update(kind='phenomenon');l['conservation_context']=dict(status='Example',system='Example',scope='Example',assessed_on='2020-02-30',source_ids=['s1']);self.assertFalse(validate_nature_content(f))
        l['conservation_context']['assessed_on']='2020-02-20';self.assertTrue(validate_nature_content(f))
class NatureAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_ranker_sends_text_context_and_binds_request_ids(self):
        p=photo();payload={'selected':[dict(photo_id=p['provider_id'],score=90,scene='leaflitter',reason='The metadata identifies straw mulch.')],'retry_queries':[]}
        create=AsyncMock(return_value=types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps(payload)))]))
        client=types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
        result=await rank_photos(fixture(),[p],client=client)
        self.assertEqual(result[0]['nature_request_ids'],['leaflitter'])
        data=json.loads(create.call_args.kwargs['messages'][1]['content']);self.assertIn('observation_context',data['lesson'])
        self.assertNotIn('https://',json.dumps(data['photos']))
    async def test_nature_uses_one_recovery_and_keeps_popular_views_at_the_end(self):
        photos=[{**unsplash_photo(i),'likes':i} for i in range(3)];p=photo()
        rank=AsyncMock(side_effect=[PhotoRankingResult([], [{'scene':'leaflitter','query':'mulch'}]),[{**p,'nature_request_ids':['leaflitter']} ]])
        result=await select_nature_photos(fixture(),fetch=AsyncMock(return_value=photos),commons=AsyncMock(return_value=[p]),rank=rank)
        self.assertEqual(rank.await_count,2);self.assertEqual(result[0]['provider'],'wikimedia')
        self.assertTrue(all(p['popular_pick'] and p['nature_request_ids']==[] for p in result[-3:]))
    async def test_empty_photo_plan_starts_provider_searches(self):
        f=fixture();f['nature_lesson']['photos']=[];fetch=AsyncMock(return_value=[]);commons=AsyncMock(return_value=[]);rank=AsyncMock(return_value=[])
        self.assertEqual(await select_nature_photos(f,fetch=fetch,commons=commons,rank=rank),[])
        self.assertTrue(fetch.await_count);self.assertTrue(commons.await_count);rank.assert_awaited_once()
        place=f['nature_lesson']['real_world_example']['place']
        self.assertNotIn(place,[c.args[0] for c in fetch.call_args_list])
    async def test_worker_caps_ai_images_and_preserves_feature_binding(self):
        r=routes_module();f=fixture();prepare_nature_media(f)
        r.generate_and_save_image=AsyncMock(return_value='https://example.org/illustration.jpg')
        r.select_nature_photos=AsyncMock(return_value=[{**photo(),'nature_request_ids':['leaflitter']}])
        await r._background_image_task({**f['visual_suggestions'],'how_it_works':'Ignore'},'hash',article=f)
        self.assertEqual(r.generate_and_save_image.await_count,2)
        calls=[c for c in r.set_fact_image_state.call_args_list if c.kwargs.get('credit')]
        self.assertEqual(sum(c.kwargs['credit'].get('kind')=='generated' for c in calls),2)
        bound=next(c.kwargs['credit'] for c in calls if c.args[1]=='nature_photo_0')
        self.assertEqual(bound['feature_id'],'litter');self.assertEqual(bound['section_id'],'recognition')
    async def test_generator_selects_global_observation_prompt_and_prepares_media(self):
        r=generator_module();r.genai.Client.return_value.aio.models.generate_content=AsyncMock(return_value=types.SimpleNamespace(parsed=fixture()))
        result=await r.generate_daily_fact('nature',[])
        self.assertIsNotNone(result);self.assertEqual(result['nature_media']['generated_limit'],2)
        prompt=r.genai.Client.return_value.aio.models.generate_content.call_args.kwargs['contents']
        self.assertIn('No India-first requirement',prompt);self.assertIn('unaided observer',prompt)

    async def test_exact_species_and_microscopy_never_use_stock_or_wrong_view(self):
        for kind in ('named_species','microscopy'):
            f=fixture();f['nature_lesson']['photos'][0].update(kind=kind,subject='Acer rubrum',queries=['Acer rubrum'])
            good={**photo(),'title':'Acer rubrum micrograph','description':'Microscopy of Acer rubrum tissue'}
            wrong={**photo(1),'title':'Acer rubrum macro view','description':'A close-up of a leaf'}
            fetch=AsyncMock();rank=AsyncMock(return_value=[{**good,'nature_request_ids':['leaflitter']},{**wrong,'nature_request_ids':['leaflitter']}])
            result=await select_nature_photos(f,fetch=fetch,commons=AsyncMock(return_value=[good,wrong]),rank=rank)
            fetch.assert_not_awaited();self.assertEqual(len(result),1 if kind=='microscopy' else 2)


class NaturePhotoPlanTests(unittest.TestCase):
    def test_missing_null_empty_plans_have_valid_feature_and_place_bindings(self):
        for missing in ('missing',None,[]):
            f=fixture();l=f['nature_lesson'];l['photos']=missing
            if missing=='missing':l.pop('photos')
            self.assertTrue(ensure_nature_photo_plan(f));self.assertTrue(validate_nature_content(f))
            photos=l['photos'];self.assertEqual([p['section_id'] for p in photos],['overview','recognition','example'])
            self.assertEqual(photos[1]['feature_id'],'litter');self.assertEqual(photos[-1]['kind'],'named_place')
            self.assertFalse(ensure_nature_photo_plan(f));self.assertIs(l['photos'],photos)
        f=fixture();photos=f['nature_lesson']['photos'];self.assertFalse(ensure_nature_photo_plan(f));self.assertIs(f['nature_lesson']['photos'],photos)
    def test_fallback_never_invents_optional_subjects_or_masks_invalid_model_plans(self):
        f=fixture();l=f['nature_lesson'];l.update(photos=[],recognition_features=[]);l['real_world_example'].update(kind='phenomenon',place=None,scientific_name=None)
        ensure_nature_photo_plan(f);self.assertEqual(len(l['photos']),1);self.assertEqual(l['photos'][0]['section_id'],'overview')
        f=fixture();f['nature_lesson']['photos']=[{'invalid':'request'}];self.assertFalse(ensure_nature_photo_plan(f));self.assertFalse(validate_nature_content(f))
        f=fixture();l=f['nature_lesson'];l['photos']=[];l['identity']['name']='x'*400
        ensure_nature_photo_plan(f);self.assertTrue(all(1<=len(q)<=160 for p in l['photos'] for q in p['queries']))
    def test_scientific_names_and_microscopic_scales_remain_explicit(self):
        f=fixture();l=f['nature_lesson'];l['photos']=[];l['identity'].update(name='Red maple',scientific_name='Acer rubrum',topic_type='organism')
        l['recognition_features']=l['recognition_features'][:1];l['recognition_features'][0]['viewing_scale']='microscopic'
        l['real_world_example'].update(kind='organism',scientific_name='Acer rubrum',subject='Red maple')
        ensure_nature_photo_plan(f);self.assertEqual([p['kind'] for p in l['photos']],['named_species','microscopy','named_species'])
        self.assertTrue(all(p['subject']=='Acer rubrum' for p in l['photos']));self.assertIn('microscopy',l['photos'][1]['queries'][0])
        self.assertEqual(l['photos'][1]['feature_id'],'litter')
    def test_repository_updates_only_the_missing_nature_plan(self):
        collection=Mock();collection.update_one.return_value.matched_count=1
        repo=load('nature_photo_repo_test','src/database/facts_repository.py',{**config_import,
            'pymongo.errors':module('pymongo.errors',DuplicateKeyError=RuntimeError),
            'src.database.connection':module('src.database.connection',get_db=lambda:{'facts':collection})})
        f=fixture();f['nature_lesson']['photos']=[];ensure_nature_photo_plan(f)
        self.assertTrue(repo.save_nature_photo_plan('hash',f));query,update=collection.update_one.call_args.args
        self.assertEqual(query['full_response.article_type'],'nature_lesson')
        self.assertEqual(query['$or'],[{'full_response.nature_lesson.photos':[]},{'full_response.nature_lesson.photos':None}])
        self.assertEqual(set(update['$set']),{'full_response.nature_lesson.photos','full_response.nature_media.photo_plan_version','full_response.nature_media.photo_plan_source'})
        collection.update_one.return_value.matched_count=0;self.assertFalse(repo.save_nature_photo_plan('hash',f))

class NaturePhotoRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_generation_repairs_empty_plan_before_validation(self):
        r=generator_module();f=fixture();f['nature_lesson']['photos']=[]
        generate=AsyncMock(return_value=types.SimpleNamespace(parsed=f));r.genai.Client.return_value.aio.models.generate_content=generate
        result=await r.generate_daily_fact('nature',[])
        self.assertTrue(result['nature_lesson']['photos']);self.assertEqual(result['nature_media']['photo_plan_source'],'fallback');generate.assert_awaited_once()
    async def test_retry_persists_before_search_and_photo_only_skips_ai(self):
        r=routes_module();f=fixture();f['nature_lesson']['photos']=[]
        r.get_fact_by_hash.return_value={'full_response':f,'images':{'cover':'https://example.org/cover'}}
        bg=Mock();await r.retry_image_generation(Mock(),bg,'hash',photos_only=True)
        r.save_nature_photo_plan.assert_called_once();args=bg.add_task.call_args;article=args.kwargs['article']
        self.assertTrue(args.kwargs['photos_only']);self.assertTrue(all(k.startswith(('nature_photo_','nature_scene_')) for k in r.start_fact_images.call_args.args[1]))
        first=article['nature_lesson']['photos'][0];r.select_nature_photos=AsyncMock(return_value=[{**photo(),'nature_request_ids':[first['id']]}])
        await args.args[0](*args.args[1:],**args.kwargs);r.generate_and_save_image.assert_not_awaited();r.save_nature_photo_plan.assert_called_once()
        credit=next(c.kwargs['credit'] for c in r.set_fact_image_state.call_args_list if c.args[1]=='nature_photo_0' and c.kwargs.get('credit'))
        self.assertEqual(credit['photo_id'],first['id']);self.assertEqual(credit['section_id'],'overview')
    async def test_persistence_failure_stops_retry_and_concurrent_repair_uses_saved_plan(self):
        r=routes_module();f=fixture();f['nature_lesson']['photos']=[];r.get_fact_by_hash.return_value={'full_response':f};r.save_nature_photo_plan.return_value=False
        bg=Mock()
        with self.assertRaises(r.HTTPException) as error:await r.retry_image_generation(Mock(),bg,'hash',photos_only=True)
        self.assertEqual(error.exception.status_code,503);bg.add_task.assert_not_called();r.start_fact_images.assert_not_called()
        current=fixture();r.get_fact_by_hash.return_value={'full_response':current};self.assertIs(r._with_article_photo_plan(f,'hash'),current)
    async def test_retry_preserves_existing_photos_and_source_exclusions(self):
        r=routes_module();f=fixture();f['image_credits']={'nature_photo_0':photo(),'nature_scene_0':photo(1)}
        existing={'cover':'https://example.org/cover','nature_photo_0':photo()['url'],'nature_scene_0':photo(1)['url']}
        await r._background_image_task(f['visual_suggestions'],'hash',existing,article=f,photos_only=True)
        r.generate_and_save_image.assert_not_awaited();self.assertTrue(all(c.args[1] not in ('nature_photo_0','nature_scene_0') for c in r.set_fact_image_state.call_args_list))
        self.assertEqual(r.set_fact_photo_selection.call_args.args[1]['selected_count'],2)
        self.assertEqual(r.select_nature_photos.call_args.kwargs['excluded'],{photo()['source_url'],photo(1)['source_url']})
    async def test_job_polling_merges_repaired_photo_plan_and_metadata(self):
        r=routes_module();old=fixture();old['nature_lesson']['photos']=[];current=fixture();current['nature_lesson']['photos']=[];ensure_nature_photo_plan(current)
        r.get_fact_job.return_value={'status':'completed','fact_data':{'fact':old,'content_hash':'hash'}};r.get_fact_by_hash.return_value={'full_response':current,'images':{}}
        result=await r.get_fact_job_status('job');self.assertEqual(result['data']['fact']['nature_lesson']['photos'],current['nature_lesson']['photos'])
        self.assertEqual(result['data']['fact']['nature_media']['photo_plan_source'],'fallback')
    async def test_fallback_species_and_microscopy_reject_stock_and_wrong_subjects(self):
        f=fixture();l=f['nature_lesson'];l['photos']=[];l['identity'].update(name='Red maple',scientific_name='Acer rubrum',topic_type='organism')
        l['recognition_features']=l['recognition_features'][:1];l['recognition_features'][0]['viewing_scale']='microscopic';l['real_world_example'].update(kind='organism',scientific_name='Acer rubrum')
        ensure_nature_photo_plan(f);fetch=AsyncMock();commons=AsyncMock(return_value=[])
        good={**photo(),'title':'Acer rubrum micrograph','description':'Microscopy of Acer rubrum tissue','nature_request_ids':['fallback_feature']}
        wrong={**photo(1),'title':'Acer rubrum macro photograph','description':'Leaf close-up','nature_request_ids':['fallback_feature']}
        rank=AsyncMock(return_value=[good,wrong]);result=await select_nature_photos(f,fetch=fetch,commons=commons,rank=rank)
        fetch.assert_not_awaited();self.assertEqual(result,[good])
