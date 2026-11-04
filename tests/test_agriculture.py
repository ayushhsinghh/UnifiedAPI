"""Agriculture contract, diagram/data provenance and shared asynchronous media checks."""
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
APP=Path(__file__).resolve().parents[1]/'app';sys.path.insert(0,str(APP))
package=types.ModuleType('src.facts');package.__path__=[str(APP/'src/facts')];sys.modules.setdefault('src.facts',package)
from src.facts.agriculture import validate_agriculture_content,valid_agriculture_diagram,prepare_agriculture_media
from src.facts.photo_ranking import select_agriculture_photos,rank_photos,PhotoRankingResult
from src.facts.lifecycle import fact_image_keys
from test_fact_evidence_lifecycle import routes_module,generator_module
from test_photo_ranking import photo as unsplash_photo
def fixture():return json.loads((Path(__file__).parent/'fixtures/agriculture_lesson.json').read_text())
def photo(i=0):
    return dict(provider='wikimedia',provider_id=f'commons_{i}',url=f'https://upload.wikimedia.org/straw{i}.jpg',
        source_url=f'https://commons.wikimedia.org/wiki/File:Straw{i}.jpg',title='Straw mulch',description='Straw mulch cover',
        author='Photographer',license='CC BY-SA 4.0',license_url='https://creativecommons.org/licenses/by-sa/4.0/')
class AgricultureContractTests(unittest.TestCase):
    def test_valid_contract_server_owned_budget_and_optional_fields(self):
        f=fixture();self.assertTrue(validate_agriculture_content(f));prepare_agriculture_media(f)
        self.assertEqual(f['agriculture_media']['generated_limit'],2)
        self.assertEqual(f['agriculture_validation']['agronomic_verification'],'not_performed')
        self.assertEqual(set(fact_image_keys(f)),{'cover','overview','agriculture_photo_0',*[f'agriculture_scene_{n}' for n in range(6)]})
        f['agriculture_lesson'].update(diagram=None,photos=[],measurements=[],optional_depth=[],key_terms=[])
        f['agriculture_lesson']['field_context'].update(crops=[],growing_conditions=[],when_it_matters=None)
        self.assertTrue(validate_agriculture_content(f))
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
        rank=AsyncMock(side_effect=[PhotoRankingResult([], [{'scene':'residue','query':'mulch'}]),[{**p,'agriculture_request_ids':['residue']} ]])
        result=await select_agriculture_photos(fixture(),fetch=AsyncMock(return_value=photos),commons=AsyncMock(return_value=[p]),rank=rank)
        self.assertEqual(rank.await_count,2);self.assertEqual(result[0]['provider'],'wikimedia')
        self.assertTrue(all(p['popular_pick'] and p['agriculture_request_ids']==[] for p in result[-3:]))
    async def test_no_documentary_requests_make_no_provider_or_ranker_calls(self):
        f=fixture();f['agriculture_lesson']['photos']=[];fetch=AsyncMock();commons=AsyncMock();rank=AsyncMock()
        self.assertEqual(await select_agriculture_photos(f,fetch=fetch,commons=commons,rank=rank),[])
        fetch.assert_not_awaited();commons.assert_not_awaited();rank.assert_not_awaited()
    async def test_worker_caps_ai_images_and_preserves_step_binding(self):
        r=routes_module();f=fixture();prepare_agriculture_media(f)
        r.generate_and_save_image=AsyncMock(return_value='https://example.org/illustration.jpg')
        r.select_agriculture_photos=AsyncMock(return_value=[{**photo(),'agriculture_request_ids':['residue']}])
        await r._background_image_task({**f['visual_suggestions'],'how_it_works':'Ignore'},'hash',article=f)
        self.assertEqual(r.generate_and_save_image.await_count,2)
        calls=[c for c in r.set_fact_image_state.call_args_list if c.kwargs.get('credit')]
        self.assertEqual(sum(c.kwargs['credit'].get('kind')=='generated' for c in calls),2)
        bound=next(c.kwargs['credit'] for c in calls if c.args[1]=='agriculture_photo_0')
        self.assertEqual(bound['step_id'],'cover');self.assertEqual(bound['section_id'],'process')
    async def test_generator_selects_indian_concept_prompt_and_prepares_media(self):
        r=generator_module();r.genai.Client.return_value.aio.models.generate_content=AsyncMock(return_value=types.SimpleNamespace(parsed=fixture()))
        result=await r.generate_daily_fact('agriculture',[])
        self.assertIsNotNone(result);self.assertEqual(result['agriculture_media']['generated_limit'],2)
        prompt=r.genai.Client.return_value.aio.models.generate_content.call_args.kwargs['contents']
        self.assertIn('rooted in Indian agriculture',prompt);self.assertIn('no single growing season',prompt)
