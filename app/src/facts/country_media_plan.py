"""Bounded section-photo plan, shared by generation, backfill and image state."""
import re

PHOTO_VERSION = 2
GROUPS = [('people','notable_people'),('places','notable_places'),('culture','everyday_life'),
          ('contributions','global_contributions'),('products','products_and_industries'),('cities','major_cities')]

def subject_queries(item,kind=None):
    title=item.get('name') or item.get('title') or ''
    explicit=item.get('photo_subject')
    quotes=re.findall(r"['‘\"]([^'’\"]{3,80})['’\"]",title)
    acronym=re.findall(r'\(([A-Z]{3,8})\)',item.get('explanation',''))
    lead=re.split(r'\s+(?:and|—|–)\s+|[(:]',title)[0].strip()
    lead=re.sub(r'^(?:The meaning of|Global pioneer in|Specialty highland)\s+','',lead,flags=re.I)
    named=re.findall(r'\b[A-Z][a-z]+(?:\s+(?:(?:of|for|de|la|and)\s+)?[A-Z][a-z]+){1,5}',item.get('explanation','')) if kind in ('culture','contributions') else []
    objects=[v.strip(" '\"") for group in re.findall(r'\(([^)]+)\)',title) for v in re.split(r'\s+and\s+|,',group)] if kind=='products' else []
    if kind=='products':
        objects+=re.findall(r',\s*(?:and\s+)?([a-z][a-z ]{2,35}?)(?=,| manufactured| produced| are)',item.get('explanation',''))
    if kind=='products':
        objects.sort(key=lambda value:len(value.split()),reverse=True)
        objects=[*objects,*(v[:-1] if v.endswith('s') else v for v in objects)]
    noun=lead.split()[-1] if kind=='products' and lead.split() and lead.split()[-1].casefold() not in {'devices','systems','manufacturing','industries','technology','culture','cuisine'} else None
    queries=[explicit,*(item.get('photo_queries') or []),*acronym,*quotes,*objects,*named,lead,noun,title]
    clean=[]
    for query in queries:
        if isinstance(query,str) and query.strip() and query.strip().casefold() not in [v.casefold() for v in clean]:
            clean.append(query.strip()[:160])
    return title,clean[:6]

def country_photo_entries(profile,extended=True):
    result=[]
    for kind,field in GROUPS if extended else GROUPS[:3]:
        items=profile.get('geography',{}).get(field,[]) if kind=='cities' else profile.get(field,[])
        for index,item in enumerate(items[:6]):
            title,queries=subject_queries(item,kind)
            country=profile.get('identity',{}).get('name','').casefold()
            queries=[q for q in queries if q.casefold()!=country][:3]
            if kind=='contributions' and re.search(r'ecotourism|conservation|biodiversity',title,re.I):
                nature=next((p['name'] for p in profile.get('notable_places',[]) if p.get('kind')=='natural'),None)
                if nature and nature not in queries:queries=[queries[0],nature,*queries[1:]][:3]
            if kind=='people':queries=list(dict.fromkeys([item.get('name',''),*queries]))[:3]
            if queries:result.append(dict(key=f'country_{kind}_{index}',kind=kind,index=index,
                title=title,subject=queries[0],queries=queries))
    return result
