"""Economics evidence status, safe arithmetic, actor links and shared media integration."""
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
APP=Path(__file__).resolve().parents[1]/'app';sys.path.insert(0,str(APP))
package=types.ModuleType('src.facts');package.__path__=[str(APP/'src/facts')];sys.modules.setdefault('src.facts',package)
from src.facts.economics import validate_economics_content,valid_economics_diagram,prepare_economics_media
from src.facts.photo_ranking import select_economics_photos,rank_photos,PhotoRankingUnavailable
from src.facts.lifecycle import fact_image_keys
from src.facts.evidence import normalize_evidence
from src.facts.visual_prompts import build_section_image_context
from test_fact_evidence_lifecycle import routes_module,generator_module
def fixture():return json.loads((Path(__file__).parent/'fixtures/economics_lesson.json').read_text())
def photo(i=0,title='Grocery market',provider='wikimedia'):
    return dict(provider=provider,provider_id=f'{provider}_{i}',url=f'https://upload.wikimedia.org/market{i}.jpg',
        source_url=f'https://commons.wikimedia.org/wiki/File:Market{i}.jpg',title=title,description=title,
        author='Photographer',license='CC BY-SA 4.0',license_url='https://creativecommons.org/licenses/by-sa/4.0/')
class EconomicsContractTests(unittest.TestCase):
    def test_valid_contract_optional_sections_and_server_owned_media(self):
        f=fixture();self.assertTrue(validate_economics_content(f));f['images']={'cover':'untrusted'};prepare_economics_media(f)
        self.assertEqual(f['images'],{});self.assertEqual(f['economics_media']['generated_limit'],2)
        self.assertEqual(f['economics_validation']['data_verification'],'not_performed')
        self.assertEqual(set(fact_image_keys(f)),{'cover','overview','economics_photo_0',*[f'economics_scene_{n}' for n in range(6)]})
        l=f['economics_lesson'];l.update(diagram=None,photos=[],distributional_effects=[],optional_depth=[])
        l['worked_example'].update(values=[],calculations=[]);self.assertTrue(validate_economics_content(f))
    def test_invalid_arithmetic_actor_references_sources_and_photo_sections_fail(self):
        for mutate in (lambda l:l['worked_example']['calculations'][0].update(result=6),
            lambda l:l['worked_example']['calculations'][0].update(operand_ids=['after-count','before-price']),
            lambda l:l['worked_example']['values'][1].update(value=0),
            lambda l:l['worked_example']['values'][0].update(value=True),
            lambda l:l['worked_example']['values'][0].update(value=float('inf')),
            lambda l:l['worked_example']['values'][0].update(value=1e16),
            lambda l:l['mechanism']['steps'][0].update(actor_ids=['unknown']),
            lambda l:l['mechanism']['steps'][0].update(conditions=[]),
            lambda l:l['mechanism']['actors'][0].update(id='seller'),
            lambda l:l['distributional_effects'][0].update(actor_id='unknown'),
            lambda l:l['conditions_and_limits'][0].update(source_ids=['unknown']),
            lambda l:l['photos'][0].update(section_id='case'),
            lambda l:l['diagram']['series'][0].update(values=[5])):
            f=fixture();mutate(f['economics_lesson']);self.assertFalse(validate_economics_content(f))
        f=fixture();f['visual_suggestions']['how_it_works']='extra';self.assertFalse(validate_economics_content(f))
    def test_observed_data_requires_nonfuture_real_date_region_and_period(self):
        f=fixture();p=f['economics_lesson']['diagram']['provenance'];p['kind']='observed'
        self.assertFalse(validate_economics_content(f))
        p.update(period='2020',geography='Demonstration region',as_of='2020-12-31');self.assertTrue(validate_economics_content(f))
        for day in ('2020-02-30','9999-01-01'):
            p['as_of']=day;self.assertFalse(validate_economics_content(f))
    def test_comparison_and_signed_line_data_have_valid_shapes(self):
        d=fixture()['economics_lesson']['diagram'];d.update(type='line');d['series'][0]['values']=[0,-1]
        self.assertTrue(valid_economics_diagram(d))
        d.update(type='comparison',labels=[],series=[],x_label=None,unit=None,comparison_basis='The same use of a fixed budget',comparisons=[
            dict(name='A',approach='One choice',benefit='One benefit',cost='One cost',conditions='One condition'),
            dict(name='B',approach='Another choice',benefit='Another benefit',cost='Another cost',conditions='Another condition')])
        self.assertTrue(valid_economics_diagram(d));d['comparison_basis']=None;self.assertFalse(valid_economics_diagram(d))
    def test_evidence_links_and_visual_context_include_economics(self):
        f=fixture();normalize_evidence(f)
        self.assertTrue(f['economics_lesson']['identity']['source_ids'])
        context=build_section_image_context('overview',f)
        self.assertIn('economics_context',str(context));self.assertIn('Purchasing power',str(context))
class EconomicsAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_ranker_uses_text_only_and_exact_request_ids(self):
        p=photo();payload={'selected':[dict(photo_id=p['provider_id'],score=90,scene='market',reason='Metadata identifies a grocery market.') ]}
        create=AsyncMock(return_value=types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps(payload)))]))
        client=types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
        selected=await rank_photos(fixture(),[p],client=client)
        self.assertEqual(selected[0]['economics_request_ids'],['market'])
        data=json.loads(create.call_args.kwargs['messages'][1]['content']);self.assertIn('mechanism',data['lesson'])
        self.assertNotIn('https://',json.dumps(data['photos']));self.assertEqual(create.call_args.kwargs['model'],'gpt-6-luna')
    async def test_missing_photos_do_not_call_providers(self):
        f=fixture();f['economics_lesson']['photos']=[];fetch=AsyncMock();commons=AsyncMock();rank=AsyncMock()
        self.assertEqual(await select_economics_photos(f,fetch=fetch,commons=commons,rank=rank),[])
        fetch.assert_not_awaited();commons.assert_not_awaited();rank.assert_not_awaited()
    async def test_named_people_stay_commons_only_and_fallback_keeps_subject_match(self):
        f=fixture();f['economics_lesson']['photos'][0].update(kind='person',subject='Demonstration Economist')
        fetch=AsyncMock(return_value=[photo(1,'Generic portrait','unsplash')]);commons=AsyncMock(return_value=[photo(2,'Demonstration Economist'),photo(3,'Generic portrait')])
        selected=await select_economics_photos(f,fetch=fetch,commons=commons,rank=AsyncMock(side_effect=PhotoRankingUnavailable()))
        fetch.assert_not_awaited();self.assertEqual([p['provider_id'] for p in selected],['wikimedia_2'])
    async def test_worker_caps_generation_and_binds_editorial_images(self):
        r=routes_module();f=fixture();prepare_economics_media(f)
        r.generate_and_save_image=AsyncMock(return_value='https://example.org/illustration.jpg');r.track_selection=AsyncMock(return_value=True)
        r.select_economics_photos=AsyncMock(return_value=[{**photo(),'economics_request_ids':['market']}])
        await r._background_image_task({**f['visual_suggestions'],'how_it_works':'Ignore extra'},'hash',article=f)
        self.assertEqual(r.generate_and_save_image.await_count,2);r.track_selection.assert_not_awaited()
        credits=[c for c in r.set_fact_image_state.call_args_list if c.kwargs.get('credit')]
        self.assertEqual(sum(c.kwargs['credit'].get('kind')=='generated' for c in credits),2)
        bound=next(c.kwargs['credit'] for c in credits if c.args[1]=='economics_photo_0')
        self.assertEqual(bound['section_id'],'overview');self.assertEqual(bound['photo_id'],'market')
    async def test_generator_uses_dedicated_global_prompt(self):
        r=generator_module();r.genai.Client.return_value.aio.models.generate_content=AsyncMock(return_value=types.SimpleNamespace(parsed=fixture()))
        result=await r.generate_daily_fact('economics',[])
        self.assertIsNotNone(result);self.assertEqual(result['economics_media']['generated_limit'],2)
        prompt=r.genai.Client.return_value.aio.models.generate_content.call_args.kwargs['contents']
        self.assertIn('No India-first requirement',prompt);self.assertNotIn('INDIA-FIRST RULE',prompt)
