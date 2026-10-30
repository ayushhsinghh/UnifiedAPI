"""Bounded, fixed-host Wikimedia Commons photo lookup with reusable licence metadata."""
import asyncio
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlsplit

class PlainText(HTMLParser):
    def __init__(self): super().__init__(); self.parts = []
    def handle_data(self, data): self.parts.append(data)

def plain(value):
    parser = PlainText(); parser.feed(str(value or ''))
    return unescape(' '.join(''.join(parser.parts).split()))[:800]

def allowed_url(value, hosts):
    try:
        p = urlsplit(value)
        return p.scheme == 'https' and p.hostname in hosts and not p.username and not p.password and p.port in (None, 443)
    except (ValueError, TypeError): return False

def photo_candidates(payload):
    result = []
    pages = payload.get('query', {}).get('pages', {})
    if not isinstance(pages, dict): return []
    for page in sorted(pages.values(), key=lambda p:p.get('index', 999)):
        info = (page.get('imageinfo') or [{}])[0]; meta = info.get('extmetadata') or {}
        read = lambda key: plain((meta.get(key) or {}).get('value', ''))
        licence = read('LicenseShortName'); licence_url = read('LicenseUrl')
        reusable = licence in ('Public domain', 'CC0') or bool(re.fullmatch(r'CC BY(?:-SA)? [1-4]\.0', licence))
        url = info.get('thumburl') or info.get('url'); source = info.get('descriptionurl')
        if not reusable or info.get('mime') not in ('image/jpeg', 'image/png', 'image/webp'): continue
        if not allowed_url(url, {'upload.wikimedia.org', 'thumb.wikimedia.org'}) or not allowed_url(source, {'commons.wikimedia.org'}): continue
        if licence.startswith('CC BY') and (not read('Artist') or not allowed_url(licence_url, {'creativecommons.org', 'www.creativecommons.org'})): continue
        if not licence_url:
            licence_url = 'https://creativecommons.org/publicdomain/zero/1.0/' if licence == 'CC0' else 'https://creativecommons.org/publicdomain/mark/1.0/'
        if not allowed_url(licence_url, {'creativecommons.org', 'www.creativecommons.org'}): continue
        if any(term in (read('Categories') + ' ' + read('ImageDescription')).lower() for term in ('ai-generated', 'ai generated', 'stable diffusion', 'midjourney')): continue
        title = plain(page.get('title', '')).removeprefix('File:')
        description = read('ImageDescription') or title
        if re.search(r'\b(painting|drawing|engraving|woodblock|illustration|eb1911|map|flag)\b',
                     title + ' ' + description + ' ' + read('Categories'), re.IGNORECASE):
            continue
        result.append({'url': url, 'title': title, 'author': read('Artist') or 'Creator not supplied',
            'license': licence, 'license_url': licence_url, 'source_url': source,
            'description': description, 'modifications': 'Displayed at a reduced size; cover and card views may crop the photograph.'})
    return result

def _lookup(country, query):
    import requests
    params = {'action':'query','format':'json','generator':'search','gsrnamespace':6,
        'gsrsearch':f'intitle:"{country}" {query[:240]} filetype:bitmap -artificial -generated -painting -drawing -illustration',
        'gsrlimit':6,'prop':'imageinfo','iiprop':'url|extmetadata|mime','iiurlwidth':1600}
    with requests.get('https://commons.wikimedia.org/w/api.php', params=params,
        headers={'User-Agent':'CuriosityArchive/1.0 (https://fact.ayush.ltd)'}, timeout=(4,12),
        allow_redirects=False, stream=True) as response:
        if response.status_code != 200: return []
        data = bytearray()
        for chunk in response.iter_content(16384):
            data.extend(chunk)
            if len(data) > 1_500_000: return []
        # Search can match incidental page text. Require the country in returned photo metadata too.
        return [photo for photo in photo_candidates(__import__('json').loads(data))
                if re.search(r'\b' + re.escape(country) + r'\b', photo['title'], re.IGNORECASE)]

async def find_country_photos(country, query):
    return await asyncio.to_thread(_lookup, country, query)
