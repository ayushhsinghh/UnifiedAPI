"""Nature contract, diagram/data provenance and shared asynchronous media checks."""
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
APP=Path(__file__).resolve().parents[1]/'app';sys.path.insert(0,str(APP))
package=types.ModuleType('src.facts');package.__path__=[str(APP/'src/facts')];sys.modules.setdefault('src.facts',package)
from src.facts.nature import validate_nature_content,valid_nature_diagram,prepare_nature_media
from src.facts.photo_ranking import select_nature_photos,rank_photos,PhotoRankingResult
from src.facts.lifecycle import fact_image_keys
from test_fact_evidence_lifecycle import routes_module,generator_module
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
        self.assertTrue(validate_nature_content(f))
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
    async def test_no_documentary_requests_make_no_provider_or_ranker_calls(self):
        f=fixture();f['nature_lesson']['photos']=[];fetch=AsyncMock();commons=AsyncMock();rank=AsyncMock()
        self.assertEqual(await select_nature_photos(f,fetch=fetch,commons=commons,rank=rank),[])
        fetch.assert_not_awaited();commons.assert_not_awaited();rank.assert_not_awaited()
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
