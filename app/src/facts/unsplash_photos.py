"""Server-only Unsplash search, attribution, and selected-photo tracking."""
import asyncio
import os
import logging
import re
import time
from collections import OrderedDict
from threading import Lock
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .country_photos import allowed_url, plain
logger=logging.getLogger(__name__)
_DETAIL_CACHE=OrderedDict()
_DETAIL_LOCK=Lock()
_DETAIL_TTL=600
class _UnsplashBlocked(Exception):pass


def access_key():
    return (os.getenv('UNSPLASH_ACCESS_KEY', '').strip() or os.getenv('ACCESS_KEY', '').strip())


def referral(url):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query.update(utm_source='the_curiosity_archive', utm_medium='referral')
    return urlunsplit(parts._replace(query=urlencode(query)))


def candidates(payload, country):
    """Require explicit country evidence; search ranking alone is not identification."""
    result = []
    for photo in payload.get('results', []):
        user = photo.get('user') or {}
        links = photo.get('links') or {}
        url = (photo.get('urls') or {}).get('regular')
        source, author_url = links.get('html'), (user.get('links') or {}).get('html')
        description = plain(photo.get('description') or photo.get('alt_description'))
        tags=list(dict.fromkeys(plain(tag.get('title'))[:100] for tag in (photo.get('tags') or []) if isinstance(tag,dict) and plain(tag.get('title'))))[:30]
        evidence = ' '.join([description, plain(photo.get('alt_description')),
            plain((photo.get('location') or {}).get('country')),
            plain((photo.get('location') or {}).get('name')),
            ' '.join(tags)])
        if country and not re.search(r'\b' + re.escape(country) + r'\b', evidence, re.I):
            continue
        width, height = photo.get('width'), photo.get('height')
        if not isinstance(width, int) or not isinstance(height, int) or min(width, height) < 800:
            continue
        if not allowed_url(url, {'images.unsplash.com'}):
            continue
        if not all(allowed_url(link, {'unsplash.com'}) for link in (source, author_url)):
            continue
        if not plain(user.get('name')) or not description:
            continue
        tracking = links.get('download_location')
        if not allowed_url(tracking, {'api.unsplash.com'}) or not re.fullmatch(
                r'/photos/[\w-]+/download', urlsplit(tracking).path):
            continue
        result.append(dict(provider='unsplash', provider_id=photo.get('id'), url=url,
            title=description, description=description,description_text=plain(photo.get('description')), author=plain(user['name']),
            author_url=referral(author_url), source_url=referral(source),
            license='Unsplash License', license_url=referral('https://unsplash.com/license'),
            width=width, height=height, download_location=tracking, tags=tags,
            alt_description=plain(photo.get('alt_description')),location_country=plain((photo.get('location') or {}).get('country')),
            location_name=plain((photo.get('location') or {}).get('name')),
            likes=photo.get('likes',0) if type(photo.get('likes',0)) is int else 0))
    return sorted(result, key=lambda p: min(p['width'], p['height']), reverse=True)


def _details(photo_id,key):
    """Public photo metadata only; fixed endpoint and bounded, in-memory cache."""
    import requests
    if not isinstance(photo_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',photo_id):return None
    with _DETAIL_LOCK:
        cached=_DETAIL_CACHE.get(photo_id)
        if cached and time.monotonic()-cached[0]<_DETAIL_TTL:
            _DETAIL_CACHE.move_to_end(photo_id);return cached[1]
    try:
        response=requests.get(f'https://api.unsplash.com/photos/{photo_id}',
            headers={'Authorization':f'Client-ID {key}','Accept-Version':'v1'},
            timeout=(2,4),allow_redirects=False)
        if response.status_code in (401,403,429):
            logger.warning('Unsplash detail lookup blocked (%s)',response.status_code)
            raise _UnsplashBlocked()
        if response.status_code!=200 or len(response.content)>1_500_000:return None
        photo=response.json()
        if not isinstance(photo,dict) or photo.get('id')!=photo_id:return None
        with _DETAIL_LOCK:
            _DETAIL_CACHE[photo_id]=(time.monotonic(),photo)
            _DETAIL_CACHE.move_to_end(photo_id)
            while len(_DETAIL_CACHE)>256:_DETAIL_CACHE.popitem(last=False)
        return photo
    except (requests.RequestException,ValueError,TypeError):return None

def _tag_match(photo,query,country):
    words=lambda value:set(re.findall(r'[^\W_]+',value.casefold()))
    required=words(query)-words(country)-{'the','and','for','with','photo','photograph'}
    return bool(required & words(' '.join(photo.get('tags') or [])))

def _search(country, query, match=None, exact_query=False, popular_fallback=False):
    import requests
    key = access_key()
    if not key:
        return []
    deadline=time.monotonic()+45
    try:
        response = requests.get('https://api.unsplash.com/search/photos',
            params={'query': (query if exact_query else f'{country} {query}')[:240], 'per_page': 12,
                'content_filter': 'high', 'order_by': 'relevant'},
            headers={'Authorization': f'Client-ID {key}', 'Accept-Version': 'v1'},
            timeout=(3, 7), allow_redirects=False)
        if response.status_code != 200 or len(response.content) > 1_500_000:
            logger.warning('Unsplash search rejected (%s), query=%r',response.status_code,query)
            return []
        payload=response.json()
        raw=[p for p in payload.get('results',[]) if isinstance(p,dict)]
        ranked=sorted(raw,key=lambda p:p.get('likes',0) if type(p.get('likes',0)) is int else 0,reverse=True)
        eligible=[];popular=[];seen=set()
        for summary in ranked[:12]:
            if len(eligible)>=3 or time.monotonic()>deadline:break
            photo_id=summary.get('id')
            if not isinstance(photo_id,str) or photo_id in seen:continue
            seen.add(photo_id)
            try:detail=_details(photo_id,key)
            except _UnsplashBlocked:break
            if not detail:continue
            for photo in candidates({'results':[detail]},country):
                photo['search_likes']=summary.get('likes',0)
                photo['detail_fetched']=True
                popular.append(photo)
                matches=match(photo) if match else _tag_match(photo,query,country)
                if matches:eligible.append(photo)
        if popular_fallback and len(eligible)<3:
            eligible=[{**photo,'selection_mode':'popular_fallback'} for photo in popular[:3]]
        mode='popular fallback' if eligible and eligible[0].get('selection_mode')=='popular_fallback' else 'tag matches'
        logger.info('Unsplash query=%r: %d raw results, %d detail-checked photos (%s)',query,len(raw),len(eligible),mode)
        return eligible
    except (requests.RequestException, ValueError, TypeError):
        return []


async def search(country, query, *, match=None, exact_query=False, popular_fallback=False):
    return await asyncio.to_thread(_search, country, query,match,exact_query,popular_fallback)

def _ranking_candidates(query):
    """Larger metadata-only pool; relevance is decided by the text ranker, not missing summary tags."""
    import requests
    key=access_key()
    if not key:return []
    try:
        response=requests.get('https://api.unsplash.com/search/photos',
            params={'query':query[:240],'per_page':30,'content_filter':'high','order_by':'relevant'},
            headers={'Authorization':f'Client-ID {key}','Accept-Version':'v1'},timeout=(3,7),allow_redirects=False)
        if response.status_code!=200 or len(response.content)>2_500_000:return []
        return [dict(photo,search_query=query) for photo in candidates(response.json(),None)
            if isinstance(photo.get('provider_id'),str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}',photo['provider_id'])]
    except (requests.RequestException,ValueError,TypeError):return []

async def ranking_candidates(query):
    return await asyncio.to_thread(_ranking_candidates,query)


def _track(photo):
    import requests
    key = access_key()
    location = photo.get('download_location')
    if not key or not allowed_url(location, {'api.unsplash.com'}) or not re.fullmatch(
            r'/photos/[\w-]+/download', urlsplit(location).path):
        return False
    try:
        response = requests.get(location,
            headers={'Authorization': f'Client-ID {key}', 'Accept-Version': 'v1'},
            timeout=(3, 5), allow_redirects=False)
        return response.status_code == 200
    except requests.RequestException:
        return False


async def track_selection(photo):
    return await asyncio.to_thread(_track, photo)
