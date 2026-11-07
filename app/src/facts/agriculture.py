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
AGRICULTURE_LESSON_SCHEMA['properties']['photos'].update(minItems=1,maxItems=18)
AGRICULTURE_RESPONSE_SCHEMA = deepcopy(PHYSICS_RESPONSE_SCHEMA)
del AGRICULTURE_RESPONSE_SCHEMA['properties']['physics_lesson']
AGRICULTURE_RESPONSE_SCHEMA['required'].remove('physics_lesson')
AGRICULTURE_RESPONSE_SCHEMA['properties'].update({'article_type':{'type':'STRING','enum':['agriculture_lesson']},'agriculture_lesson':AGRICULTURE_LESSON_SCHEMA})
AGRICULTURE_RESPONSE_SCHEMA['required'].append('agriculture_lesson')
LEGACY_AGRICULTURE_RESPONSE_SCHEMA=deepcopy(AGRICULTURE_RESPONSE_SCHEMA)
LEGACY_AGRICULTURE_RESPONSE_SCHEMA['properties']['visual_suggestions']=_object({'cover':_TEXT,'overview':_TEXT})
AGRICULTURE_RESPONSE_SCHEMA['properties']['visual_suggestions']=_object({'cover':_TEXT,'overview':_TEXT,'how_it_works':_TEXT})

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

def ensure_agriculture_photo_plan(fact,expand=False):
    """Append subject-derived requests; existing indexes and ready credits remain stable."""
    if fact.get('article_type')!='agriculture_lesson':return False
    lesson=fact.get('agriculture_lesson')
    if not isinstance(lesson,dict):return False
    old=lesson.get('photos')
    if old not in (None,[]) and (not expand or not isinstance(old,list)):return False
    if old and any(not isinstance(p,dict) or not simple_id(p.get('id')) or not p.get('section_id') for p in old):return False
    media=fact.get('agriculture_media') or {}
    if old and media.get('photo_plan_version')==2:return False
    def phrase(value):return ' '.join(value.split())[:160].strip() if isinstance(value,str) else ''
    identity=lesson.get('identity') if isinstance(lesson.get('identity'),dict) else {}
    subject=phrase(identity.get('name')) or phrase(fact.get('topic'))
    if not subject:return False
    plan=list(old or []);seen={(p.get('section_id'),p.get('step_id'),p.get('subject','').casefold()) for p in plan if isinstance(p,dict)}
    def add(section,kind,label,queries,step=None):
        label=phrase(label);key=(section,step,label.casefold())
        if not label or key in seen or len(plan)>=18:return
        q=list(dict.fromkeys(phrase(v) for v in queries if phrase(v)))[:3]
        if not q:return
        name='fallback_'+section+'_'+str(len(plan))
        while any(p.get('id')==name for p in plan):name+='x'
        plan.append(dict(id=name,section_id=section,kind=kind,step_id=step,subject=label,queries=q));seen.add(key)
    plain=phrase(re.sub(r'[^\w\s]',' ',subject).replace('_',' '))
    simpler=[]
    terms=set(plain.casefold().split())
    if 'rice' in terms and any(word.startswith('fish') for word in terms):simpler=['rice fish culture','paddy fish farming']
    add('overview','process',subject,[subject,plain,*simpler][-3:] if simpler else [subject,plain])
    context=lesson.get('field_context') if isinstance(lesson.get('field_context'),dict) else {}
    for crop in (context.get('crops') or [])[:4]:
        if phrase(crop):add('context','crop',crop,[crop+' farming',crop+' crop',crop])
    for step in (lesson.get('process_steps') or [])[:6]:
        if isinstance(step,dict) and simple_id(step.get('id')):
            title=phrase(step.get('title'))
            add('process','process',subject+' '+title,[plain+' '+title,title+' farming',simpler[0] if simpler else plain],step['id'])
    case=lesson.get('indian_case_study') if isinstance(lesson.get('indian_case_study'),dict) else {}
    place=phrase(case.get('place'))
    if place:add('case','named_place',place,[place,phrase(re.sub(r'[^\w\s]',' ',place))])
    # Explain the supported practice in these sections; do not invent a photograph of a claimed outcome.
    add('tradeoffs','process',subject,[plain,plain+' farming'])
    add('limits','process',subject,[plain,plain+' field'])
    if plan==old:return False
    lesson['photos']=plan
    if not isinstance(fact.get('agriculture_media'),dict):fact['agriculture_media']={}
    fact['agriculture_media'].update(photo_plan_version=2,photo_plan_source='expanded' if old else 'fallback')
    return True


def ensure_agriculture_science_image(fact):
    """Add one conceptual mechanism illustration to explicit legacy media retries."""
    if fact.get('article_type')!='agriculture_lesson':return False
    visuals=fact.setdefault('visual_suggestions',{})
    if visuals.get('how_it_works'):return False
    l=fact.get('agriculture_lesson') or {}
    idea=l.get('central_idea') or fact.get('core_mechanics')
    if not isinstance(idea,str) or not idea.strip():return False
    visuals['how_it_works']=('Create one educational conceptual diagram explaining this farming mechanism: '+idea[:1800]+
        '. Show the relevant materials and organisms, with clear arrows for actual movements and relationships. '
        'Use before/after panels or a cross-section only where appropriate. Do not invent chemical bonds, numerical '
        'measurements, yield claims or laboratory evidence. Use accurate short labels and a concise legend. Conceptual scale.')
    details=fact.setdefault('image_details',[])
    if not any(p.get('slot')=='how_it_works' for p in details):details.append(dict(slot='how_it_works',placement='explanation',
        alt='Conceptual illustration of the farming mechanism',caption='How the farming system works — conceptual illustration.',learning_purpose=idea[:600]))
    fact.setdefault('agriculture_media',{}).update(version=2,generated_limit=3,generated_slots=['cover','overview','how_it_works'])
    return True


def validate_agriculture_images(fact):
    visuals=fact.get('visual_suggestions',{})
    if not visuals.get('how_it_works'):return validate_india_images(fact)
    expected={'cover','overview','how_it_works'}
    if set(visuals)!=expected or any(not isinstance(visuals[k],str) or not visuals[k].strip() for k in expected):return False
    details=fact.get('image_details',[])
    return len(details)==2 and {d.get('slot') for d in details}=={'overview','how_it_works'} and all(
        d.get('placement')==('overview' if d.get('slot')=='overview' else 'explanation') and all(isinstance(d.get(k),str) and d[k].strip() for k in ('alt','caption','learning_purpose')) for d in details)

def agriculture_photo_entries(fact):
    return [dict(p,key=f'agriculture_photo_{i}') for i,p in enumerate(fact.get('agriculture_lesson',{}).get('photos',[])[:18])]

def validate_agriculture_content(fact):
    try:
        schema=AGRICULTURE_RESPONSE_SCHEMA if fact.get('visual_suggestions',{}).get('how_it_works') else LEGACY_AGRICULTURE_RESPONSE_SCHEMA
        if not _shape(fact,schema) or not validate_agriculture_images(fact):return False
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
        if not 1<=len(photos)<=18 or not _unique_ids(photos):return False
        if fact.get('visual_suggestions',{}).get('how_it_works'):
            if not {'overview','context','process','case','tradeoffs','limits'}<={p['section_id'] for p in photos}:return False
            if not step_ids<={p['step_id'] for p in photos if p['section_id']=='process'}:return False
        return all(simple_id(p['id']) and 1<=len(p['queries'])<=3 and all(len(q)<=160 for q in p['queries'])
            and (p['step_id'] is None or (p['section_id']=='process' and p['step_id'] in step_ids)) for p in photos)
    except (KeyError,TypeError,ValueError,OverflowError):return False

def prepare_agriculture_media(fact):
    fact['visual_suggestions']={k:v for k,v in fact['visual_suggestions'].items() if k in ('cover','overview','how_it_works')}
    fact['images']={};fact['image_credits']={}
    slots=['cover','overview']+(['how_it_works'] if fact['visual_suggestions'].get('how_it_works') else [])
    fact['agriculture_media']={'version':2,'generated_limit':len(slots),'generated_slots':slots,'photo_timeout_seconds':720,
        'photo_plan_version':2,'photo_plan_source':fact.get('agriculture_media',{}).get('photo_plan_source','model')}
    fact['agriculture_validation']={'structure_checked':True,'diagram_references_checked':True,
        'source_verification':'not_performed','agronomic_verification':'not_performed','measurement_verification':'not_performed'}

AGRICULTURE_IMAGE_INSTRUCTIONS='AGRICULTURE IMAGE PLAN overrides the ordinary generated-image plan.\nGenerate exactly THREE conceptual illustrations: cover, overview/card and how_it_works.\nCover: one coherent farming scene with a mobile-safe subject centre-right and quiet space for the title.\nOverview: a distinct visual summary legible as a discovery card. Science/how_it_works: explain ONE actual\nmechanism from the lesson using an accurate cross-section, before/after states or material/organism flows.\nWrite a detailed standalone prompt naming the mechanism, components, causal relationships, flow arrows,\nshort accurate labels and a legend. State conceptual scale. No invented bonds, measured results, yield\nclaims, fake field trials or diagnostic evidence. Keep geographical and historical article claims truthful.\nimage_details has overview/placement overview and how_it_works/placement explanation, with alt, caption\nand learning_purpose. Illustrations are labelled conceptual and do not replace sourced explanation.\nRequest 8-18 documentary photographs across overview, context, process, case, tradeoffs and limits.\nAllow multiple requests per section. Give each key process step its own photo request bound by step_id;\ninclude relevant crops, tools, materials and an exact case location. Each request has 2-3 distinct concise\nqueries: precise/local subject, crop or equipment term, and a simpler factual search. Do not invent names.\nNamed places, people and historical objects use Wikimedia only. Sections use Wikimedia photos;\na separate Unsplash/Pixabay pool supplies the end carousel, with text-only AI relevance ranking.\nNever use generic portraits to represent named farmers. Photos cannot prove outcomes, trial data or\nlocal applicability. Show relevant materials/practices, never unrelated agricultural stock filler.\n'

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
