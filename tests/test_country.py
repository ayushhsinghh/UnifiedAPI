"""Offline country schema, truthful data, media budget and licensed-photo worker checks."""
import copy
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

APP=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(APP))
package=types.ModuleType('src.facts');package.__path__=[str(APP/'src/facts')]
sys.modules.setdefault('src.facts',package)
from src.facts.country import COUNTRY_RESPONSE_SCHEMA, PHOTO_KEYS, validate_country_content, validate_country_images, enrich_country_identity, build_country_prompt, COUNTRY_IMAGE_INSTRUCTIONS
from src.facts.country_photos import photo_candidates, _lookup
from src.facts.lifecycle import expected_image_keys

def fixture(): return json.loads((Path(__file__).parent/'fixtures/country_profile.json').read_text())
def candidate(licence='CC BY-SA 4.0'):
    return {'query':{'pages':{'1':{'index':1,'title':'File:An actual place.jpg','imageinfo':[{'mime':'image/jpeg','thumburl':'https://upload.wikimedia.org/photo.jpg','descriptionurl':'https://commons.wikimedia.org/wiki/File:Photo.jpg','extmetadata':{'Artist':{'value':'<a>Actual author</a>'},'LicenseShortName':{'value':licence},'LicenseUrl':{'value':'https://creativecommons.org/licenses/by-sa/4.0/'},'ImageDescription':{'value':'<p>A place in the country.</p>'}}}]}}}}

class CountryContractTests(unittest.TestCase):
    def test_country_shape_identity_and_snapshot_ownership(self):
        f=fixture();self.assertTrue(validate_country_content(f))
        f['country_profile']['identity']['name']='Another country'
        self.assertFalse(validate_country_content(f))
        f=fixture();f['country_profile']['data_context']={'currency_check':'verified'};f['images']={'cover':'invented'}
        enrich_country_identity(f)
        self.assertEqual(f['country_profile']['identity']['iso3'],'JPN')
        self.assertEqual(f['country_profile']['identity']['flag_url'],'https://flagcdn.com/w320/jp.png')
        self.assertEqual(f['country_profile']['data_context']['currency_check'],'not_performed')
        self.assertEqual(f['images'],{})
        self.assertEqual(f['country_validation']['generated_image_limit'],4)
        self.assertEqual(f['country_media']['generated_slots'],list(PHOTO_KEYS[:4]))

    def test_sources_population_year_and_minimum_learning_content(self):
        mutations=[lambda p:p['introduction'].update(source_ids=['missing']),lambda p:p['essentials']['population'].update(value=100,year=None),
            lambda p:p['essentials']['population'].update(value=-1,year=2020),lambda p:p['essentials']['population'].update(value=100,year=9999),
            lambda p:p.update(notable_people=[]),lambda p:p.update(notable_places=[]),lambda p:p['identity'].update(iso2='ZZ')]
        for mutate in mutations:
            f=fixture();mutate(f['country_profile']);self.assertFalse(validate_country_content(f))
        f=fixture();f['country_profile']['essentials']['population'].update(value=123,year=2020)
        self.assertTrue(validate_country_content(f))

    def test_four_generation_slots_and_separate_photo_queries(self):
        f=fixture()
        self.assertTrue(validate_country_images(f))
        for key in ('how_it_works','explanation_2'):
            f['visual_suggestions'][key]=''
        f['image_details']=[d for d in f['image_details'] if d['slot'] not in ('how_it_works','explanation_2')]
        self.assertTrue(validate_country_images(f))
        f['visual_suggestions']['cover']='';self.assertFalse(validate_country_images(f))
        f=fixture()
        f['visual_suggestions']['ninth_photo']='Another';self.assertFalse(validate_country_images(f))
        f=fixture();f['image_details'].pop();self.assertFalse(validate_country_images(f))

    def test_prompt_and_reusable_photo_metadata(self):
        self.assertIn('excluded',build_country_prompt(['excluded']))
        self.assertIn('at most FOUR',COUNTRY_IMAGE_INSTRUCTIONS)
        photos=photo_candidates(candidate());self.assertEqual(photos[0]['author'],'Actual author')
        self.assertNotIn('<',photos[0]['description'])
        self.assertEqual(photo_candidates(candidate('All rights reserved')),[])
        data=candidate();data['query']['pages']['1']['imageinfo'][0]['thumburl']='https://attacker.example/image.jpg'
        self.assertEqual(photo_candidates(data),[])

    def test_search_falls_back_to_simpler_country_specific_queries(self):
        payload=candidate();payload['query']['pages']['1']['title']='File:Japan landscape.jpg'
        class Response:
            status_code=200
            def __init__(self,payload):self.payload=payload
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def iter_content(self,size):return iter([json.dumps(self.payload).encode()])
        with patch('requests.get',side_effect=[Response({}),Response({}),Response(payload)]) as request:
            photos=_lookup('Japan','Japan very specific landscape beach rainforest')
        self.assertEqual(len(photos),1)
        searches=[call.kwargs['params']['gsrsearch'] for call in request.call_args_list]
        self.assertEqual(len(searches),3)
        self.assertTrue(all('intitle:"Japan"' in q for q in searches))
        self.assertLess(len(searches[-1]),len(searches[0]))
        data=candidate();data['query']['pages']['1']['imageinfo'][0]['extmetadata']['Artist']['value']=''
        self.assertEqual(photo_candidates(data),[])

class CountryGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_routing_retry_and_photo_budget_contract(self):
        from test_fact_evidence_lifecycle import generator_module
        g=generator_module();g.COUNTRY_RESPONSE_SCHEMA=COUNTRY_RESPONSE_SCHEMA;g.validate_country_content=validate_country_content
        g.validate_image_plan=lambda f,**kwargs:validate_country_images(f);g.enrich_country_identity=enrich_country_identity
        invalid=fixture();invalid['country_profile']['identity']['name']='Mismatch'
        create=AsyncMock(side_effect=[types.SimpleNamespace(parsed=invalid),types.SimpleNamespace(parsed=fixture())])
        g.genai.Client.return_value.aio.models.generate_content=create
        with patch.object(g.asyncio,'sleep',new=AsyncMock()):result=await g.generate_daily_fact('country')
        self.assertEqual(create.call_count,2);self.assertIs(create.call_args.kwargs['config']['response_schema'],COUNTRY_RESPONSE_SCHEMA)
        self.assertEqual(result['country_profile']['identity']['iso3'],'JPN')

    async def test_country_worker_uses_licensed_photos_not_paid_generation(self):
        from test_fact_evidence_lifecycle import routes_module
        routes=routes_module();photo=photo_candidates(candidate())[0]
        routes.find_country_photos=AsyncMock(return_value=[photo])
        routes.generate_and_save_image=AsyncMock()
        f=enrich_country_identity(fixture());f.pop('country_media')
        await routes._background_image_task({'cover':'Japan mountain'},'hash',article=f)
        routes.generate_and_save_image.assert_not_awaited()
        call=routes.set_fact_image_state.call_args
        self.assertEqual(call.args[2],'ready');self.assertEqual(call.kwargs['credit']['license'],'CC BY-SA 4.0')
        await routes._background_image_task({'cover':'Invalid country'},'hash',article={'article_type':'country_profile','country_profile':{}})
        routes.generate_and_save_image.assert_not_awaited()
        self.assertEqual(routes.set_fact_image_state.call_args.args[2],'failed')

    async def test_hybrid_worker_caps_generated_images_and_keeps_gallery_credits(self):
        from test_fact_evidence_lifecycle import routes_module
        routes=routes_module();photo=photo_candidates(candidate())[0]
        routes.find_country_photos=AsyncMock(return_value=[photo])
        routes.generate_and_save_image=AsyncMock(side_effect=lambda prompt,filename,**kwargs:'https://images.example/'+filename)
        f=enrich_country_identity(fixture())
        await routes._background_image_task({**f['visual_suggestions'],'myth_visual':'Never generate this fifth image'},'hash',article=f)
        self.assertEqual(routes.generate_and_save_image.await_count,4)
        self.assertEqual(routes.find_country_photos.await_count,12)
        credits=[c.kwargs.get('credit') for c in routes.set_fact_image_state.call_args_list]
        self.assertEqual(sum(bool(c and c.get('kind')=='generated') for c in credits),4)
        galleries=[c.kwargs.get('gallery') for c in routes.set_fact_image_state.call_args_list if c.kwargs.get('gallery')]
        self.assertEqual(galleries[0][0]['license'],'CC BY-SA 4.0')

if __name__=='__main__':unittest.main()
