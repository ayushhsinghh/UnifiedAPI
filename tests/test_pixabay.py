"""Offline Pixabay retrieval, durable caching, shared ranking and publication checks."""
import copy
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
package = types.ModuleType('src.facts')
package.__path__ = [str(Path(__file__).resolve().parents[1] / 'app/src/facts')]
sys.modules.setdefault('src.facts', package)
from src.facts import pixabay_photos as p, stock_photos as stock
from src.facts.photo_ranking import select_food_photos, PhotoRankingResult, ranking_input
from test_food import fixture
from test_fact_evidence_lifecycle import routes_module


def payload():
    return {'totalHits': 1, 'hits': [{'id': 123, 'user_id': 45, 'user': 'Creator',
        'type': 'photo', 'tags': 'hummus, chickpeas, food', 'imageWidth': 2400, 'imageHeight': 1600,
        'largeImageURL': 'https://cdn.pixabay.com/photo/hummus_1280.jpg',
        'pageURL': 'https://pixabay.com/photos/hummus-123/', 'likes': 100}]}


def response(data=None, status=200, headers=None):
    value = MagicMock(status_code=status, headers=headers or {})
    value.__enter__.return_value = value
    value.iter_content.return_value = [json.dumps(payload() if data is None else data).encode()]
    return value


class PixabayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'PIXABAY_KEY': 'test-only-key', 'PIXABAY_CACHE_DIR': self.temp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_candidates_have_provider_ids_and_only_report_supplied_metadata(self):
        photo = p.candidates(payload(), 'hummus')[0]
        self.assertEqual(photo['provider_id'], 'pixabay_123')
        self.assertEqual(photo['description_text'], 'hummus, chickpeas, food')
        self.assertEqual(photo['license'], 'Pixabay Content License')
        self.assertNotIn('download_location', photo)
        self.assertEqual(ranking_input(fixture(), [photo])['photos'][0]['photo_id'], 'pixabay_123')

    def test_rejects_nonphotos_small_unknown_hosts_missing_credits_and_explicit_ai(self):
        for change in ({'type': 'vector'}, {'imageWidth': 100}, {'id': True}, {'user': ''},
                       {'largeImageURL': 'https://cdn.pixabay.com.evil.example/x.jpg'},
                       {'largeImageURL': 'http://127.0.0.1/x.jpg'},
                       {'pageURL': 'https://evil.example/photo'}, {'tags': 'ai-generated hummus'}):
            data = payload()
            data['hits'][0].update(change)
            self.assertEqual(p.candidates(data, 'hummus'), [], change)

    def test_search_persists_24_hour_cache_without_key_and_refreshes_after_expiry(self):
        now = time.time()
        with patch('requests.get', return_value=response()) as get:
            self.assertTrue(p._ranking_candidates('hummus'))
            self.assertTrue(p._ranking_candidates('hummus'))
            self.assertEqual(get.call_count, 1)
            params = get.call_args.kwargs['params']
            self.assertEqual(params['image_type'], 'photo')
            self.assertEqual(params['safesearch'], 'true')
            for path in Path(self.temp.name).glob('*.json'):
                self.assertNotIn('test-only-key', path.read_text())
            with patch.object(p.time, 'time', return_value=now + p.TTL + 10):
                self.assertTrue(p._ranking_candidates('hummus'))
            self.assertEqual(get.call_count, 2)

    def test_empty_results_are_cached_and_missing_key_never_calls_api(self):
        with patch('requests.get', return_value=response({'hits': [], 'totalHits': 0})) as get:
            self.assertEqual(p._ranking_candidates('unknown'), [])
            self.assertEqual(p._ranking_candidates('unknown'), [])
            self.assertEqual(get.call_count, 1)
        with patch.dict(os.environ, {'PIXABAY_KEY': ''}), patch('requests.get') as get:
            self.assertEqual(p._ranking_candidates('hummus'), [])
            get.assert_not_called()

    def test_rate_limit_blocks_following_queries_and_redirects_are_disabled(self):
        with patch('requests.get', return_value=response(status=429, headers={'X-RateLimit-Reset': '60'})) as get:
            self.assertEqual(p._ranking_candidates('hummus'), [])
            self.assertEqual(p._ranking_candidates('different query'), [])
            self.assertEqual(get.call_count, 1)
            self.assertFalse(get.call_args.kwargs['allow_redirects'])

    def test_http_debug_logs_redact_query_key(self):
        record = logging.LogRecord('urllib3.connectionpool', logging.DEBUG, '', 1,
                                   'GET /api/?key=%s&q=hummus', ('secret',), None)
        p._HideQueryKey().filter(record)
        self.assertNotIn('secret', record.getMessage())
        self.assertIn('[REDACTED]', record.getMessage())

    async def test_both_providers_are_searched_and_one_failure_keeps_other_results(self):
        photo = p.candidates(payload(), 'hummus')[0]
        with patch.object(stock.unsplash_photos, 'ranking_candidates', new=AsyncMock(side_effect=RuntimeError())), \
             patch.object(stock.pixabay_photos, 'ranking_candidates', new=AsyncMock(return_value=[photo])) as fetch:
            self.assertEqual(await stock.ranking_candidates('hummus'), [photo])
            fetch.assert_awaited_once_with('hummus')

    async def test_editorial_recovery_queries_include_pixabay_and_use_same_ranker(self):
        fact = fixture()
        fact['food_lesson']['photos'] = fact['food_lesson']['photos'][:1]
        request = fact['food_lesson']['photos'][0]['id']
        photo = p.candidates(payload(), 'hummus')[0]
        calls = []
        async def rank(fact, photos, **kwargs):
            calls.append(photos)
            if len(calls) == 1:
                return PhotoRankingResult([], [{'scene': request, 'query': 'chickpea hummus bowl'}])
            return PhotoRankingResult([{**photos[0], 'food_request_ids': [request], 'ranking_score': 90}])
        with patch.object(stock.unsplash_photos, 'ranking_candidates', new=AsyncMock(return_value=[])), \
             patch.object(stock.pixabay_photos, 'ranking_candidates', new=AsyncMock(return_value=[photo])) as fetch:
            chosen = await select_food_photos(fact, commons=AsyncMock(return_value=[]), rank=rank)
        self.assertEqual(chosen[0]['provider'], 'pixabay')
        self.assertEqual(len(calls), 2)
        self.assertIn(('chickpea hummus bowl',), [call.args for call in fetch.await_args_list])

    async def test_selected_images_are_stored_once_before_publication(self):
        photo = p.candidates(payload(), 'hummus')[0]
        image = response()
        image.iter_content.return_value = [b'\xff\xd8\xfftest-jpeg']
        url = 'https://objectstorage.ap-mumbai-1.oraclecloud.com/p/read/n/ns/b/bucket/o/photo.jpg'
        upload = Mock(return_value=url)
        module = types.ModuleType('src.facts.image_generator')
        module._upload_to_oci_and_get_par = upload
        with patch.dict(sys.modules, {'src.facts.image_generator': module}), \
             patch('requests.get', return_value=image) as get:
            route = routes_module()
            self.assertTrue(await route._prepare_selected_photo(photo))
            self.assertEqual(photo['url'], url)
            self.assertTrue(photo['stored_locally'])
            self.assertEqual(await p.persist_selected(p.candidates(payload(), 'hummus')[0]), url)
            self.assertEqual(get.call_count, 1)
        self.assertEqual(upload.call_args.kwargs['content_type'], 'image/jpeg')

    async def test_failed_storage_never_publishes_pixabay_hotlink(self):
        photo = p.candidates(payload(), 'hummus')[0]
        route = routes_module()
        with patch.object(p, 'persist_selected', new=AsyncMock(return_value=None)):
            self.assertFalse(await route._prepare_selected_photo(photo))
        self.assertNotIn('stored_locally', photo)

    def test_download_rejects_html_and_oversized_payloads(self):
        photo = p.candidates(payload(), 'hummus')[0]
        for data in (b'<html>error</html>', b'x' * (12 * 1024 * 1024 + 1)):
            image = response()
            image.iter_content.return_value = [data]
            with patch('requests.get', return_value=image):
                self.assertIsNone(p._persist_selected(photo))
