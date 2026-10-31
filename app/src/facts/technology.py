"""Technology lessons with linked system parts, walkthroughs and explanatory diagrams."""
from copy import deepcopy
from datetime import date
import re
from .schemas import _object,_items,_strings,_TEXT,_SOURCE_IDS_SCHEMA
from .physics import PHYSICS_RESPONSE_SCHEMA,_shape,_unique_ids
from .india import validate_india_images
def sourced(fields):return _object({**fields,'source_ids':_SOURCE_IDS_SCHEMA})
PART=sourced({'id':_TEXT,'name':_TEXT,'explanation':_TEXT})
COMPONENT=sourced({'id':_TEXT,'name':_TEXT,'role':_TEXT})
DIAGRAM=sourced({'type':{'type':'STRING','enum':['flow','layers','comparison']},'title':_TEXT,'caption':_TEXT,
    'description':_TEXT,'assumptions':_strings(),'node_ids':_strings(),
    'connections':_items(_object({'from_id':_TEXT,'to_id':_TEXT,'label':_TEXT,'what_moves':_TEXT})),
    'layers':_items(_object({'id':_TEXT,'title':_TEXT,'role':_TEXT,'component_ids':_strings(),'depends_on_ids':_strings()})),
    'comparison_basis':{**_TEXT,'nullable':True},
    'comparisons':_items(_object({'name':_TEXT,'approach':_TEXT,'strength':_TEXT,'limitation':_TEXT}))})
TECHNOLOGY_LESSON_SCHEMA=_object({
    'subject_type':{'type':'STRING','enum':['device','network','software_system','digital_system','material','manufacturing_process']},
    'identity':sourced({'name':_TEXT,'domain':_TEXT,'scope':_TEXT}),
    'version_context':{**sourced({'system':_TEXT,'version':_TEXT,'as_of':_TEXT,'scope':_TEXT}),'nullable':True},
    'hook':_TEXT,'question':_TEXT,'learning_goal':_TEXT,
    'opening_scenario':sourced({'title':_TEXT,'experience':_TEXT,'question':_TEXT}),
    'problem':sourced({'what_is_hard':_TEXT,'why_it_matters':_TEXT}),'central_idea':_TEXT,
    'system_model':_object({'inputs':_items(PART),'components':_items(COMPONENT),'outputs':_items(PART)}),
    'walkthrough':_items(sourced({'id':_TEXT,'title':_TEXT,'component_ids':_strings(),'what_happens':_TEXT,'what_changes':_TEXT})),
    'diagram':{**DIAGRAM,'nullable':True},
    'worked_example':sourced({'title':_TEXT,'kind':{'type':'STRING','enum':['illustrative','source_described']},
        'starting_conditions':_strings(),'actions':_strings(),'outcome':_TEXT,'explanation':_TEXT,'limits':_strings()}),
    'tradeoffs':_items(sourced({'benefit':_TEXT,'cost':_TEXT,'when_it_matters':_TEXT})),
    'failure_modes':_items(sourced({'symptom':_TEXT,'cause':_TEXT,'what_it_shows':_TEXT})),
    'practical_implications':_items(sourced({'title':_TEXT,'explanation':_TEXT})),
    'misconceptions':_items(sourced({'belief':_TEXT,'correction':_TEXT,'explanation':_TEXT})),
    'optional_depth':_items(sourced({'title':_TEXT,'explanation':_TEXT})),
    'knowledge_checks':_items(_object({'question':_TEXT,'answer':_TEXT,'explanation':_TEXT})),
    'takeaways':_strings(),'related_topics':_strings(),
    'photos':_items(_object({'id':_TEXT,'section_id':{'type':'STRING','enum':['overview','system','walkthrough','example','tradeoffs','implications']},
        'kind':{'type':'STRING','enum':['hardware','component','process','named_model','historical_object','screenshot','person']},
        'component_id':{**_TEXT,'nullable':True},'subject':_TEXT,'queries':_strings()})),
})
TECHNOLOGY_RESPONSE_SCHEMA=deepcopy(PHYSICS_RESPONSE_SCHEMA)
del TECHNOLOGY_RESPONSE_SCHEMA['properties']['physics_lesson']
TECHNOLOGY_RESPONSE_SCHEMA['required'].remove('physics_lesson')
TECHNOLOGY_RESPONSE_SCHEMA['properties'].update({'article_type':{'type':'STRING','enum':['technology_lesson']},'technology_lesson':TECHNOLOGY_LESSON_SCHEMA})
TECHNOLOGY_RESPONSE_SCHEMA['required'].append('technology_lesson')
TECHNOLOGY_RESPONSE_SCHEMA['properties']['visual_suggestions']=_object({'cover':_TEXT,'overview':_TEXT})

def valid_technology_diagram(d,system):
    if d is None:return True
    if not _shape(d,DIAGRAM):return False
    parts={p['id'] for group in system.values() for p in group}
    if d['type']=='flow':
        ids=d['node_ids'];edges=d['connections']
        if not 2<=len(ids)<=7 or len(set(ids))!=len(ids) or not set(ids)<=parts:return False
        if d['layers'] or d['comparisons'] or d['comparison_basis'] is not None:return False
        if not len(ids)-1<=len(edges)<=2*(len(ids)-1):return False
        pairs={(e['from_id'],e['to_id']) for e in edges}
        if len(pairs)!=len(edges):return False
        if any(a not in ids or b not in ids or abs(ids.index(a)-ids.index(b))!=1 for a,b in pairs):return False
        return all((a,b) in pairs or (b,a) in pairs for a,b in zip(ids,ids[1:]))
    if d['type']=='layers':
        layers=d['layers']
        if d['node_ids'] or d['connections'] or d['comparisons'] or d['comparison_basis'] is not None:return False
        if not 2<=len(layers)<=4 or not _unique_ids(layers):return False
        component_ids={p['id'] for p in system['components']};used=[]
        for i,layer in enumerate(layers):
            if not re.fullmatch('[a-z][a-z0-9_-]{0,47}',layer['id']):return False
            if not layer['component_ids'] or not set(layer['component_ids'])<=component_ids:return False
            used+=layer['component_ids']
            deps=layer['depends_on_ids'];later={l['id'] for l in layers[i+1:]}
            if len(set(deps))!=len(deps) or not set(deps)<=later or (i<len(layers)-1 and not deps):return False
        return len(set(used))==len(used)
    return (not(d['node_ids'] or d['connections'] or d['layers']) and bool(d['comparison_basis']) and 2<=len(d['comparisons'])<=3)

def technology_photo_entries(fact):
    return [dict(p,key=f'technology_photo_{i}') for i,p in enumerate(fact.get('technology_lesson',{}).get('photos',[])[:6])]

def validate_technology_content(fact):
    try:
        if not _shape(fact,TECHNOLOGY_RESPONSE_SCHEMA) or not validate_india_images(fact):return False
        l=fact['technology_lesson'];sources=fact['sources']
        if not sources or not _unique_ids(sources):return False
        ids={s['id'] for s in sources}
        def check(v):
            if isinstance(v,dict):
                if 'source_ids' in v and (not v['source_ids'] or not set(v['source_ids'])<=ids):return False
                return all(check(x) for x in v.values())
            if isinstance(v,list):return all(check(x) for x in v)
            return not isinstance(v,str) or bool(v.strip())
        if not check(l):return False
        system=l['system_model']
        if not 1<=len(system['inputs'])<=3 or not 2<=len(system['components'])<=6 or not 1<=len(system['outputs'])<=3:return False
        parts=[p for group in system.values() for p in group]
        if not _unique_ids(parts) or any(not re.fullmatch('[a-z][a-z0-9_-]{0,47}',p['id']) for p in parts):return False
        part_ids={p['id'] for p in parts};steps=l['walkthrough']
        if not 3<=len(steps)<=6 or not _unique_ids(steps) or any(not re.fullmatch('[a-z][a-z0-9_-]{0,47}',p['id']) for p in steps):return False
        if any(not p['component_ids'] or len(set(p['component_ids']))!=len(p['component_ids']) or not set(p['component_ids'])<=part_ids for p in steps):return False
        if not {p['id'] for p in system['components']}<={i for p in steps for i in p['component_ids']}:return False
        if not valid_technology_diagram(l['diagram'],system):return False
        example=l['worked_example']
        if not 1<=len(example['starting_conditions'])<=5 or not 2<=len(example['actions'])<=6 or len(example['limits'])>4:return False
        if not 1<=len(l['tradeoffs'])<=4 or not 1<=len(l['practical_implications'])<=4:return False
        if len(l['failure_modes'])>3 or len(l['optional_depth'])>3 or not 1<=len(l['misconceptions'])<=4:return False
        if not 1<=len(l['knowledge_checks'])<=3 or not 2<=len(l['takeaways'])<=5 or not 1<=len(l['related_topics'])<=6:return False
        version=l['version_context']
        if version is not None and (not re.fullmatch(r'\d{4}-\d{2}-\d{2}',version['as_of']) or date.fromisoformat(version['as_of'])>date.today()):return False
        photos=l['photos']
        if len(photos)>6 or not _unique_ids(photos) or len({p['section_id'] for p in photos})!=len(photos):return False
        for p in photos:
            if not 1<=len(p['queries'])<=2 or any(len(q)>160 for q in p['queries']):return False
            if p['component_id'] is not None and p['component_id'] not in part_ids:return False
            if p['kind']=='screenshot' and version is None:return False
        return True
    except (KeyError,TypeError,ValueError):return False

def prepare_technology_media(fact):
    fact['visual_suggestions']={k:v for k,v in fact['visual_suggestions'].items() if k in ('cover','overview')}
    fact['images']={};fact['image_credits']={}
    fact['technology_media']={'version':1,'generated_limit':2,'generated_slots':['cover','overview'],'photo_timeout_seconds':720}
    fact['technology_validation']={'structure_checked':True,'system_references_checked':True,'source_verification':'not_performed','version_verification':'not_performed','example_executed':False}

TECHNOLOGY_IMAGE_INSTRUCTIONS='''TECHNOLOGY IMAGE PLAN overrides the ordinary generated-image plan.
Generate exactly TWO labelled conceptual illustrations: cover and overview/card. Return one image_details
record for overview, placement overview, alt, caption, learning_purpose. Cover: one coherent subject,
subject center-right, quiet left for title, mobile-safe crop, no lettering, fake logos or interface text.
Overview: a different visual summary. Neither image is a real screenshot, benchmark, circuit schematic
or technical evidence. Structured system diagrams render in the UI, not through image generation.
Request zero to six useful documentary photos for distinct sections. Omit photos that do not explain
the mechanism; do not pad a software lesson with generic laptop stock. Supply kind, nullable component_id,
subject and one or two exact searches. Named models, people, historical objects and version-specific
screenshots use Commons only. Screenshots require version_context and must match that context in metadata.
Generic hardware must not impersonate a named product. Photos never trigger extra AI images.
'''

def build_technology_prompt(blocklist):
    return f'''Create ONE global technology_lesson, category technology, schema_version 2.0.
Avoid recent topics: {blocklist}. Start with a familiar action/device and explain one easy-to-medium
mechanism to a curious beginner. No India-first requirement, advanced coursework or shopping catalogue.
Choose device/network/software_system/digital_system/material/manufacturing_process. Prefer stable
concepts over hype, unreleased products or unsupported future claims. Define unfamiliar words at first use.
Identity has name, domain and scope. Give a hook, question, learning_goal, opening_scenario and problem.
Explain the central idea simply before parts and detail. system_model has 1-3 inputs, 2-6 components,
and 1-3 outputs. Every part has a globally unique simple id and name; inputs/outputs have explanation,
components have role. Distinguish information, energy and material when relevant.
Walkthrough has 3-6 connected steps: id/title/component_ids/what_happens/what_changes/source_ids.
Step and layer IDs use simple lowercase slugs, just like system part IDs.
References resolve to system part IDs. Every component must appear in the walkthrough.
Diagram is optional flow/layers/comparison with title/caption/description/assumptions/source_ids.
Flow shows ONE simplified path: node_ids are 2-7 system part IDs in path order; connections only link
adjacent nodes, in either direction or both. Every neighbouring pair connects. Each connection includes
from_id/to_id/label/what_moves. Label payloads and direction accurately. Other diagram arrays are empty.
Layers has 2-4 layers in top-to-foundation order, each with id/title/role/component_ids/depends_on_ids.
Only existing components belong to layers, each once. Dependencies point to later layers, and each
non-foundation layer has a dependency. Flow fields are empty. Comparison uses comparison_basis and
2-3 comparisons with name/approach/strength/limitation; flow and layer arrays are empty. comparison_basis
is null except in comparisons. Do not invent geometry, undocumented architectures or universal models.
worked_example has title, kind illustrative/source_described, starting_conditions, 2-6 actions, outcome,
explanation and limits. Invented examples are illustrative; never claim execution, measured performance,
real logs or actual responses. State assumptions. Use cited documented examples only when justified.
Give 1-4 tradeoffs (benefit/cost/when_it_matters), up to three failure_modes (symptom/cause/what_it_shows),
1-4 practical_implications, 1-4 misconceptions, optional_depth up to three entries, 1-3 knowledge_checks
with answer/explanation, 2-5 takeaways and related_topics. Explain consequences rather than specifications.
Optional depth clarifies the same idea; omit advanced maths and configuration tutorials.
version_context is null for stable version-independent concepts. When needed, supply system/version/as_of
(valid YYYY-MM-DD, not a future date)/scope/source_ids; explain applicability without claiming latest status.
Use credible standards, manufacturer documentation and primary technical sources. All sourced blocks
reference resolving source_ids. Do not invent source URLs, benchmark figures, versions or quotes.
Sources appear only at the bottom. Root compatibility fields agree with the lesson; historical/India fields
remain optional. This is a knowledge article, not a news roundup or product ranking.
'''
