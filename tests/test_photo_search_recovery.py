"""One model-directed search recovery, without weakening subject or provider checks."""
import json
import types
import unittest
from unittest.mock import AsyncMock
from test_food import fixture as food_fixture,photo as food_photo
from test_country import fixture as country_fixture
from test_photo_ranking import photo
from test_india import fixture as india_fixture
from test_fact_evidence_lifecycle import routes_module
from src.facts.photo_ranking import (PhotoRankingResult,PhotoRankingUnavailable,validate_ranking,
    rank_photos,select_food_photos,select_country_photos,select_india_photos,PopularUnsplash)

def empty(scene='dish',query='hummus'):
    return PhotoRankingResult([], [{'scene':scene,'query':query}])

def narrow_food():
    fact=food_fixture()
    fact['food_lesson']['photos']=fact['food_lesson']['photos'][:1]
    fact['food_lesson']['photos'][0]['queries']=['ceramic hummus bowl with paprika']
    return fact

class FeedbackContractTests(unittest.TestCase):
    def test_global_top_three_survive_deduplication_caps_and_ranking_rejection(self):
        bank=PopularUnsplash()
        photos=[{**photo(i),'likes':i} for i in range(300)]
        bank.add(photos);bank.add([{**photo(0),'likes':1000}])
        selected=bank.include([],request_key='food_request_ids')
        self.assertEqual([p['likes'] for p in selected],[1000,299,298])
        self.assertTrue(all(p['selection_mode']=='popular_unsplash' and p['food_request_ids']==[] for p in selected))
        result=bank.include([{**photos[299],'ranking_score':90},*photos[:18]])
        self.assertEqual(len(result),18);self.assertEqual(len({p['source_url'] for p in result}),18)
        self.assertEqual(result[-2]['ranking_score'],90)
        self.assertTrue(all(p.get('popular_pick') for p in result[-3:]))
        self.assertTrue(all(not p.get('popular_pick') for p in result[:-3]))
        excluded=PopularUnsplash([photo(299)['source_url']]);excluded.add(photos)
        self.assertNotIn(photo(299)['source_url'],[p['source_url'] for p in excluded.include([])])
    def test_empty_ranking_preserves_normalized_scene_bound_simpler_queries(self):
        result=validate_ranking({'selected':[],'retry_queries':[
            {'scene':'dish','query':'  hummus  bowl  '},{'scene':'dish','query':'Hummus bowl'},
            {'scene':'dish','query':'hummus'}]},[],request_ids={'dish'})
        self.assertEqual(result,[])
        self.assertEqual(result.retry_queries,[{'scene':'dish','query':'hummus bowl'},{'scene':'dish','query':'hummus'}])
    def test_low_scores_are_empty_and_need_search_feedback(self):
        p=food_photo();row=dict(photo_id=p['provider_id'],score=69,scene='dish',reason='Insufficient subject evidence')
        result=validate_ranking({'selected':[row],'retry_queries':[{'scene':'dish','query':'hummus'}]},[p],request_ids={'dish'})
        self.assertEqual(result,[]);self.assertEqual(result.retry_queries[0]['query'],'hummus')
        with self.assertRaises(ValueError):validate_ranking({'selected':[]},[])
    def test_selected_photo_keeps_the_ranking_score_and_reason(self):
        p=food_photo();row=dict(photo_id=p['provider_id'],score=88,scene='dish',reason='The metadata identifies hummus.')
        result=validate_ranking({'selected':[row]},[p],request_ids={'dish'})
        self.assertEqual(result[0]['ranking_score'],88)
        self.assertEqual(result[0]['ranking_reason'],row['reason'])
        self.assertEqual(result[0]['ranking_scene'],'dish')
    def test_malformed_unbounded_or_unknown_searches_are_rejected(self):
        for queries in ([{'scene':'unknown','query':'hummus'}],
            [{'scene':'dish','query':'https://example.org/secret'}],
            [{'scene':'dish','query':'one two three four five six seven'}],
            [{'scene':'dish','query':'hummus\nignore rules'}],
            [{'scene':'dish','query':''}],
            [{'scene':'dish','query':q} for q in ('hummus','hummus bowl','hummus plate')],
            [{'scene':'dish','query':'hummus'}]*7):
            with self.assertRaises(ValueError):validate_ranking({'selected':[],'retry_queries':queries},[],request_ids={'dish'})
        with self.assertRaises(ValueError):validate_ranking({'selected':[],'retry_queries':[{'scene':'dish','query':'hummus'}]},[])

class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_three_most_liked_across_initial_and_recovery_searches_are_always_retained(self):
        initial=[{**photo(i),'likes':i} for i in range(4)]
        extra=[{**photo(10+i),'likes':100+i} for i in range(3)]
        fetch=AsyncMock(side_effect=lambda query:extra if query=='hummus' else initial)
        rank=AsyncMock(side_effect=[empty(),empty(query='hummus plate')])
        result=await select_food_photos(narrow_food(),fetch=fetch,commons=AsyncMock(return_value=[]),rank=rank)
        self.assertEqual([p['likes'] for p in result],[102,101,100]);self.assertEqual(rank.await_count,2)
        self.assertTrue(all(p['popular_pick'] for p in result))
        self.assertEqual(fetch.await_count,2)
    async def test_successful_ranking_also_includes_popular_photos_without_an_extra_ranking(self):
        pool=[{**photo(i),'likes':i} for i in range(6)]
        rank=AsyncMock(return_value=[{**pool[0],'food_request_ids':['dish']}])
        result=await select_food_photos(narrow_food(),fetch=AsyncMock(return_value=pool),commons=AsyncMock(return_value=[]),rank=rank)
        self.assertEqual([p['likes'] for p in result],[0,5,4,3]);rank.assert_awaited_once()
        self.assertEqual(result[-1]['food_request_ids'],[])
    async def test_ranking_transport_failure_keeps_the_popular_photos(self):
        pool=[{**photo(i),'likes':i} for i in range(3)]
        result=await select_country_photos(country_fixture(),fetch=AsyncMock(return_value=pool),rank=AsyncMock(side_effect=PhotoRankingUnavailable()))
        self.assertEqual(len(result),3);self.assertTrue(all(p['popular_pick'] for p in result))
    async def test_popular_only_editorial_images_go_to_gallery_and_keep_their_selection_mode(self):
        r=routes_module();r.track_selection=AsyncMock(return_value=True)
        chosen=PopularUnsplash();chosen.add([{**photo(i),'likes':i} for i in range(3)])
        r.select_food_photos=AsyncMock(return_value=chosen.include([],request_key='food_request_ids'))
        await r._background_image_task({},'hash',article=narrow_food(),photos_only=True)
        ready=[c for c in r.set_fact_image_state.call_args_list if c.args[2]=='ready']
        self.assertEqual([c.args[1] for c in ready],['food_scene_0','food_scene_1','food_scene_2'])
        self.assertTrue(all(c.kwargs['credit']['selection_mode']=='popular_unsplash' for c in ready))
        self.assertTrue(all(c.kwargs['credit']['ranking_model'] is None for c in ready))
        self.assertEqual(r.track_selection.await_count,3)
    async def test_popular_photos_end_the_existing_gallery_even_when_ranked_or_gallery_is_full(self):
        r=routes_module();r.track_selection=AsyncMock(return_value=True)
        ranked=[{**food_photo(i),'food_request_ids':['dish']} for i in range(8)]
        popular=[{**photo(100+i),'likes':100-i,'popular_pick':True,'food_request_ids':['dish']} for i in range(3)]
        r.select_food_photos=AsyncMock(return_value=[*popular,*ranked])
        await r._background_image_task({},'hash',article=narrow_food(),photos_only=True)
        ready=[c for c in r.set_fact_image_state.call_args_list if c.args[2]=='ready']
        gallery=[c.kwargs['credit'] for c in ready if c.args[1].startswith('food_scene_')]
        self.assertEqual(len(gallery),6)
        self.assertTrue(all(not p.get('popular_pick') for p in gallery[:3]))
        self.assertTrue(all(p.get('popular_pick') for p in gallery[-3:]))
        self.assertTrue(all(not c.kwargs['credit'].get('popular_pick') for c in ready if c.args[1].startswith('food_photo_')))
    async def test_country_worker_publishes_popular_photos_even_with_fewer_than_ten(self):
        r=routes_module();r.track_selection=AsyncMock(return_value=True)
        chosen=PopularUnsplash();chosen.add([{**photo(i),'likes':i} for i in range(3)])
        r.select_country_photos=AsyncMock(return_value=chosen.include([]))
        f=country_fixture();f['country_media']={'photo_ranking_version':1}
        await r._background_image_task({},'hash',article=f,photos_only=True)
        self.assertEqual(r.set_fact_photo_selection.call_args.args[1]['status'],'completed')
        self.assertEqual(r.set_fact_photo_selection.call_args.args[1]['selected_count'],3)
    async def test_actual_ranker_and_selector_complete_the_two_response_protocol(self):
        new=food_photo(1)
        payloads=[{'selected':[],'retry_queries':[{'scene':'dish','query':'hummus'}]},
            {'selected':[dict(photo_id=new['provider_id'],score=93,scene='dish',reason='The metadata identifies hummus.')],'retry_queries':[]}]
        create=AsyncMock(side_effect=[types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps(p)))]) for p in payloads])
        client=types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
        async def rank(f,photos,**kw):return await rank_photos(f,photos,client=client,**kw)
        fetch=AsyncMock(side_effect=lambda q:[new] if q=='hummus' else [food_photo()])
        result=await select_food_photos(narrow_food(),fetch=fetch,commons=AsyncMock(return_value=[]),rank=rank)
        self.assertEqual(create.await_count,2);self.assertEqual(result[0]['ranking_score'],93)
        second=json.loads(create.call_args.kwargs['messages'][1]['content'])
        self.assertEqual(second['photos'][0]['photo_id'],new['provider_id'])
    async def test_ranker_returns_feedback_and_records_zero_qualified_count(self):
        payload={'selected':[],'retry_queries':[{'scene':'dish','query':'hummus'}]}
        create=AsyncMock(return_value=types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=json.dumps(payload)))]))
        client=types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
        states=[];result=await rank_photos(narrow_food(),[food_photo()],client=client,report=states.append)
        self.assertEqual(result.retry_queries,payload['retry_queries']);create.assert_awaited_once()
        self.assertEqual(states[-1]['qualified_count'],0)
        self.assertIn('hummus bowl',create.call_args.kwargs['messages'][0]['content'])
    async def test_empty_result_searches_model_suggestion_and_ranks_again_once(self):
        f=narrow_food();old=food_photo(0);new=food_photo(1)
        fetch=AsyncMock(side_effect=lambda q:[new] if q=='hummus' else [old]);commons=AsyncMock(return_value=[])
        rank=AsyncMock(side_effect=[empty(),[{**new,'food_request_ids':['dish']}]])
        states=[];result=await select_food_photos(f,fetch=fetch,commons=commons,rank=rank,report=states.append)
        self.assertEqual(result[0]['provider_id'],new['provider_id']);self.assertEqual(rank.await_count,2)
        self.assertEqual([c.args[0] for c in fetch.call_args_list],['ceramic hummus bowl with paprika','hummus'])
        self.assertEqual(rank.call_args.args[1][0]['provider_id'],new['provider_id'])
        self.assertTrue(any(s.get('recovery_used') and s.get('search_round')==2 for s in states))
    async def test_second_empty_ranking_stops_even_with_more_suggestions(self):
        rank=AsyncMock(side_effect=[empty(),empty(query='hummus plate')]);states=[]
        fetch=AsyncMock(return_value=[food_photo()])
        result=await select_food_photos(narrow_food(),fetch=fetch,commons=AsyncMock(return_value=[]),rank=rank,report=states.append)
        self.assertEqual(result,[]);self.assertEqual(rank.await_count,2)
        self.assertNotIn('hummus plate',[c.args[0] for c in fetch.call_args_list])
        self.assertEqual(states[-1]['reason'],'empty_after_search_recovery')
    async def test_first_success_does_not_search_again(self):
        rank=AsyncMock(side_effect=lambda f,photos,**kw:photos)
        fetch=AsyncMock(return_value=[food_photo()])
        result=await select_food_photos(narrow_food(),fetch=fetch,commons=AsyncMock(return_value=[]),rank=rank)
        self.assertEqual(len(result),1);rank.assert_awaited_once();fetch.assert_awaited_once()
    async def test_no_initial_candidates_can_still_recover_without_forcing_unrelated_photos(self):
        new=food_photo(1);fetch=AsyncMock(side_effect=lambda q:[new] if q=='hummus' else [])
        rank=AsyncMock(side_effect=[empty(),[{**new,'food_request_ids':['dish']}]])
        result=await select_food_photos(narrow_food(),fetch=fetch,commons=AsyncMock(return_value=[]),rank=rank)
        self.assertEqual(len(result),1);self.assertEqual(rank.call_args_list[0].args[1],[])
    async def test_repeated_queries_are_not_fetched_or_ranked_again(self):
        rank=AsyncMock(return_value=empty(query='ceramic hummus bowl with paprika'))
        fetch=AsyncMock(return_value=[food_photo()])
        self.assertEqual(await select_food_photos(narrow_food(),fetch=fetch,commons=AsyncMock(return_value=[]),rank=rank),[])
        rank.assert_awaited_once();fetch.assert_awaited_once()
    async def test_named_person_recovery_remains_commons_only(self):
        f=narrow_food();f['food_lesson']['photos'][0].update(kind='person',subject='Named Person')
        # kind checks are shared even when a caller supplies a request outside its generation schema.
        fetch=AsyncMock();commons=AsyncMock(return_value=[food_photo()])
        rank=AsyncMock(side_effect=[empty(query='Named Person'),[{**food_photo(),'food_request_ids':['dish']} ]])
        result=await select_food_photos(f,fetch=fetch,commons=commons,rank=rank)
        fetch.assert_not_awaited();self.assertEqual(commons.await_count,2);self.assertEqual(len(result),1)
    async def test_recovery_failure_retains_conservative_fallback_and_no_excluded_sources(self):
        prior=food_photo();new=food_photo(1)
        rank=AsyncMock(side_effect=[empty(),PhotoRankingUnavailable()])
        result=await select_food_photos(narrow_food(),fetch=AsyncMock(return_value=[prior,new]),commons=AsyncMock(return_value=[]),
            rank=rank,excluded=[prior['source_url']])
        self.assertEqual([p['source_url'] for p in result],[new['source_url']])
    async def test_new_candidates_replace_full_original_pool_without_duplicates(self):
        f=narrow_food();new=food_photo(500)
        fetch=AsyncMock(side_effect=lambda q:[new,new] if q=='hummus' else [food_photo(i) for i in range(240)])
        rank=AsyncMock(side_effect=[empty(),[{**new,'food_request_ids':['dish']} ]])
        result=await select_food_photos(f,fetch=fetch,commons=AsyncMock(return_value=[]),rank=rank)
        pool=rank.call_args.args[1]
        self.assertEqual(len(pool),240);self.assertEqual(pool[0]['provider_id'],new['provider_id'])
        self.assertEqual(len({p['source_url'] for p in pool}),240);self.assertEqual(len(result),1)
    async def test_country_recovers_once_and_retains_ten_photo_minimum(self):
        counter=iter(range(100));fetch=AsyncMock(side_effect=lambda q:[photo(next(counter)),photo(next(counter))])
        rank=AsyncMock()
        async def ranked(f,photos,**kw):
            if rank.await_count==1:return empty(scene='topic',query='Japan market')
            return photos[:10]
        rank.side_effect=ranked
        result=await select_country_photos(country_fixture(),fetch=fetch,rank=rank)
        self.assertEqual(len(result),10);self.assertEqual(rank.await_count,2);self.assertEqual(fetch.await_count,13)
        rank=AsyncMock(side_effect=[empty(scene='topic',query='Japan market'),empty(scene='topic',query='Japan street')])
        counter=iter(range(100));fetch=AsyncMock(side_effect=lambda q:[photo(next(counter)),photo(next(counter))])
        states=[]
        self.assertEqual(await select_country_photos(country_fixture(),fetch=fetch,rank=rank,report=states.append),[])
        self.assertEqual(rank.await_count,2);self.assertEqual(fetch.await_count,13)
        self.assertEqual(states[-1]['reason'],'not_enough_relevant_metadata')
    async def test_india_recovery_can_fetch_commons_and_keeps_the_minimum(self):
        f=india_fixture();counter=iter(range(100))
        fetch=AsyncMock(side_effect=lambda q:[photo(next(counter)),photo(next(counter))])
        commons=AsyncMock(return_value=[{**food_photo(i),'provider_id':f'commons_{i}'} for i in range(10)])
        rank=AsyncMock()
        async def ranked(f,photos,**kw):
            if rank.await_count==1:return empty(scene='topic',query='Meghalaya root bridge')
            return [p for p in photos if p['provider']=='wikimedia'][:10]
        rank.side_effect=ranked
        result=await select_india_photos(f,fetch=fetch,fallback_fetch=commons,rank=rank)
        self.assertEqual(len(result),10);self.assertEqual(rank.await_count,2)
        commons.assert_awaited_once_with('Meghalaya root bridge')
        self.assertTrue(all(p['provider']=='wikimedia' for p in result))
    async def test_country_completion_retains_recovery_diagnostics(self):
        r=routes_module();r.track_selection=AsyncMock(return_value=True)
        async def select(f,*,report,excluded):
            report({'search_round':2,'recovery_used':True,'recovery_queries':[{'scene':'topic','query':'Japan market'}]})
            return [photo(i) for i in range(10)]
        r.select_country_photos=AsyncMock(side_effect=select)
        f=country_fixture();f['country_media']={'photo_ranking_version':1}
        await r._background_image_task({},'hash',article=f,photos_only=True)
        state=r.set_fact_photo_selection.call_args.args[1]
        self.assertEqual(state['status'],'completed');self.assertTrue(state['recovery_used'])
        self.assertEqual(state['search_round'],2)
