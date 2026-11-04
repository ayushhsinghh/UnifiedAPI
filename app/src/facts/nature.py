"""Observation-led Nature lessons with linked explanations and explicit evidence scope."""
from copy import deepcopy
from datetime import date
import math
import re
from .schemas import _object,_items,_strings,_TEXT,_SOURCE_IDS_SCHEMA
from .physics import PHYSICS_RESPONSE_SCHEMA,_shape,_unique_ids
from .india import validate_india_images

def sourced(fields):return _object({**fields,'source_ids':_SOURCE_IDS_SCHEMA})
NULL_TEXT={**_TEXT,'nullable':True}
DIAGRAM=sourced({'type':{'type':'STRING','enum':['labelled_structure','process','cycle','relationships','comparison']},
    'title':_TEXT,'caption':_TEXT,'description':_TEXT,'assumptions':_strings(),
    'nodes':_items(_object({'id':_TEXT,'ref_type':{'type':'STRING','enum':['feature','step','connection']},'ref_id':_TEXT,'explanation':_TEXT})),
    'edges':_items(_object({'from_id':_TEXT,'to_id':_TEXT,'label':_TEXT,'explanation':_TEXT})),
    'comparison_basis':NULL_TEXT,'comparisons':_items(_object({'name':_TEXT,'observation':_TEXT,'explanation':_TEXT,'conditions':_TEXT}))})
NATURE_LESSON_SCHEMA=_object({
    'identity':sourced({'name':_TEXT,'domain':_TEXT,'scope':_TEXT,'common_names':_strings(),'scientific_name':NULL_TEXT,
        'topic_type':{'type':'STRING','enum':['organism','phenomenon','natural_material','ecological_relationship','natural_process','structure']}}),
    'conservation_context':{**sourced({'status':_TEXT,'system':_TEXT,'scope':_TEXT,'assessed_on':_TEXT}),'nullable':True},
    'hook':_TEXT,'question':_TEXT,'learning_goal':_TEXT,
    'opening_observation':sourced({'title':_TEXT,'scene':_TEXT,'question':_TEXT}),
    'central_idea':_TEXT,
    'explanation_status':sourced({'level':{'type':'STRING','enum':['well_established','active_research','mixed']},'explanation':_TEXT}),
    'observation_context':sourced({'where':_TEXT,'when':NULL_TEXT,'conditions':_strings(),'size_context':NULL_TEXT,'time_context':NULL_TEXT,'variability':_TEXT}),
    'recognition_features':_items(sourced({'id':_TEXT,'name':_TEXT,'viewing_scale':{'type':'STRING','enum':['unaided','close_up','microscopic']},
        'what_to_look_for':_TEXT,'meaning':_TEXT,'connection':_TEXT})),
    'key_terms':_items(sourced({'term':_TEXT,'meaning':_TEXT})),
    'explanation_steps':_items(sourced({'id':_TEXT,'title':_TEXT,'explanation':_TEXT,'what_changes':_TEXT,'conditions':_strings(),
        'evidence_kind':{'type':'STRING','enum':['established_mechanism','supported_explanation','open_question']},'evidence_note':_TEXT})),
    'diagram':{**DIAGRAM,'nullable':True},
    'natural_connections':_items(sourced({'id':_TEXT,'title':_TEXT,'relationship':_TEXT,'explanation':_TEXT,'scale_or_conditions':_TEXT})),
    'real_world_example':sourced({'title':_TEXT,'kind':{'type':'STRING','enum':['organism','place','phenomenon']},'subject':_TEXT,
        'scientific_name':NULL_TEXT,'place':NULL_TEXT,'time_context':NULL_TEXT,'observation':_TEXT,'explanation':_TEXT,'connection':_TEXT,'limits':_TEXT}),
    'notice_it_yourself':{**sourced({'mode':{'type':'STRING','enum':['everyday_observation','photo_comparison']},'title':_TEXT,
        'setting':_TEXT,'steps':_strings(),'what_to_notice':_TEXT,'can_conclude':_TEXT,'cannot_conclude':_TEXT,'care_note':NULL_TEXT}),'nullable':True},
    'measurements':_items(sourced({'id':_TEXT,'label':_TEXT,'value':{'type':'NUMBER'},'unit':_TEXT,'basis':_TEXT,
        'kind':{'type':'STRING','enum':['illustrative','reported']},'explanation':_TEXT,'place':NULL_TEXT,'period':NULL_TEXT,'as_of':NULL_TEXT})),
    'variation_and_limits':_items(sourced({'title':_TEXT,'explanation':_TEXT})),
    'misconceptions':_items(sourced({'belief':_TEXT,'correction':_TEXT,'explanation':_TEXT})),
    'optional_depth':_items(sourced({'title':_TEXT,'explanation':_TEXT})),
    'knowledge_checks':_items(_object({'question':_TEXT,'answer':_TEXT,'explanation':_TEXT})),
    'takeaways':_strings(),'related_topics':_strings(),
    'photos':_items(_object({'id':_TEXT,'section_id':{'type':'STRING','enum':['overview','recognition','explanation','connections','example','observation']},
        'kind':{'type':'STRING','enum':['organism','named_species','feature','material','process','named_place','person','microscopy']},
        'feature_id':NULL_TEXT,'subject':_TEXT,'queries':_strings()}))})
NATURE_RESPONSE_SCHEMA=deepcopy(PHYSICS_RESPONSE_SCHEMA)
del NATURE_RESPONSE_SCHEMA['properties']['physics_lesson']
NATURE_RESPONSE_SCHEMA['required'].remove('physics_lesson')
NATURE_RESPONSE_SCHEMA['properties'].update({'article_type':{'type':'STRING','enum':['nature_lesson']},'nature_lesson':NATURE_LESSON_SCHEMA})
NATURE_RESPONSE_SCHEMA['required'].append('nature_lesson')
NATURE_RESPONSE_SCHEMA['properties']['visual_suggestions']=_object({'cover':_TEXT,'overview':_TEXT})

def simple_id(v):return isinstance(v,str) and bool(re.fullmatch('[a-z][a-z0-9_-]{0,47}',v))
def valid_date(v):
    try:return bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}',v)) and date.fromisoformat(v)<=date.today()
    except (ValueError,TypeError):return False
def nature_references(l):
    return {'feature':{p['id']:p for p in l['recognition_features']},'step':{p['id']:p for p in l['explanation_steps']},'connection':{p['id']:p for p in l['natural_connections']}}

def valid_nature_diagram(d,l):
    if d is None:return True
    if not _shape(d,DIAGRAM):return False
    nodes=d['nodes'];edges=d['edges']
    if d['type']=='comparison':return not nodes and not edges and bool(d['comparison_basis']) and 2<=len(d['comparisons'])<=3
    if d['comparisons'] or d['comparison_basis'] is not None or not 2<=len(nodes)<=6 or not _unique_ids(nodes):return False
    refs=nature_references(l);ids=[n['id'] for n in nodes]
    if any(not simple_id(n['id']) or n['ref_id'] not in refs[n['ref_type']] for n in nodes):return False
    if len({(n['ref_type'],n['ref_id']) for n in nodes})!=len(nodes):return False
    pairs={(e['from_id'],e['to_id']) for e in edges}
    if len(edges)>10 or len(pairs)!=len(edges) or any(a not in ids or b not in ids or a==b for a,b in pairs):return False
    if d['type']=='labelled_structure':return all(n['ref_type']=='feature' for n in nodes)
    if d['type'] in ('process','cycle'):
        order=[s['id'] for s in l['explanation_steps']];used=[n['ref_id'] for n in nodes]
        if any(n['ref_type']!='step' for n in nodes) or used!=sorted(used,key=order.index):return False
        expected=set(zip(ids,ids[1:]))
        if d['type']=='cycle':expected.add((ids[-1],ids[0]))
        return pairs==expected
    reached={ids[0]}
    for _ in nodes:
        reached|={b for a,b in pairs if a in reached}|{a for a,b in pairs if b in reached}
    return reached==set(ids)

def nature_photo_entries(fact):
    return [dict(p,key=f'nature_photo_{i}') for i,p in enumerate(fact.get('nature_lesson',{}).get('photos',[])[:6])]

def validate_nature_content(fact):
    try:
        if not _shape(fact,NATURE_RESPONSE_SCHEMA) or not validate_india_images(fact):return False
        l=fact['nature_lesson'];sources=fact['sources']
        if not sources or not _unique_ids(sources):return False
        ids={s['id'] for s in sources}
        def check(v):
            if isinstance(v,dict):
                if 'source_ids' in v and (not v['source_ids'] or not set(v['source_ids'])<=ids):return False
                return all(check(x) for x in v.values())
            if isinstance(v,list):return all(check(x) for x in v)
            return not isinstance(v,str) or bool(v.strip())
        if not check(l):return False
        if len(l['identity']['common_names'])>4 or len(l['observation_context']['conditions'])>4 or len(l['key_terms'])>6:return False
        features=l['recognition_features'];steps=l['explanation_steps'];connections=l['natural_connections']
        if len(features)>4 or not 3<=len(steps)<=6 or len(connections)>4:return False
        if any(not _unique_ids(group) or any(not simple_id(p['id']) for p in group) for group in (features,steps,connections)):return False
        if any(not 1<=len(s['conditions'])<=3 for s in steps) or not valid_nature_diagram(l['diagram'],l):return False
        example=l['real_world_example']
        if example['kind']=='organism' and example['scientific_name'] is None:return False
        if example['kind']=='place' and example['place'] is None:return False
        conservation=l['conservation_context']
        if conservation is not None and not valid_date(conservation['assessed_on']):return False
        activity=l['notice_it_yourself']
        if activity is not None and not 2<=len(activity['steps'])<=4:return False
        measurements=l['measurements']
        if len(measurements)>4 or not _unique_ids(measurements):return False
        for m in measurements:
            if type(m['value']) not in (int,float) or not math.isfinite(m['value']) or abs(m['value'])>1e12 or not simple_id(m['id']):return False
            if m['kind']=='reported' and any(m[k] is None for k in ('place','period','as_of')):return False
            if m['as_of'] is not None and not valid_date(m['as_of']):return False
        if not 1<=len(l['variation_and_limits'])<=4 or not 1<=len(l['misconceptions'])<=4 or len(l['optional_depth'])>3:return False
        if not 1<=len(l['knowledge_checks'])<=3 or not 2<=len(l['takeaways'])<=5 or not 1<=len(l['related_topics'])<=6:return False
        photos=l['photos'];feature_ids={p['id'] for p in features}
        if len(photos)>6 or not _unique_ids(photos) or len({p['section_id'] for p in photos})!=len(photos):return False
        return all(simple_id(p['id']) and 1<=len(p['queries'])<=2 and all(len(q)<=160 for q in p['queries'])
            and (p['feature_id'] is None or (p['section_id']=='recognition' and p['feature_id'] in feature_ids))
            and (p['section_id']!='recognition' or bool(features))
            and (p['section_id']!='connections' or bool(connections))
            and (p['section_id']!='observation' or activity is not None) for p in photos)
    except (KeyError,ValueError,TypeError,OverflowError):return False

def prepare_nature_media(fact):
    fact['visual_suggestions']={k:v for k,v in fact['visual_suggestions'].items() if k in ('cover','overview')}
    fact['images']={};fact['image_credits']={}
    fact['nature_media']={'version':1,'generated_limit':2,'generated_slots':['cover','overview'],'photo_timeout_seconds':720}
    fact['nature_validation']={'structure_checked':True,'diagram_references_checked':True,'source_verification':'not_performed',
        'species_verification':'not_performed','conservation_verification':'not_performed','measurement_verification':'not_performed'}

NATURE_IMAGE_INSTRUCTIONS='''NATURE IMAGE PLAN overrides the ordinary generated-image plan.
Generate exactly TWO conceptual illustrations: cover and overview/card, with one overview image_details
record containing placement overview, alt/caption/learning_purpose. Cover has one coherent subject,
center-right with quiet left for title and mobile-safe crop. No lettering, fake microscopy, fabricated
field evidence or precise anatomical claims. The overview is a different conceptual summary. Scientific
diagrams render from structured data, not generated images. Request zero to six relevant documentary
photos bound to distinct active sections, nullable feature_id and 1-2 concise subject queries.
Named species, places, people and microscopy use Commons only. Microscopy metadata must explicitly
identify the view and subject; never replace it with a generic close-up. For named_species, subject is the exact scientific name and at least one query includes it.
For microscopy, subject names only the exact organism or material, and queries also specify microscopy.
Exact species cannot be inferred
from a similar photograph. Recognition features have text explanations, not invented annotations over
photos. Popular Unsplash picks stay at the END of the existing carousel, never in exact-subject or
explanation slots. Do not create a separate popular-photo section or any additional AI images.
'''

def build_nature_prompt(blocklist):
    return f'''Create ONE global nature_lesson, category nature, schema_version 2.0.
Avoid recent topics: {blocklist}. Start with something a curious non-expert might notice, explain one
easy-to-medium concept, then help the reader recognise it again. No India-first requirement, wildlife
catalogue, generic conservation roundup or advanced biology coursework. India examples are welcome
when useful. Choose organism/phenomenon/natural_material/ecological_relationship/natural_process/structure.
identity has name/domain/scope, up to four common_names, nullable scientific_name and topic_type.
Give hook/question/learning_goal/opening_observation (title/scene/question), then central_idea.
explanation_status has level well_established/active_research/mixed and a plain explanation of the evidence.
Distinguish an observation from its explanation, an established mechanism from a hypothesis, a current
function from an evolutionary origin, and a species-specific result from a general pattern. Do not
imply intentional design with phrases such as 'nature designed this to'. Avoid unsupported adaptation stories.
observation_context states where, nullable when/size_context/time_context, up to four conditions and
variability. Explain relevant scale and duration without invented measurements or universal calendars.
Give zero to four recognition_features: id/name/viewing_scale unaided/close_up/microscopic,
what_to_look_for/meaning/connection/source_ids. Prefer 2-4 useful visible features; omit them when they
would be misleading. Never claim a microscopic structure is visible to an unaided observer. key_terms up to six.
explanation_steps has 3-6 unique lowercase slug IDs, title/explanation/what_changes/1-3 conditions,
evidence_kind established_mechanism/supported_explanation/open_question and a clear evidence_note.
Give zero to four natural_connections with id/title/relationship/explanation/scale_or_conditions/source_ids.
diagram is optional labelled_structure/process/cycle/relationships/comparison with title/caption/
description/assumptions/source_ids. Nodes have id/ref_type feature or step or connection/ref_id/explanation.
All nodes reference existing lesson records, without repeating a reference. Edges have from_id/to_id/
label/explanation, no self-edges, no duplicate directed pairs. Non-comparison diagrams have 2-6 nodes.
labelled_structure uses feature references; edges may be empty. process and cycle use step references
in lesson order, connecting exactly adjacent nodes; cycle additionally connects last to first, only
for a genuinely repeating mechanism. Do not imply energy recycles because nutrients do. relationships
must connect every node. Comparison uses a shared comparison_basis and 2-3 name/observation/explanation/
conditions records, with empty nodes/edges. Other types have comparisons empty and comparison_basis null.
No invented geometry, scales, anatomical placement or graphs with unlabeled relationships.
Give one real_world_example: title/kind organism or place or phenomenon/subject/scientific_name/place/
time_context/observation/explanation/connection/limits/source_ids. Organism examples need a sourced
scientific_name; place examples need place. Other nullable fields may be null. Prefer primary research,
natural-history museums, botanical institutions and public scientific agencies. Do not invent names,
studies, quotations or URLs. conservation_context is null unless relevant; otherwise status/system/
geographic scope/assessed_on valid nonfuture YYYY-MM-DD/source_ids. Never claim 'latest' without retrieval.
notice_it_yourself is nullable, or mode everyday_observation/photo_comparison, title/setting/2-4 steps/
what_to_notice/can_conclude/cannot_conclude/nullable care_note/source_ids. Use looking, listening or
photo comparison without collecting, handling, feeding or disturbing wildlife. No tasting unknown
organisms, unsafe access, direct Sun viewing or claimed species identification from one clue. Omit
an unsafe or pointless activity; an accessible photo comparison is valid. Explain what one observation
cannot establish. Keep a care_note visible only when there is a relevant observation boundary.
Optional measurements up to four: id/label/value/unit/basis/kind illustrative or reported/explanation/
place/period/as_of/source_ids. Reported values require all context and a valid nonfuture ISO date.
Numbers must be finite and within 1e12. Use no numbers instead of invented precision.
Give 1-4 variation_and_limits, 1-4 misconceptions belief/correction/explanation, up to three optional_depth,
1-3 knowledge_checks with answer/explanation, 2-5 takeaways and 1-6 related_topics. All factual blocks
use resolving source_ids. Sources only at the bottom; root compatibility fields agree with the lesson.
Never claim independent source, species, conservation or measurement verification. Photos have id/
section_id overview/recognition/explanation/connections/example/observation, kind organism/named_species/
feature/material/process/named_place/person/microscopy, nullable feature_id/subject/queries. A feature_id
can bind only recognition photos. Omit requests for absent recognition/connections/observation sections.
'''
