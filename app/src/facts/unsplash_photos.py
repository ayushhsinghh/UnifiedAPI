"""Server-only Unsplash search, attribution, and selected-photo tracking."""
import asyncio
import os
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .country_photos import allowed_url, plain


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
        evidence = ' '.join([description, plain(photo.get('alt_description')),
            plain((photo.get('location') or {}).get('country')),
            ' '.join(plain(tag.get('title')) for tag in photo.get('tags', []))])
        if not re.search(r'\b' + re.escape(country) + r'\b', evidence, re.I):
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
            title=description, description=description, author=plain(user['name']),
            author_url=referral(author_url), source_url=referral(source),
            license='Unsplash License', license_url=referral('https://unsplash.com/license'),
            width=width, height=height, download_location=tracking))
    return sorted(result, key=lambda p: min(p['width'], p['height']), reverse=True)


def _search(country, query):
    import requests
    key = access_key()
    if not key:
        return []
    try:
        response = requests.get('https://api.unsplash.com/search/photos',
            params={'query': f'{country} {query}'[:240], 'per_page': 12,
                'content_filter': 'high', 'order_by': 'relevant'},
            headers={'Authorization': f'Client-ID {key}', 'Accept-Version': 'v1'},
            timeout=(3, 7), allow_redirects=False)
        if response.status_code != 200 or len(response.content) > 1_500_000:
            return []
        return candidates(response.json(), country)
    except (requests.RequestException, ValueError, TypeError):
        return []


async def search(country, query):
    return await asyncio.to_thread(_search, country, query)


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
