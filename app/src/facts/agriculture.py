"""Indian farming concepts for curious readers, with explicit field context and evidence limits."""
from copy import deepcopy
from datetime import date
import math
import re
from .schemas import _object, _items, _strings, _TEXT, _SOURCE_IDS_SCHEMA
from .physics import PHYSICS_RESPONSE_SCHEMA, _shape, _unique_ids
from .india import validate_india_images

def sourced(fields):
    return _object({**fields, 'source_ids': _SOURCE_IDS_SCHEMA})

EXPLANATION = sourced({'title': _TEXT, 'explanation': _TEXT})
DIAGRAM = sourced({'type': {'type':'STRING','enum':['process','seasonal','cross_section','comparison']},
    'title':_TEXT,'caption':_TEXT,'description':_TEXT,'assumptions':_strings(),
    'process_step_ids':_strings(),
    'season_stages':_items(_object({'id':_TEXT,'title':_TEXT,'timing':_TEXT,'process_step_ids':_strings(),'what_to_notice':_TEXT})),
    'layers':_items(_object({'id':_TEXT,'name':_TEXT,'material':_TEXT,'explanation':_TEXT})),
    'connections':_items(_object({'from_id':_TEXT,'to_id':_TEXT,'label':_TEXT,'explanation':_TEXT})),
    'comparison_basis':{**_TEXT,'nullable':True},
    'comparisons':_items(_object({'name':_TEXT,'approach':_TEXT,'benefit':_TEXT,'limitation':_TEXT,'conditions':_TEXT}))})
MEASUREMENT = sourced({'id':_TEXT,'label':_TEXT,'value':{'type':'NUMBER'},'unit':_TEXT,'basis':_TEXT,
    'kind':{'type':'STRING','enum':['illustrative','reported']},'explanation':_TEXT,
    'place':{**_TEXT,'nullable':True},'period':{**_TEXT,'nullable':True},'as_of':{**_TEXT,'nullable':True}})
AGRICULTURE_LESSON_SCHEMA = _object({
    'identity':sourced({'name':_TEXT,'domain':_TEXT,'scope':_TEXT,'local_names':_strings(),
        'concept_type':{'type':'STRING','enum':['practice','natural_process','crop_system','tool','post_harvest','traditional_knowledge','innovation']}}),
    'hook':_TEXT,'question':_TEXT,'learning_goal':_TEXT,
    'opening_scenario':sourced({'title':_TEXT,'experience':_TEXT,'question':_TEXT}),
    'central_idea':_TEXT,
    'field_context':sourced({'purpose':_TEXT,'crops':_strings(),
        'growing_conditions':_items(_object({'title':_TEXT,'explanation':_TEXT})),
        'when_it_matters':{**_TEXT,'nullable':True},'indian_connection':_TEXT,'applicability_limits':_TEXT}),
    'key_terms':_items(sourced({'term':_TEXT,'meaning':_TEXT})),
    'process_steps':_items(sourced({'id':_TEXT,'title':_TEXT,'action':_TEXT,'what_changes':_TEXT,
        'why_it_matters':_TEXT,'what_to_notice':_TEXT,'conditions':_strings()})),
    'diagram':{**DIAGRAM,'nullable':True},
    'indian_case_study':sourced({'title':_TEXT,'kind':{'type':'STRING','enum':['documented_practice','research_example']},
        'place':_TEXT,'time_context':_TEXT,'crops':_strings(),'practice':_TEXT,'explanation':_TEXT,
        'connection':_TEXT,'outcome':_TEXT,'limits':_TEXT}),
    'measurements':_items(MEASUREMENT),
    'benefits_and_tradeoffs':_items(sourced({'benefit':_TEXT,'explanation':_TEXT,'requirements':_strings(),'costs_and_limits':_TEXT})),
    'conditions_and_limits':_items(EXPLANATION),
    'misconceptions':_items(sourced({'belief':_TEXT,'correction':_TEXT,'explanation':_TEXT})),
    'optional_depth':_items(EXPLANATION),
    'knowledge_checks':_items(_object({'question':_TEXT,'answer':_TEXT,'explanation':_TEXT})),
    'takeaways':_strings(),'related_topics':_strings(),
    'photos':_items(_object({'id':_TEXT,'section_id':{'type':'STRING','enum':['overview','context','process','case','tradeoffs','limits']},
        'kind':{'type':'STRING','enum':['crop','tool','material','process','named_place','person','historical_object']},
        'step_id':{**_TEXT,'nullable':True},'subject':_TEXT,'queries':_strings()}))})
AGRICULTURE_RESPONSE_SCHEMA = deepcopy(PHYSICS_RESPONSE_SCHEMA)
del AGRICULTURE_RESPONSE_SCHEMA['properties']['physics_lesson']
AGRICULTURE_RESPONSE_SCHEMA['required'].remove('physics_lesson')
AGRICULTURE_RESPONSE_SCHEMA['properties'].update({'article_type':{'type':'STRING','enum':['agriculture_lesson']},'agriculture_lesson':AGRICULTURE_LESSON_SCHEMA})
AGRICULTURE_RESPONSE_SCHEMA['required'].append('agriculture_lesson')
AGRICULTURE_RESPONSE_SCHEMA['properties']['visual_suggestions']=_object({'cover':_TEXT,'overview':_TEXT})

def simple_id(value):
    return isinstance(value,str) and bool(re.fullmatch('[a-z][a-z0-9_-]{0,47}',value))

def ordered_references(ids,steps):
    order=[s['id'] for s in steps]
    return (2<=len(ids)<=6 and len(set(ids))==len(ids) and set(ids)<=set(order)
            and ids==sorted(ids,key=order.index))

def valid_agriculture_diagram(d,steps):
    if d is None:return True
    if not _shape(d,DIAGRAM):return False
    if d['type']=='process':
        return (ordered_references(d['process_step_ids'],steps) and not(d['season_stages'] or d['layers'] or d['connections'] or d['comparisons']) and d['comparison_basis'] is None)
    if d['type']=='seasonal':
        stages=d['season_stages'];ids={s['id'] for s in steps};used=[]
        if d['process_step_ids'] or d['layers'] or d['connections'] or d['comparisons'] or d['comparison_basis'] is not None:return False
        if not 2<=len(stages)<=6 or not _unique_ids(stages):return False
        for stage in stages:
            refs=stage['process_step_ids']
            if not simple_id(stage['id']) or not refs or len(set(refs))!=len(refs) or not set(refs)<=ids:return False
            used.extend(refs)
        # A simplified season sequence progresses through the explained stages once.
        return len(set(used))==len(used) and used==sorted(used,key=[s['id'] for s in steps].index)
    if d['type']=='cross_section':
        layers=d['layers'];edges=d['connections'];ids={l['id'] for l in layers}
        return (not(d['process_step_ids'] or d['season_stages'] or d['comparisons']) and d['comparison_basis'] is None
            and 2<=len(layers)<=5 and _unique_ids(layers) and all(simple_id(l['id']) for l in layers)
            and len(edges)<=6 and len({(e['from_id'],e['to_id']) for e in edges})==len(edges)
            and all(e['from_id'] in ids and e['to_id'] in ids and e['from_id']!=e['to_id'] for e in edges))
    return (not(d['process_step_ids'] or d['season_stages'] or d['layers'] or d['connections'])
            and bool(d['comparison_basis']) and 2<=len(d['comparisons'])<=3)

def agriculture_photo_entries(fact):
    return [dict(p,key=f'agriculture_photo_{i}') for i,p in enumerate(fact.get('agriculture_lesson',{}).get('photos',[])[:6])]

def validate_agriculture_content(fact):
    try:
        if not _shape(fact,AGRICULTURE_RESPONSE_SCHEMA) or not validate_india_images(fact):return False
        l=fact['agriculture_lesson'];sources=fact['sources']
        if not sources or not _unique_ids(sources):return False
        ids={s['id'] for s in sources}
        def check(v):
            if isinstance(v,dict):
                if 'source_ids' in v and (not v['source_ids'] or not set(v['source_ids'])<=ids):return False
                return all(check(x) for x in v.values())
            if isinstance(v,list):return all(check(x) for x in v)
            return not isinstance(v,str) or bool(v.strip())
        if not check(l):return False
        steps=l['process_steps'];context=l['field_context'];case=l['indian_case_study']
        if not 3<=len(steps)<=6 or not _unique_ids(steps) or any(not simple_id(s['id']) or not 1<=len(s['conditions'])<=3 for s in steps):return False
        if not valid_agriculture_diagram(l['diagram'],steps):return False
        if len(l['identity']['local_names'])>4 or len(l['key_terms'])>6 or len(context['crops'])>6 or len(context['growing_conditions'])>4 or len(case['crops'])>6:return False
        if not 1<=len(l['benefits_and_tradeoffs'])<=4 or any(not 1<=len(b['requirements'])<=4 for b in l['benefits_and_tradeoffs']):return False
        if not 1<=len(l['conditions_and_limits'])<=4 or not 1<=len(l['misconceptions'])<=4 or len(l['optional_depth'])>3:return False
        if not 1<=len(l['knowledge_checks'])<=3 or not 2<=len(l['takeaways'])<=5 or not 1<=len(l['related_topics'])<=6:return False
        measurements=l['measurements']
        if len(measurements)>5 or not _unique_ids(measurements):return False
        for m in measurements:
            if not simple_id(m['id']) or type(m['value']) not in (int,float) or not math.isfinite(m['value']) or abs(m['value'])>1e12:return False
            if m['kind']=='reported' and any(m[k] is None for k in ('place','period','as_of')):return False
            if m['as_of'] is not None and (not re.fullmatch(r'\d{4}-\d{2}-\d{2}',m['as_of']) or date.fromisoformat(m['as_of'])>date.today()):return False
        photos=l['photos'];step_ids={s['id'] for s in steps}
        if len(photos)>6 or not _unique_ids(photos) or len({p['section_id'] for p in photos})!=len(photos):return False
        return all(simple_id(p['id']) and 1<=len(p['queries'])<=2 and all(len(q)<=160 for q in p['queries'])
            and (p['step_id'] is None or (p['section_id']=='process' and p['step_id'] in step_ids)) for p in photos)
    except (KeyError,TypeError,ValueError,OverflowError):return False

def prepare_agriculture_media(fact):
    fact['visual_suggestions']={k:v for k,v in fact['visual_suggestions'].items() if k in ('cover','overview')}
    fact['images']={};fact['image_credits']={}
    fact['agriculture_media']={'version':1,'generated_limit':2,'generated_slots':['cover','overview'],'photo_timeout_seconds':720}
    fact['agriculture_validation']={'structure_checked':True,'diagram_references_checked':True,
        'source_verification':'not_performed','agronomic_verification':'not_performed','measurement_verification':'not_performed'}

AGRICULTURE_IMAGE_INSTRUCTIONS='''AGRICULTURE IMAGE PLAN overrides the ordinary generated-image plan.
Generate exactly TWO conceptual illustrations: cover and overview/card. Return one image_details record
for overview with placement overview, caption, alt and learning_purpose. Cover: coherent farming scene,
subject center-right, quiet left for title, mobile-safe crop, no lettering or fabricated documentary claims.
Overview gives a different conceptual summary. Do not generate fake field trials, numerical charts,
diagnostic disease photographs or precise agronomic diagrams; the UI renders structured diagrams.
Request zero to six useful documentary photos, each bound to one section. Provide kind, subject,
nullable step_id and 1-2 exact concise queries. Only process photos may reference a process step.
Named people, named places and historical objects use Commons only. Do not use stock portraits for named
farmers or researchers. Popular Unsplash picks remain at the END of the existing carousel, never inline.
Photos never trigger extra generated images. Omit irrelevant stock photography.
'''

def build_agriculture_prompt(blocklist):
    return f'''Create ONE agriculture_lesson, category agriculture, schema_version 2.0.
Avoid recent topics: {blocklist}. Teach one easy-to-medium farming concept to curious non-experts,
rooted in Indian agriculture. Focus on WHY a practice/process works and where it applies, not a broad
history/policy roundup, promotional product claims or advanced agronomy. Choose practice/natural_process/
crop_system/tool/post_harvest/traditional_knowledge/innovation. Topics can include mulching, intercropping,
seed selection/storage, water harvesting, crop rotation, farm tools or region-specific farming systems.
Define unfamiliar words at first use. Respect regional differences; India has no single growing season.
identity has name/domain/scope/concept_type and up to four local_names, only when genuinely relevant.
Start with hook/question/learning_goal/opening_scenario, then a clear central_idea. field_context has
purpose, zero to six relevant crops, zero to four growing_conditions (title/explanation), nullable
when_it_matters, indian_connection and applicability_limits. Keep essential conditions visible. Storage
and tool lessons omit irrelevant field-soil, irrigation and season details. Give zero to six key_terms.
Explain 3-6 process_steps with unique lowercase slug id/title/action/what_changes/why_it_matters/
what_to_notice and 1-3 conditions each. Distinguish farmer actions from natural processes. Explain outcomes
conditionally, not as guaranteed yield gains. Teach understanding rather than a personalized field prescription.
diagram is nullable. Otherwise include type/title/caption/description/assumptions/source_ids.
process diagrams have 2-6 process_step_ids in original order; labels and explanations come from those steps.
seasonal diagrams have 2-6 season_stages with unique slug id/title/timing/process_step_ids/what_to_notice.
Use relative crop stages, or explicitly local season context; never invent a universal calendar. Each
referenced step appears once across stages, in process order. cross_section has 2-5 layers ordered
top-to-bottom, each with id/name/material/explanation, and up to six connections with from_id/to_id/label/
explanation referencing distinct existing layer IDs. Label movements and relationships; dimensions are
conceptual, not measured. Comparison has comparison_basis and 2-3 comparisons with name/approach/benefit/
limitation/conditions. All unused diagram arrays are empty; comparison_basis is null except comparison.
Give ONE sourced indian_case_study with title, kind documented_practice/research_example, place,
time_context, relevant crops, practice, explanation, connection, outcome and limits. Use a real supported
regional practice or study; do not fabricate a farmer story, institute endorsement, trial, date or source.
Use ICAR, Indian agricultural universities, public extension publications and relevant research as primary
references. Do not assume traditional or newer methods work simply because they are traditional or new.
measurements is optional, up to five records with id/label/value/unit/basis/kind illustrative or reported/
explanation/place/period/as_of/source_ids. Prefer no numbers over invented precision. Reported values
require place, period, nonfuture valid YYYY-MM-DD as_of and a source. Illustrative context can be null.
State per-plant, per-plot, per-area or other basis. No universal fertilizer/pesticide doses, diagnosed
crop diseases, unsupported savings/yield percentages, efficacy guarantees or financial returns.
Give 1-4 benefits_and_tradeoffs with benefit/explanation/1-4 requirements/costs_and_limits, 1-4
conditions_and_limits, 1-4 misconceptions belief/correction/explanation, up to three optional_depth
entries, 1-3 knowledge_checks with answer/explanation, 2-5 takeaways and 1-6 related_topics.
All factual blocks use resolving source_ids. Root compatibility fields agree with the lesson.
No inline source lists; references stay at the bottom. Do not claim independent verification or live
retrieval. Additional detail clarifies the same concept, without becoming advanced coursework.
'''
