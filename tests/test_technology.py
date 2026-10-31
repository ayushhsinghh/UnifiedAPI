"""Technology contracts, linked diagram models, version-aware photos and media budgets."""
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
APP=Path(__file__).resolve().parents[1]/'app';sys.path.insert(0,str(APP))
package=types.ModuleType('src.facts');package.__path__=[str(APP/'src/facts')];sys.modules.setdefault('src.facts',package)
from src.facts.technology import validate_technology_content,valid_technology_diagram,prepare_technology_media
from src.facts.photo_ranking import select_technology_photos,rank_photos,PhotoRankingUnavailable
from src.facts.lifecycle import fact_image_keys
from test_fact_evidence_lifecycle import routes_module,generator_module
def fixture():return json.loads((Path(__file__).parent/'fixtures/technology_lesson.json').read_text())
def photo(i=0,title='Wireless router',provider='wikimedia'):
    return dict(provider=provider,provider_id=f'{provider}_{i}',url=f'https://upload.wikimedia.org/router{i}.jpg',
        source_url=f'https://commons.wikimedia.org/wiki/File:Router{i}.jpg',title=title,description=title,
        author='Photographer',license='CC BY-SA 4.0',license_url='https://creativecommons.org/licenses/by-sa/4.0/')
class TechnologyContractTests(unittest.TestCase):
    def test_valid_lesson_server_owned_budget_and_zero_photo_mode(self):
        f=fixture();self.assertTrue(validate_technology_content(f));f['images']={'cover':'untrusted'};prepare_technology_media(f)
        self.assertEqual(f['images'],{});self.assertEqual(f['technology_media']['generated_limit'],2)
        self.assertEqual(set(fact_image_keys(f)),{'cover','overview','technology_photo_0',*[f'technology_scene_{n}' for n in range(6)]})
        f['technology_lesson']['photos']=[];self.assertTrue(validate_technology_content(f))
    def test_unresolved_parts_sources_and_invalid_versions_fail(self):
        for mutate in (lambda l:l['system_model']['inputs'][0].update(id='phone'),
            lambda l:l['walkthrough'][0].update(component_ids=['unknown']),
            lambda l:l['walkthrough'][0].update(id='Step One'),
            lambda l:l['walkthrough'][2].update(component_ids=['router','page']),
            lambda l:l['tradeoffs'][0].update(source_ids=['missing']),
            lambda l:l['diagram']['connections'][0].update(to_id='server'),
            lambda l:l['photos'][0].update(component_id='missing'),
            lambda l:l['photos'][0].update(kind='screenshot'),
            lambda l:l.update(version_context=dict(system='Demo',version='2.0',as_of='2020-02-30',scope='Example',source_ids=['s1'])),
            lambda l:l.update(version_context=dict(system='Demo',version='2.0',as_of='9999-01-01',scope='Example',source_ids=['s1']))):
            f=fixture();mutate(f['technology_lesson']);self.assertFalse(validate_technology_content(f))
        f=fixture();f['visual_suggestions']['how_it_works']='Extra image';self.assertFalse(validate_technology_content(f))
    def test_flow_supports_return_paths_and_layers_require_real_dependencies(self):
        l=fixture()['technology_lesson'];self.assertTrue(valid_technology_diagram(l['diagram'],l['system_model']))
        d=l['diagram'];d.update(type='layers',node_ids=[],connections=[],layers=[
            dict(id='upper',title='Upper',role='An example responsibility',component_ids=['phone'],depends_on_ids=['lower']),
            dict(id='lower',title='Lower',role='A supporting responsibility',component_ids=['router','server'],depends_on_ids=[])])
        self.assertTrue(valid_technology_diagram(d,l['system_model']))
        d['layers'][1]['depends_on_ids']=['upper'];self.assertFalse(valid_technology_diagram(d,l['system_model']))
        d.update(type='comparison',layers=[],comparison_basis='The same use case',comparisons=[dict(name='A',approach='One approach',strength='One benefit',limitation='One cost'),dict(name='B',approach='Another approach',strength='Another benefit',limitation='Another cost')])
        self.assertTrue(valid_technology_diagram(d,l['system_model']))
        d['comparison_basis']=None;self.assertFalse(valid_technology_diagram(d,l['system_model']))
class TechnologyAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_ranker_sends_text_system_model_and_binds_scene_ids(self):
        p=photo();payload={'selected':[dict(photo_id=p['provider_id'],score=90,scene='hardware',reason='Metadata identifies the requested router.') ]}
        create=AsyncMock(return_value=types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps(payload)))]))
        client=types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
        selected=await rank_photos(fixture(),[p],client=client)
        self.assertEqual(selected[0]['technology_request_ids'],['hardware'])
        data=json.loads(create.call_args.kwargs['messages'][1]['content']);self.assertIn('system_model',data['lesson']);self.assertNotIn('https://',json.dumps(data['photos']))
    async def test_exact_model_numbers_and_screenshot_versions_are_not_substituted(self):
        f=fixture();f['technology_lesson']['photos'][0].update(kind='named_model',subject='Demo Router 16')
        fetch=AsyncMock(return_value=[]);commons=AsyncMock(return_value=[photo(15,'Demo Router 15'),photo(16,'Demo Router 16')])
        rank=AsyncMock(side_effect=lambda f,photos,**kw:photos)
        selected=await select_technology_photos(f,fetch=fetch,commons=commons,rank=rank)
        fetch.assert_not_awaited();self.assertEqual([p['provider_id'] for p in selected],['wikimedia_16'])
        f['technology_lesson']['version_context']=dict(system='Demo Browser',version='2.0',as_of='2020-01-01',scope='Example',source_ids=['s1'])
        f['technology_lesson']['photos'][0].update(kind='screenshot',subject='Demo Browser')
        commons.return_value=[photo(1,'Demo Browser 2.1'),photo(2,'Demo Browser 2.0')]
        selected=await select_technology_photos(f,fetch=fetch,commons=commons,rank=AsyncMock(side_effect=PhotoRankingUnavailable()))
        self.assertEqual([p['provider_id'] for p in selected],['wikimedia_2'])
    async def test_pure_software_lessons_do_not_force_photo_searches_or_ranking(self):
        f=fixture();f['technology_lesson']['photos']=[];fetch=AsyncMock();commons=AsyncMock();rank=AsyncMock()
        self.assertEqual(await select_technology_photos(f,fetch=fetch,commons=commons,rank=rank),[])
        fetch.assert_not_awaited();commons.assert_not_awaited();rank.assert_not_awaited()
    async def test_worker_keeps_two_generated_credits_and_component_photo_binding(self):
        r=routes_module();f=fixture();prepare_technology_media(f)
        r.generate_and_save_image=AsyncMock(return_value='https://example.org/illustration.jpg');r.track_selection=AsyncMock(return_value=True)
        r.select_technology_photos=AsyncMock(return_value=[{**photo(),'technology_request_ids':['hardware']}])
        await r._background_image_task({**f['visual_suggestions'],'how_it_works':'Ignore extra'},'hash',article=f)
        self.assertEqual(r.generate_and_save_image.await_count,2);r.track_selection.assert_not_awaited()
        credits=[c for c in r.set_fact_image_state.call_args_list if c.kwargs.get('credit')]
        self.assertEqual(sum(c.kwargs['credit'].get('kind')=='generated' for c in credits),2)
        bound=next(c.kwargs['credit'] for c in credits if c.args[1]=='technology_photo_0')
        self.assertEqual(bound['component_id'],'router');self.assertEqual(bound['section_id'],'system')
    async def test_generator_uses_dedicated_stable_global_prompt(self):
        r=generator_module();r.genai.Client.return_value.aio.models.generate_content=AsyncMock(return_value=types.SimpleNamespace(parsed=fixture()))
        result=await r.generate_daily_fact('technology',[])
        self.assertIsNotNone(result);self.assertEqual(result['technology_media']['generated_limit'],2)
        prompt=r.genai.Client.return_value.aio.models.generate_content.call_args.kwargs['contents']
        self.assertIn('No India-first requirement',prompt);self.assertNotIn('INDIA-FIRST RULE',prompt)
