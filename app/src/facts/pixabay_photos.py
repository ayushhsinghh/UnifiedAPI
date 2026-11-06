"""Server-only Pixabay photos, durable 24-hour search cache, and selected assets."""
import asyncio
import hashlib
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from .country_photos import allowed_url, plain

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()
TTL = 24 * 60 * 60
IMAGE_HOSTS = {'pixabay.com', 'cdn.pixabay.com'}


class _HideQueryKey(logging.Filter):
    def filter(self, record):
        # urllib3 DEBUG otherwise prints the API key in its request URL.
        record.msg = re.sub(r'([?&]key=)[^&\s\"]+', r'\1[REDACTED]', record.getMessage())
        record.args = ()
        return True


logging.getLogger('urllib3.connectionpool').addFilter(_HideQueryKey())


def cache_directory():
    from configs.config import get_config
    return Path(os.getenv('PIXABAY_CACHE_DIR') or str(Path(get_config().OUTPUT_DIR) / 'photo-cache' / 'pixabay'))


def _write(path, value):
    temp = path.with_name(path.name + '.' + uuid4().hex + '.part')
    try:
        temp.write_text(json.dumps(value), encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _read(path):
    try:
        if path.stat().st_size > 2_500_000:
            return {}
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def candidates(payload, query):
    """Tags are source metadata, never proof of an exact subject or AI provenance."""
    result = []
    if not isinstance(payload, dict) or not isinstance(payload.get('hits'), list):
        return result
    seen = set()
    for photo in payload['hits'][:30]:
        if not isinstance(photo, dict) or photo.get('type') != 'photo':
            continue
        identity, user_id = photo.get('id'), photo.get('user_id')
        width, height = photo.get('imageWidth'), photo.get('imageHeight')
        if (type(identity) is not int or identity <= 0 or identity in seen
                or type(user_id) is not int or user_id <= 0
                or type(width) is not int or type(height) is not int or min(width, height) < 800):
            continue
        image, source = photo.get('largeImageURL'), photo.get('pageURL')
        author, tags = plain(photo.get('user')), plain(photo.get('tags'))
        if (not author or not tags or not allowed_url(image, IMAGE_HOSTS)
                or not allowed_url(source, {'pixabay.com'})):
            continue
        if re.search(r'\b(ai.generated|generative ai|midjourney|stable diffusion)\b', tags, re.I):
            continue
        seen.add(identity)
        result.append(dict(provider='pixabay', provider_id=f'pixabay_{identity}',
            url=image, source_url=source, author=author,
            author_url=f'https://pixabay.com/users/{quote(author, safe="")}-{user_id}/',
            title=tags, description=tags, description_text=tags, alt_description='',
            tags=[tag.strip() for tag in tags.split(',') if tag.strip()],
            license='Pixabay Content License', license_url='https://pixabay.com/service/license-summary/',
            width=width, height=height, search_query=query,
            likes=photo.get('likes', 0) if type(photo.get('likes', 0)) is int else 0))
    return result


def _ranking_candidates(query):
    import fcntl
    import requests
    key = os.getenv('PIXABAY_KEY', '').strip()
    query = ' '.join(str(query).split())[:100]
    if not key or not query:
        return []
    account = hashlib.sha256(key.encode()).hexdigest()[:16]
    digest = hashlib.sha256((account + ':' + query.casefold()).encode()).hexdigest()
    try:
        root = cache_directory()
        root.mkdir(parents=True, exist_ok=True)
        path, cooldown = root / f'{digest}.json', root / f'{account}-cooldown.json'
        # Shared disk lock prevents duplicate calls from parallel threads/processes.
        with _LOCK, (root / f'{account}.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            cached = _read(path)
            if cached.get('expires_at', 0) > time.time() and isinstance(cached.get('photos'), list):
                logger.info('Pixabay search cache hit: query=%r candidates=%d', query, len(cached['photos']))
                return cached['photos']
            if _read(cooldown).get('until', 0) > time.time():
                logger.warning('Pixabay rate-limit cooldown; query=%r', query)
                return []
            with requests.get('https://pixabay.com/api/', params={'key': key, 'q': query,
                    'image_type': 'photo', 'safesearch': 'true', 'per_page': 30, 'order': 'popular',
                    'min_width': 800, 'min_height': 800}, timeout=(3, 7),
                    allow_redirects=False, stream=True) as response:
                if response.status_code in (401, 403, 429) or response.headers.get('X-RateLimit-Remaining') == '0':
                    try:
                        delay = min(3600, max(1, int(response.headers.get('X-RateLimit-Reset', '60'))))
                    except ValueError:
                        delay = 60
                    _write(cooldown, {'until': time.time() + delay})
                if response.status_code != 200:
                    logger.warning('Pixabay search rejected: status=%s query=%r', response.status_code, query)
                    return []
                data = bytearray()
                for chunk in response.iter_content(16384):
                    data.extend(chunk)
                    if len(data) > 2_500_000:
                        logger.warning('Pixabay response too large; query=%r', query)
                        return []
                payload = json.loads(data)
            if not isinstance(payload, dict) or not isinstance(payload.get('hits'), list):
                logger.warning('Pixabay returned invalid search data; query=%r', query)
                return []
            photos = candidates(payload, query)
            _write(path, {'expires_at': time.time() + TTL, 'photos': photos})
            logger.info('Pixabay search completed: query=%r hits=%s candidates=%d',
                        query, payload.get('totalHits', 0), len(photos))
            return photos
    except (OSError, requests.RequestException, ValueError, TypeError, OverflowError) as exc:
        # Never include request URLs, exception strings, or the query API key.
        logger.warning('Pixabay search unavailable: error_type=%s query=%r', type(exc).__name__, query)
        return []


async def ranking_candidates(query):
    return await asyncio.to_thread(_ranking_candidates, query)


async def search(country, query, *, match=None, exact_query=False, popular_fallback=False):
    photos = await ranking_candidates(query if exact_query else f'{country} {query}')
    if country:
        photos = [p for p in photos if re.search(r'\b' + re.escape(country) + r'\b', p['description'], re.I)]
    if match:
        photos = [p for p in photos if match(p)]
    return photos


def _persist_selected(photo):
    import requests
    identity = photo.get('provider_id', '')
    if not re.fullmatch(r'pixabay_[1-9][0-9]*', identity) or not allowed_url(photo.get('url'), IMAGE_HOSTS):
        return None
    try:
        root = cache_directory()
        root.mkdir(parents=True, exist_ok=True)
        path = root / f'{identity}-stored.json'
        cached = _read(path)
        if cached.get('expires_at', 0) > time.time():
            return cached.get('url')
        with requests.get(photo['url'], timeout=(3, 10), allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                logger.warning('Pixabay selected download rejected: id=%s status=%s', identity, response.status_code)
                return None
            data = bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data) > 12 * 1024 * 1024:
                    return None
        if data.startswith(b'\xff\xd8\xff'):
            kind, suffix = 'image/jpeg', 'jpg'
        elif data.startswith(b'\x89PNG\r\n\x1a\n'):
            kind, suffix = 'image/png', 'png'
        else:
            return None
        from .image_generator import _upload_to_oci_and_get_par
        url = _upload_to_oci_and_get_par(bytes(data), f'photos/pixabay/{identity}.{suffix}', content_type=kind)
        if url:
            # Existing OCI helper creates five-year read URLs; refresh before expiry.
            _write(path, {'url': url, 'expires_at': time.time() + 4 * 365 * TTL})
            logger.info('Pixabay selected image stored: id=%s bytes=%d', identity, len(data))
        return url
    except (OSError, requests.RequestException, ValueError, TypeError) as exc:
        logger.warning('Pixabay selected image unavailable: id=%s error_type=%s', identity, type(exc).__name__)
        return None


async def persist_selected(photo):
    return await asyncio.to_thread(_persist_selected, photo)
