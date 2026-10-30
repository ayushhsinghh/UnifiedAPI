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

async def find_country_photos(country, query, protected_names=(), scene_only=False, scene_fallback=False):
    if scene_only:
        from .unsplash_photos import search
        themes = {'landscape nature':r'forest|mountain|beach|coast|lake|river|landscape|volcano|valley|desert|nature',
            'local market daily life':r'market|vendor|food|shop|people|festival|daily',
            'traditional architecture countryside':r'architect|building|temple|house|village|rural|countryside',
            'beach coast':r'beach|coast|shore|sea|ocean',
            'mountains hiking':r'mountain|hill|hike|hiking|trail|peak|rock',
            'wildlife birds':r'wildlife|bird|animal|flamingo|iguana|fish|turtle',
            'local food cuisine':r'\b(?:food|dish|cuisine|meal|restaurant|bread)\b',
            'harbor boats':r'harbo[u]?r|boat|ship|port|marina',
            'historic buildings':r'histor|building|church|fort|ruin|architecture',
            'festival music culture':r'festival|music|carnival|dance|culture|celebration',
            'rural agriculture':r'rural|farm|agricultur|field|crop|countryside'}
        pattern=themes.get(query,r'city|street|town|urban|road|alley' if 'city streets' in query else re.escape(query))
        matches=[p for p in await search(country, query) if re.search(pattern,p['description'],re.I)]
        if len(matches)>=2 or (matches and not scene_fallback):return matches
        simpler={'landscape nature':'landscape','local market daily life':'market',
            'traditional architecture countryside':'architecture'}.get(query,query.split()[0] if query in themes else 'city streets' if 'city streets' in query else query)
        matches += [p for p in await search(country,simpler) if re.search(pattern,p['description'],re.I)]
        matches=list({p['source_url']:p for p in matches}.values())
        if scene_fallback and len(matches)<2:
            commons=await asyncio.to_thread(_lookup,country,query)
            matches += [{**p,'provider':'wikimedia'} for p in commons if re.search(pattern,p['title']+' '+p['description'],re.I)]
        return matches
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


def _lookup_subject(country, subject, kind, deadline=None):
    """Exact subject lookup with no generic country fallback."""
    import requests
    deadline=deadline or time.monotonic()+20
    clean = ' '.join(re.findall(r'[^\W_]+', subject))[:160]
    if not clean:
        return []
    portrait = ' portrait' if kind=='people' else ''
    searches = [f'intitle:"{clean}"{portrait} {country}', f'"{clean}"{portrait} {country}', f'intitle:"{clean}"{portrait}']
    for query in dict.fromkeys(searches):
        if time.monotonic()>deadline:break
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
                    if len(data)>1_500_000 or time.monotonic()>deadline: break
                else:
                    matches=[]
                    for photo in photo_candidates(__import__('json').loads(data), allow_art=kind=='people'):
                        title=normalized(photo['title']);desc=normalized(photo['description'])
                        evidence=title+' '+desc
                        if ' '+normalized(subject)+' ' not in ' '+evidence+' ': continue
                        country_match=' '+normalized(country)+' ' in ' '+evidence+' '
                        if kind in ('places','cities','culture','contributions') and not country_match: continue
                        if kind=='people' and re.search(r'\b(statue|bust|grave|tomb|monument|signature)\b',evidence): continue
                        title_match=' '+normalized(subject)+' ' in ' '+title+' '
                        if not title_match and desc.find(normalized(subject))>160:continue
                        if kind=='products' and title_match and title.find(normalized(subject))>40:continue
                        if kind=='products' and re.search(r'\b(patient|wound|blood|genital|penis|vagina|surgery|radiograph|radiography|radiology|xray|x ray|x rays|jugular|tomography|ct|mri|scan|lobectomy|adenocarcinoma)\b',evidence):continue
                        # A mention on a book cover, stamp or microscope slide is not a topic photo.
                        if kind not in ('people','places','cities') and any(re.search(r'\b'+word+r'\b',title) and word not in normalized(subject).split()
                            for word in ('book','books','stamp','postage','logo','epidermis','microscope','diagram','poster','corridor','park','chart','graph','output')):continue
                        photo.update(provider='wikimedia', subject=subject, subject_kind=kind,
                            country_context=country_match, image_caption=subject if country_match or kind=='people' else f'Example: {subject}',
                            _rank=(100 if title_match else 0)+(20 if country_match else 0)-max(0,title.find(normalized(subject))))
                        if kind=='products' and not country_match:
                            name=re.sub(r'\.(?:jpe?g|png|webp)$','',photo['title'],flags=re.I).replace('_',' ').strip()
                            name=re.sub(r'\s*\(\d+\)$','',name)
                            if len(name)<=90:photo['image_caption']=f'Example: {name}'
                        matches.append(photo)
                    if matches:
                        matches.sort(key=lambda p:p['_rank'],reverse=True)
                        for photo in matches:photo.pop('_rank',None)
                        return matches
        except (requests.RequestException,ValueError,TypeError): continue
    return []


def _lookup_subject_queries(country,subject,kind,queries):
    deadline=time.monotonic()+20
    for query in list(dict.fromkeys([*(queries or []),subject]))[:3]:
        if time.monotonic()>deadline:break
        photos=_lookup_subject(country,query,kind,deadline=deadline)
        if kind=='people':
            photos=[p for p in photos if ' '+normalized(subject)+' ' in ' '+normalized(p['title']+' '+p['description'])+' ']
        if photos:
            for photo in photos:
                photo['matched_query']=query
                if normalized(query)!=normalized(subject) and photo.get('country_context'):photo['image_caption']=f'Context: {query}'
            return photos
    return []

async def find_subject_photo(country, subject, kind, queries=None):
    return await asyncio.to_thread(_lookup_subject_queries,country,subject,kind,queries)


def country_scene_queries(profile, extended=False):
    cities=profile.get('geography',{}).get('major_cities',[])
    city=cities[0].get('name','') if cities else ''
    queries=['landscape nature', f'{city} city streets', 'local market daily life', 'traditional architecture countryside']
    if not extended:return queries
    # Named destinations provide country-specific topics instead of assuming every country has mountains or farms.
    places=[p.get('name','') for p in profile.get('notable_places',[]) if p.get('name')
        and p['name']!=city and not re.search(r'beach|coast',p['name'],re.I)]
    return queries + ['beach coast',places[0] if places else 'mountains hiking','wildlife birds','local food cuisine',
        'harbor boats','historic buildings','festival music culture',places[1] if len(places)>1 else 'rural agriculture']

def country_scene_plan(profile, extended=False):
    keys=['explanation_3','explanation_4','explanation_5','explanation_6']
    if extended:keys += [f'country_scene_{n}' for n in range(4,12)]
    return dict(zip(keys,country_scene_queries(profile,extended)))
