"""Geography lessons with bounded locator data and explanatory, non-executable diagrams."""
from copy import deepcopy
import math
import re
from .schemas import _object,_items,_strings,_TEXT,_SOURCE_IDS_SCHEMA
from .physics import PHYSICS_RESPONSE_SCHEMA,_shape,_unique_ids
from .india import validate_india_images

def sourced(fields):return _object({**fields,'source_ids':_SOURCE_IDS_SCHEMA})
NUMBER={'type':'NUMBER'}
LOCATION=sourced({'id':_TEXT,'name':_TEXT,'latitude':NUMBER,'longitude':NUMBER,
    'kind':{'type':'STRING','enum':['landform','water','settlement','region']},'explanation':_TEXT})
DIAGRAM=sourced({'type':{'type':'STRING','enum':['cross_section','cause_effect','comparison']},
    'title':_TEXT,'caption':_TEXT,'description':_TEXT,'assumptions':_strings(),
    'profile':_items(_object({'x':NUMBER,'height':NUMBER})),
    'nodes':_items(_object({'id':_TEXT,'label':_TEXT,'detail':_TEXT,'x':NUMBER,'y':NUMBER})),
    'connections':_items(_object({'from_id':_TEXT,'to_id':_TEXT,'label':_TEXT})),
    'comparisons':_items(_object({'label':_TEXT,'conditions':_TEXT,'explanation':_TEXT}))})
GEOGRAPHY_LESSON_SCHEMA=_object({
    'subject_type':{'type':'STRING','enum':['landform','physical_process','regional_pattern','human_environment']},
    'identity':sourced({'name':_TEXT,'region':_TEXT,'scale':_TEXT}),
    'hook':_TEXT,'question':_TEXT,'learning_goal':_TEXT,
    'opening_observation':sourced({'title':_TEXT,'observation':_TEXT,'what_to_notice':_TEXT}),
    'central_idea':_TEXT,
    'location_context':sourced({'explanation':_TEXT,'spatial_relationships':_strings(),'locations':_items(LOCATION)}),
    'map':{**sourced({'title':_TEXT,'location_ids':_strings(),'default_view':{'type':'STRING','enum':['region','world']},'what_to_notice':_TEXT}),'nullable':True},
    'key_terms':_items(_object({'term':_TEXT,'meaning':_TEXT})),
    'explanation_steps':_items(sourced({'id':_TEXT,'title':_TEXT,'explanation':_TEXT,'observable_effect':_TEXT})),
    'diagram':{**DIAGRAM,'nullable':True},
    'case_study':sourced({'title':_TEXT,'location_id':_TEXT,'observation':_TEXT,'explanation':_TEXT,'what_it_shows':_TEXT,'variability':_TEXT}),
    'human_connections':_items(sourced({'title':_TEXT,'explanation':_TEXT})),
    'variations':_items(sourced({'title':_TEXT,'conditions':_TEXT,'difference':_TEXT})),
    'misconceptions':_items(sourced({'belief':_TEXT,'correction':_TEXT,'explanation':_TEXT})),
    'limits':_strings(),'knowledge_checks':_items(_object({'question':_TEXT,'answer':_TEXT,'explanation':_TEXT})),
    'takeaways':_strings(),'related_topics':_strings(),
    'photos':_items(_object({'id':_TEXT,'section_id':{'type':'STRING','enum':['overview','location','process','case-study','connections','variations']},
        'kind':{'type':'STRING','enum':['subject','detail','process','named_place','satellite','historical_object']},
        'subject':_TEXT,'location_id':{**_TEXT,'nullable':True},'queries':_strings()})),
})
GEOGRAPHY_RESPONSE_SCHEMA=deepcopy(PHYSICS_RESPONSE_SCHEMA)
del GEOGRAPHY_RESPONSE_SCHEMA['properties']['physics_lesson']
GEOGRAPHY_RESPONSE_SCHEMA['required'].remove('physics_lesson')
GEOGRAPHY_RESPONSE_SCHEMA['properties'].update({'article_type':{'type':'STRING','enum':['geography_lesson']},'geography_lesson':GEOGRAPHY_LESSON_SCHEMA})
GEOGRAPHY_RESPONSE_SCHEMA['required'].append('geography_lesson')
GEOGRAPHY_RESPONSE_SCHEMA['properties']['visual_suggestions']=_object({'cover':_TEXT,'overview':_TEXT})

GEOGRAPHY_IMAGE_INSTRUCTIONS='''GEOGRAPHY IMAGE PLAN overrides the ordinary generated-image plan.
Generate exactly TWO labelled conceptual illustrations: cover and overview/card. Return one image_details
record for overview, placement overview, with alt, caption and learning_purpose. Cover: one coherent
subject, center-right, quiet left for the title, safe mobile crop, no words or fake map lettering.
Do not present generated terrain as a documentary photo of a named place, a real map or satellite data.
The overview is a different visual summary, not a quantitative diagram. Structured diagrams and the
locator are rendered in the UI. Request 2-6 documentary photos for distinct active sections. Use exact
subject/feature queries and a shorter alias when useful. Set location_id for named examples.
Named places, satellite imagery and historical objects use Commons only; their metadata must identify
the requested place and view. Stock photos must show the actual geographic feature, not just the region.
Photos never cause extra AI-image generation. Empty searches leave the explanation readable.
'''

def valid_geography_diagram(d):
    if d is None:return True
    if not _shape(d,DIAGRAM):return False
    if d['type']=='comparison':
        return 2<=len(d['comparisons'])<=3 and not(d['profile'] or d['nodes'] or d['connections'])
    nodes=d['nodes'];connections=d['connections']
    if d['comparisons'] or not 3<=len(nodes)<=5 or not _unique_ids(nodes) or not 2<=len(connections)<=6:return False
    if any(not re.fullmatch('[a-z][a-z0-9_-]{0,47}',n['id']) or len(n['label'])>48 or not .08<=n['x']<=.92 or not .12<=n['y']<=.85 for n in nodes):return False
    if any(math.hypot(a['x']-b['x'],a['y']-b['y'])<.22 for i,a in enumerate(nodes) for b in nodes[i+1:]):return False
    if any(abs(a['x']-b['x'])<.31 and abs(a['y']-b['y'])<.30 for i,a in enumerate(nodes) for b in nodes[i+1:]):return False
    if any(len(e['label'])>48 for e in connections):return False
    ids={n['id'] for n in nodes};edges={(e['from_id'],e['to_id']) for e in connections}
    if len(edges)!=len(connections) or any(a not in ids or b not in ids or a==b for a,b in edges):return False
    if any((b,a) in edges for a,b in edges):return False
    # Every label belongs to the explanation, rather than an isolated decorative node.
    reached={nodes[0]['id']}
    for _ in nodes:
        reached|={b for a,b in edges if a in reached}|{a for a,b in edges if b in reached}
    if reached!=ids:return False
    p=d['profile']
    if d['type']=='cause_effect':return not p
    return (4<=len(p)<=12 and p[0]['x']==0 and p[-1]['x']==1
        and all(0<=v['height']<=1 and 0<=v['x']<=1 for v in p)
        and all(a['x']<b['x'] for a,b in zip(p,p[1:])) and max(v['height'] for v in p)-min(v['height'] for v in p)>=.15)

def validate_geography_content(fact):
    try:
        if not _shape(fact,GEOGRAPHY_RESPONSE_SCHEMA) or not validate_india_images(fact):return False
        l=fact['geography_lesson'];sources=fact['sources']
        if not sources or not _unique_ids(sources):return False
        ids={s['id'] for s in sources}
        def check(v):
            if isinstance(v,dict):
                if 'source_ids' in v and (not v['source_ids'] or not set(v['source_ids'])<=ids):return False
                return all(check(x) for x in v.values())
            if isinstance(v,list):return all(check(x) for x in v)
            return not isinstance(v,str) or bool(v.strip())
        if not check(l):return False
        locations=l['location_context']['locations']
        if not 1<=len(locations)<=6 or not _unique_ids(locations):return False
        if any(not -90<=p['latitude']<=90 or not -180<=p['longitude']<=180 or len(p['name'])>80 for p in locations):return False
        location_ids={p['id'] for p in locations}
        if l['case_study']['location_id'] not in location_ids:return False
        m=l['map']
        if m is not None and (not 1<=len(m['location_ids'])<=4 or len(set(m['location_ids']))!=len(m['location_ids']) or
            not set(m['location_ids'])<=location_ids or l['case_study']['location_id'] not in m['location_ids']):return False
        steps=l['explanation_steps']
        if not 3<=len(steps)<=6 or not _unique_ids(steps) or len(l['key_terms'])>8:return False
        if not valid_geography_diagram(l['diagram']):return False
        if any(len(l[k])>4 for k in ('human_connections','variations','misconceptions','limits')):return False
        if not 1<=len(l['knowledge_checks'])<=3 or not 2<=len(l['takeaways'])<=5 or not 1<=len(l['related_topics'])<=6:return False
        photos=l['photos']
        if not 2<=len(photos)<=6 or not _unique_ids(photos) or len({p['section_id'] for p in photos})!=len(photos):return False
        for p in photos:
            if not 1<=len(p['queries'])<=2 or any(len(q)>160 for q in p['queries']):return False
            if p['location_id'] is not None and p['location_id'] not in location_ids:return False
            if p['kind'] in ('named_place','satellite') and p['location_id'] is None:return False
            if p['section_id']=='connections' and not l['human_connections']:return False
            if p['section_id']=='variations' and not l['variations']:return False
        return True
    except (KeyError,TypeError,ValueError):return False

def geography_photo_entries(fact):
    return [dict(p,key=f'geography_photo_{i}') for i,p in enumerate(fact.get('geography_lesson',{}).get('photos',[])[:6])]

def prepare_geography_media(fact):
    fact['visual_suggestions']={k:v for k,v in fact['visual_suggestions'].items() if k in ('cover','overview')}
    fact['images']={};fact['image_credits']={}
    fact['geography_media']={'version':1,'generated_limit':2,'generated_slots':['cover','overview'],'photo_timeout_seconds':720}
    fact['geography_validation']={'structure_checked':True,'coordinate_ranges_checked':True,'source_verification':'not_performed','location_verification':'not_performed'}

def build_geography_prompt(blocklist):
    return f'''Create ONE global geography_lesson, category geography, schema_version 2.0.
Avoid recent topics: {blocklist}. Choose an easy-to-medium landform, physical_process, regional_pattern
or human_environment topic across the world. No India-first requirement. Do not write a country portrait.
Ask one clear question: observe something, locate examples, explain causes and conditions, examine one
real named case study, then connect to people where useful. Use simple language for a curious beginner.
Identity has name, region and scale in plain words. Start with opening_observation and central_idea.
location_context gives an explanation, spatial_relationships and 1-6 named locations with IDs, finite
latitude/longitude, kind and explanation. Coordinates are approximate locator points, never boundaries.
Provide source_ids for the location claims. Do not invent exact precision or disputed territorial claims.
Map is nullable when it adds nothing. Otherwise give title, 1-4 resolving location_ids including the case
study, default_view region/world and what_to_notice. The UI uses real Natural Earth data, not model polygons.
Explain 3-6 connected steps with id/title/explanation/observable_effect. Define up to eight key terms.
Diagram is nullable. Use a cross_section only for a meaningful conceptual terrain profile; cause_effect
only for connected causal relationships; comparison for 2-3 conditions with explanations. No filler figures.
For comparison, profile/nodes/connections are empty. For other types, comparisons is empty, use 3-5
nodes with id, concise label (max 48 chars), detail and normalized x/y (x .08-.92, y .12-.85). Space nodes
at least .22 apart. Connect all nodes using 2-6 unique directed connections with from_id/to_id/label.
Keep node boxes separate: each pair needs horizontal separation >=.31 or vertical separation >=.30.
Connection labels have at most 48 characters.
Do not connect the same pair in both directions; explain feedback in text or a comparison instead.
Use readable labels beside the features; never only numbered circles. Cause_effect has an empty profile.
Cross_section profile has 4-12 ordered points: x from 0 to 1, height 0 to 1, first x=0, last x=1,
height range at least .15. It is conceptual, not measured terrain. Supply caption, description, assumptions
and source_ids. Never invent elevation, flow-rate, rainfall or other quantitative data to fill a diagram.
Case study has title, resolving location_id, observation, explanation, what_it_shows and variability.
Do not claim that one example proves a universal rule. Include up to four human connections, variations,
misconceptions and limits each; empty arrays are valid. Avoid deterministic claims about peoples/cultures.
Give 1-3 knowledge checks with answer and explanation, 2-5 takeaways and related topics.
Factual blocks reference resolving source_ids. Prefer geographic institutions, geological surveys,
research and authoritative maps. Do not invent sources, quotes or measurements. Sources appear only at
the bottom. Root compatibility fields agree with geography_lesson; no forced impact_on_india or timeline.
'''
