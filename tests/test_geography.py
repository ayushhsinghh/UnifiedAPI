"""Geography contracts, diagram topology, location references and bounded image work."""
import json
import sys
import types
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import AsyncMock
APP=Path(__file__).resolve().parents[1]/'app';sys.path.insert(0,str(APP))
package=types.ModuleType('src.facts');package.__path__=[str(APP/'src/facts')];sys.modules.setdefault('src.facts',package)
from src.facts.geography import validate_geography_content,valid_geography_diagram,prepare_geography_media
from src.facts.photo_ranking import select_geography_photos,rank_photos,PhotoRankingUnavailable
from src.facts.lifecycle import fact_image_keys,image_generation_state
from test_fact_evidence_lifecycle import routes_module,generator_module
def fixture():return json.loads((Path(__file__).parent/'fixtures/geography_lesson.json').read_text())
def photo(i=0,provider='wikimedia'):
    return dict(provider=provider,provider_id=f'{provider}_{i}',url=f'https://upload.wikimedia.org/valley{i}.jpg',
        source_url=f'https://commons.wikimedia.org/wiki/File:Valley{i}.jpg',title='Owens Valley',description='Owens Valley in California',
        author='Photographer',license='CC BY-SA 4.0',license_url='https://creativecommons.org/licenses/by-sa/4.0/')
class GeographyContractTests(unittest.TestCase):
    def test_valid_contract_media_budget_and_timeout(self):
        f=fixture();self.assertTrue(validate_geography_content(f));prepare_geography_media(f)
        self.assertEqual(f['geography_media']['generated_limit'],2)
        self.assertEqual(set(fact_image_keys(f)),{'cover','overview','geography_photo_0','geography_photo_1',*[f'geography_scene_{n}' for n in range(6)]})
        state=image_generation_state({'full_response':f,'image_started_at':datetime.now(timezone.utc)-timedelta(seconds=400),
            'image_status':dict.fromkeys(fact_image_keys(f),'processing')},300)
        self.assertEqual(state['status'],'processing');self.assertEqual(state['timeout_seconds'],720)
    def test_invalid_coordinates_references_and_disconnected_diagrams_fail(self):
        for mutate in (lambda l:l['location_context']['locations'][0].update(latitude=91),
            lambda l:l['location_context']['locations'][0].update(longitude=float('nan')),
            lambda l:l['case_study'].update(location_id='missing'),
            lambda l:l['map'].update(location_ids=['west']),
            lambda l:l['diagram']['connections'][0].update(to_id='missing'),
            lambda l:l['diagram']['connections'][0].update(label=''),
            lambda l:l['diagram']['profile'][1].update(x=0),
            lambda l:l['diagram']['nodes'][0].update(source_ids=['missing']),
            lambda l:l['photos'][1].update(location_id=None),
            lambda l:l['explanation_steps'][0].update(source_ids=['missing'])):
            f=fixture();mutate(f['geography_lesson']);self.assertFalse(validate_geography_content(f))
        f=fixture();f['visual_suggestions']['how_it_works']='Unexpected extra';self.assertFalse(validate_geography_content(f))
    def test_optional_map_diagram_and_human_sections_can_be_omitted(self):
        f=fixture();f['geography_lesson'].update(map=None,diagram=None,human_connections=[],variations=[],misconceptions=[],limits=[])
        self.assertTrue(validate_geography_content(f))
    def test_comparison_and_causal_diagrams_have_meaningful_structure(self):
        d=fixture()['geography_lesson']['diagram'];d.update(type='cause_effect',profile=[])
        self.assertTrue(valid_geography_diagram(d))
        reverse=json.loads(json.dumps(d));reverse['connections'].append(dict(from_id='rising',to_id='moist',label='Return flow'))
        self.assertFalse(valid_geography_diagram(reverse))
        d['connections'][1]['to_id']='moist';self.assertFalse(valid_geography_diagram(d))
        d=fixture()['geography_lesson']['diagram'];d.update(type='comparison',profile=[],nodes=[],connections=[],comparisons=[dict(label='Moist side',conditions='Incoming airflow',explanation='Air is lifted.'),dict(label='Sheltered side',conditions='Beyond the ridge',explanation='Air can be drier.')])
        self.assertTrue(valid_geography_diagram(d));d['comparisons']=[];self.assertFalse(valid_geography_diagram(d))
class GeographyAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_ranker_uses_text_and_location_context_and_valid_scene_ids(self):
        p=photo();result={'selected':[dict(photo_id=p['provider_id'],score=90,scene='valley',reason='Metadata identifies the named valley.')]}
        create=AsyncMock(return_value=types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps(result)))]))
        client=types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
        selected=await rank_photos(fixture(),[p],client=client)
        self.assertEqual(selected[0]['geography_request_ids'],['valley'])
        request=create.call_args.kwargs;self.assertEqual(request['model'],'gpt-6-luna')
        data=json.loads(request['messages'][1]['content']);self.assertIn('location_context',data['lesson']);self.assertNotIn('https://',json.dumps(data['photos']))
    async def test_named_places_and_satellite_requests_never_use_stock(self):
        f=fixture();f['geography_lesson']['photos'][1]['kind']='satellite'
        fetch=AsyncMock(return_value=[photo(1,'unsplash')]);commons=AsyncMock(return_value=[photo()])
        rank=AsyncMock(return_value=[{**photo(1,'unsplash'),'geography_request_ids':['valley']},{**photo(),'geography_request_ids':['valley']}])
        selected=await select_geography_photos(f,fetch=fetch,commons=commons,rank=rank)
        self.assertEqual(fetch.await_count,1);self.assertEqual(commons.await_count,2)
        self.assertEqual(len(selected),1);self.assertEqual(selected[0]['provider'],'wikimedia')
    async def test_fallback_keeps_only_matching_location_request(self):
        selected=await select_geography_photos(fixture(),fetch=AsyncMock(return_value=[photo()]),commons=AsyncMock(return_value=[photo()]),
            rank=AsyncMock(side_effect=PhotoRankingUnavailable()))
        self.assertEqual(selected[0]['geography_request_ids'],['valley'])
    async def test_worker_preserves_generated_labels_budget_and_location_binding(self):
        r=routes_module();f=fixture();prepare_geography_media(f)
        r.generate_and_save_image=AsyncMock(return_value='https://example.org/illustration.jpg');r.track_selection=AsyncMock(return_value=True)
        r.select_geography_photos=AsyncMock(return_value=[{**photo(),'geography_request_ids':['valley']}])
        await r._background_image_task({**f['visual_suggestions'],'how_it_works':'Ignore'},'hash',article=f)
        self.assertEqual(r.generate_and_save_image.await_count,2);r.track_selection.assert_not_awaited()
        credits=[c for c in r.set_fact_image_state.call_args_list if c.kwargs.get('credit')]
        self.assertEqual(sum(c.kwargs['credit'].get('kind')=='generated' for c in credits),2)
        bound=next(c.kwargs['credit'] for c in credits if c.args[1]=='geography_photo_1')
        self.assertEqual(bound['location_id'],'east');self.assertEqual(bound['section_id'],'case-study')
    async def test_generator_uses_global_geography_contract(self):
        r=generator_module();r.genai.Client.return_value.aio.models.generate_content=AsyncMock(return_value=types.SimpleNamespace(parsed=fixture()))
        result=await r.generate_daily_fact('geography',[])
        self.assertIsNotNone(result);self.assertEqual(result['geography_media']['generated_limit'],2)
        prompt=r.genai.Client.return_value.aio.models.generate_content.call_args.kwargs['contents']
        self.assertIn('No India-first requirement',prompt);self.assertNotIn('INDIA-FIRST RULE',prompt)
