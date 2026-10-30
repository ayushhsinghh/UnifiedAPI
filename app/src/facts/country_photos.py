"""Bounded, fixed-host Wikimedia Commons photo lookup with reusable licence metadata."""
import asyncio
import re
import time
import unicodedata
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

def photo_candidates(payload, allow_art=False):
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
        if not allow_art and re.search(r'\b(painting|drawing|engraving|woodblock|illustration|eb1911|map|flag)\b',
                     title + ' ' + description + ' ' + read('Categories'), re.IGNORECASE):
            continue
        result.append({'url': url, 'title': title, 'author': read('Artist') or 'Creator not supplied',
            'license': licence, 'license_url': licence_url, 'source_url': source,
            'description': description, 'modifications': 'Displayed at a reduced size; cover and card views may crop the photograph.'})
    return result

def _lookup(country, query):
    import requests
    subject=re.sub(re.escape(country),'',query,flags=re.IGNORECASE)
    words=re.findall(r'[^\W_]+',subject)[:18]
    searches=list(dict.fromkeys([' '.join(words),' '.join(words[:2]),'']))
    results=[];seen=set();deadline=time.monotonic()+22
    for terms in searches:
        if time.monotonic()>=deadline:break
        params={'action':'query','format':'json','generator':'search','gsrnamespace':6,
            'gsrsearch':f'intitle:"{country}" {terms} filetype:bitmap -artificial -generated -painting -drawing -illustration',
            'gsrlimit':12,'prop':'imageinfo','iiprop':'url|extmetadata|mime','iiurlwidth':1600}
        try:
            with requests.get('https://commons.wikimedia.org/w/api.php',params=params,
                headers={'User-Agent':'CuriosityArchive/1.0 (https://fact.ayush.ltd)'},timeout=(3,6),
                allow_redirects=False,stream=True) as response:
                if response.status_code==429:break
                if response.status_code!=200:continue
                data=bytearray()
                for chunk in response.iter_content(16384):
                    data.extend(chunk)
                    if len(data)>1_500_000 or time.monotonic()>deadline:break
                else:
                    for photo in photo_candidates(__import__('json').loads(data)):
                        if photo['source_url'] not in seen and re.search(r'\b'+re.escape(country)+r'\b',photo['title'],re.IGNORECASE):
                            seen.add(photo['source_url']);results.append(photo)
        except (requests.RequestException,ValueError,TypeError):continue
        if len(results)>=6:break
    return results

async def find_country_photos(country, query, protected_names=(), scene_only=False):
    if scene_only:
        from .unsplash_photos import search
        themes = {'landscape nature':r'forest|mountain|beach|coast|lake|river|landscape|volcano|valley|desert|nature',
            'local market daily life':r'market|vendor|food|shop|people|festival|daily',
            'traditional architecture countryside':r'architect|building|temple|house|village|rural|countryside'}
        pattern=themes.get(query,r'city|street|town|urban|road|alley')
        matches=[p for p in await search(country, query) if re.search(pattern,p['description'],re.I)]
        if matches:return matches
        simpler={'landscape nature':'landscape','local market daily life':'market',
            'traditional architecture countryside':'architecture'}.get(query,'city streets')
        return [p for p in await search(country,simpler) if re.search(pattern,p['description'],re.I)]
    # Named people stay with the documentary source. Never substitute stock portraits.
    if any(name and name.casefold() in query.casefold() for name in protected_names):
        photos = await asyncio.to_thread(_lookup, country, query)
        return [p for p in photos if any(name.casefold() in
            (p['title'] + ' ' + p['description']).casefold() for name in protected_names if name)]
    from .unsplash_photos import search
    commons, stock = await asyncio.gather(asyncio.to_thread(_lookup, country, query), search(country, query))
    # Preserve documentary coverage while admitting up to two contemporary photos per subject.
    subject = re.sub(re.escape(country), '', query, flags=re.I)
    terms = {w.casefold() for w in re.findall(r'[^\W_]+', subject) if len(w) > 3}
    stock = [p for p in stock if not terms or any(t in
        (p['title'] + ' ' + p['description']).casefold() for t in terms)]
    return stock[:2] + commons


def normalized(value):
    return ' '.join(re.findall(r'[^\W_]+', ''.join(c for c in
        unicodedata.normalize('NFKD', value).casefold() if not unicodedata.combining(c))))


def _lookup_subject(country, subject, kind):
    """Exact subject lookup with no generic country fallback."""
    import requests
    clean = ' '.join(re.findall(r'[^\W_]+', subject))[:160]
    if not clean:
        return []
    portrait = ' portrait' if kind=='people' else ''
    searches = [f'"{clean}"{portrait} {country}', f'"{clean}"{portrait}']
    for query in dict.fromkeys(searches):
        try:
            with requests.get('https://commons.wikimedia.org/w/api.php', params={
                'action':'query', 'format':'json', 'generator':'search', 'gsrnamespace':6,
                'gsrsearch':query+' filetype:bitmap -artificial -generated', 'gsrlimit':8,
                'prop':'imageinfo', 'iiprop':'url|extmetadata|mime', 'iiurlwidth':1200},
                headers={'User-Agent':'CuriosityArchive/1.0 (https://fact.ayush.ltd)'},
                timeout=(3,6), allow_redirects=False, stream=True) as response:
                if response.status_code in (403,429): return []
                if response.status_code != 200: continue
                data=bytearray()
                for chunk in response.iter_content(16384):
                    data.extend(chunk)
                    if len(data)>1_500_000: break
                else:
                    matches=[]
                    for photo in photo_candidates(__import__('json').loads(data), allow_art=kind=='people'):
                        evidence=normalized(photo['title']+' '+photo['description'])
                        if ' '+normalized(subject)+' ' not in ' '+evidence+' ': continue
                        if kind!='people' and ' '+normalized(country)+' ' not in ' '+evidence+' ': continue
                        if kind=='people' and re.search(r'\b(statue|bust|grave|tomb|monument|signature)\b',evidence): continue
                        photo.update(provider='wikimedia', subject=subject, subject_kind=kind)
                        matches.append(photo)
                    if matches: return matches
        except (requests.RequestException,ValueError,TypeError): continue
    return []


async def find_subject_photo(country, subject, kind):
    return await asyncio.to_thread(_lookup_subject, country, subject, kind)


def country_scene_queries(profile):
    cities=profile.get('geography',{}).get('major_cities',[])
    city=cities[0].get('name','') if cities else ''
    return ['landscape nature', f'{city} city streets', 'local market daily life', 'traditional architecture countryside']
