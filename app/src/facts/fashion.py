"""Beginner-friendly global fashion lessons and source-bound visual requests."""
import re
from copy import deepcopy
from .schemas import _object,_items,_strings,_TEXT,_SOURCE_IDS_SCHEMA
from .physics import PHYSICS_RESPONSE_SCHEMA,_shape,_unique_ids
from .india import validate_india_images

def sourced(fields):return _object({**fields,'source_ids':_SOURCE_IDS_SCHEMA})
OPTIONAL_TEXT={**_TEXT,'nullable':True}
SUBJECT_TYPES=['garment','textile','accessory','technique','tradition']
FASHION_LESSON_SCHEMA=_object({
    'subject_type':{'type':'STRING','enum':SUBJECT_TYPES},
    'identity':sourced({'name':_TEXT,'local_name':_TEXT,'region':_TEXT,'period':_TEXT}),
    'hook':_TEXT,'question':_TEXT,'learning_goal':_TEXT,
    'introduction':sourced({'explanation':_TEXT,'why_it_matters':_TEXT}),
    'recognition_guide':_items(sourced({'id':_TEXT,'feature':_TEXT,'where_to_look':_TEXT,'why_it_matters':_TEXT,'comparison':OPTIONAL_TEXT})),
    'origin_and_context':sourced({'explanation':_TEXT,'uncertainty':_TEXT,'deeper_history':OPTIONAL_TEXT}),
    'materials':_items(sourced({'name':_TEXT,'material_type':{'type':'STRING','enum':['fibre','yarn','fabric','finish','component']},'role':_TEXT,'tradeoffs':_TEXT})),
    'construction':_items(sourced({'title':_TEXT,'explanation':_TEXT,'visible_effect':_TEXT})),
    'wearing_properties':_items(sourced({'property':_TEXT,'explanation':_TEXT,'depends_on':_TEXT})),
    'practical_guide':{**sourced({'introduction':_TEXT,'wearing_suggestions':_strings(),'use_examples':_strings(),
        'fit_and_movement':_strings(),'climate_considerations':_strings(),'cultural_considerations':_strings()}),'nullable':True},
    'care':_items(sourced({'action':_TEXT,'reason':_TEXT,'limits':_TEXT})),
    'variations':_items(sourced({'name':_TEXT,'region_or_period':_TEXT,'difference':_TEXT})),
    'misconceptions':_items(sourced({'belief':_TEXT,'correction':_TEXT,'explanation':_TEXT})),
    'takeaways':_strings(),'related_topics':_strings(),
    'photos':_items(_object({'id':_TEXT,'section_id':{'type':'STRING','enum':['overview','recognition','materials','construction','practical','variations']},
        'kind':{'type':'STRING','enum':['subject','detail','process','historical_object','person']},
        'feature_id':OPTIONAL_TEXT,'subject':_TEXT,'queries':_strings()})),
})
FASHION_RESPONSE_SCHEMA=deepcopy(PHYSICS_RESPONSE_SCHEMA)
del FASHION_RESPONSE_SCHEMA['properties']['physics_lesson']
FASHION_RESPONSE_SCHEMA['required'].remove('physics_lesson')
FASHION_RESPONSE_SCHEMA['properties'].update({'article_type':{'type':'STRING','enum':['fashion_lesson']},'fashion_lesson':FASHION_LESSON_SCHEMA})
FASHION_RESPONSE_SCHEMA['required'].append('fashion_lesson')
FASHION_RESPONSE_SCHEMA['properties']['visual_suggestions']=_object({'cover':_TEXT,'overview':_TEXT})

FASHION_IMAGE_INSTRUCTIONS='''FASHION IMAGE PLAN overrides the ordinary generated-image plan.
Generate exactly TWO illustrations: cover and overview. Return one image_details record for overview,
placement overview, alt, caption and learning_purpose. Cover: exact subject, subject center-right,
quiet left for the title, generous mobile crop margins, no writing, invented logos or faux labels.
Overview: a distinct visual summary that works as a discovery card. Label both as illustrations.
Never present generated fashion imagery as an authentic museum object, designer work or historical photo.
Request 2-6 documentary photos for distinct active sections, including recognition. Supply concise exact
subject searches, kind, and nullable feature_id. A recognition detail may reference one recognition ID.
Use historical_object/person kind for identifiable historical garments or named people; these use Commons
only. Contemporary subject/detail/process photographs can use Unsplash and Commons. Generic portraits
must never represent named people, and similar clothing must not impersonate a specific museum object.
No extra AI-image slots, diagrams with invented labels or unrelated runway/travel filler.
'''

def fashion_photo_entries(fact):
    return [dict(p,key=f'fashion_photo_{i}') for i,p in enumerate(fact.get('fashion_lesson',{}).get('photos',[])[:6])]

def validate_fashion_content(fact):
    try:
        if not _shape(fact,FASHION_RESPONSE_SCHEMA) or not validate_india_images(fact):return False
        l=fact['fashion_lesson'];sources=fact['sources']
        if not sources or not _unique_ids(sources):return False
        ids={s['id'] for s in sources}
        def check(v):
            if isinstance(v,dict):
                if 'source_ids' in v and (not v['source_ids'] or not set(v['source_ids'])<=ids):return False
                return all(check(x) for x in v.values())
            if isinstance(v,list):return all(check(x) for x in v)
            return not isinstance(v,str) or bool(v.strip())
        if not check(l):return False
        features=l['recognition_guide']
        if not 3<=len(features)<=5 or not _unique_ids(features):return False
        if any(not re.fullmatch('[a-z][a-z0-9_-]{0,47}',p['id']) for p in features):return False
        if not 1<=len(l['materials'])<=6 or not 1<=len(l['construction'])<=4:return False
        if len(l['wearing_properties'])>5 or len(l['care'])>5 or len(l['variations'])>4:return False
        if not 1<=len(l['misconceptions'])<=4 or not 2<=len(l['takeaways'])<=5 or not 1<=len(l['related_topics'])<=6:return False
        guide=l['practical_guide']
        if l['subject_type'] in ('garment','accessory') and (guide is None or not guide['wearing_suggestions']):return False
        if l['subject_type'] in ('garment','textile') and not l['wearing_properties']:return False
        if guide is not None and (not (guide['wearing_suggestions'] or guide['use_examples']) or
            any(len(guide[k])>5 for k in ('wearing_suggestions','use_examples','fit_and_movement','climate_considerations','cultural_considerations'))):return False
        photos=l['photos'];feature_ids={p['id'] for p in features}
        if not 2<=len(photos)<=6 or not _unique_ids(photos) or len({p['section_id'] for p in photos})!=len(photos):return False
        if not any(p['section_id']=='recognition' for p in photos):return False
        for p in photos:
            if not 1<=len(p['queries'])<=2 or any(len(q)>160 for q in p['queries']):return False
            if p['feature_id'] is not None and (p['section_id']!='recognition' or p['feature_id'] not in feature_ids):return False
            if p['section_id']=='practical' and guide is None:return False
            if p['section_id']=='variations' and not l['variations']:return False
        return True
    except (KeyError,TypeError,ValueError):return False

def prepare_fashion_media(fact):
    fact['visual_suggestions']={k:v for k,v in fact['visual_suggestions'].items() if k in ('cover','overview')}
    fact['images']={};fact['image_credits']={}
    fact['fashion_media']={'version':1,'generated_limit':2,'generated_slots':['cover','overview'],'photo_timeout_seconds':720}
    fact['fashion_validation']={'structure_checked':True,'source_verification':'not_performed','object_authentication':'not_performed'}

def build_fashion_prompt(blocklist):
    return f'''Create ONE global fashion_lesson, category fashion, schema_version 2.0.
Avoid recent topics: {blocklist}. Explore garments, textiles, accessories, techniques and dress traditions
across the world. Do not require an Indian origin or force an Indian connection. Indian subjects remain
eligible. Teach a curious non-expert in an accessible 6-10 minute article, not a shopping catalogue.
Use the proper subject name as topic. Set subject_type garment/textile/accessory/technique/tradition.
Identity includes name, local_name (same name if necessary), region and period without inventing dates.
Start with a question and concrete introduction. recognition_guide has 3-5 distinctive observable features:
id, feature, where_to_look, why_it_matters and nullable comparison. Teach readers what to notice before
history or outfit suggestions. Avoid generic adjectives that could describe any garment.
Explain origin_and_context accurately, including uncertainty. deeper_history can be null.
Distinguish fibre, yarn, fabric, finish and component in 1-6 materials entries. Describe role and tradeoffs.
Explain 1-4 construction choices with their visible_effect. No invented measured performance claims.
wearing_properties contains 0-5 relevant properties with explanation and depends_on, such as texture,
weight, drape, movement or comfort. Garments and textiles need at least one; irrelevant properties stay absent.
practical_guide is nullable. Garment/accessory lessons include wearing_suggestions. Technique/tradition
lessons can omit this guide, or supply useful use_examples instead of invented outfit rules.
Include fit_and_movement, climate_considerations and cultural_considerations only when relevant; empty
arrays are valid. Fit concerns movement and wearer preference, never body ratings, gender rules or shame.
Avoid universal claims that a fabric is cool, sustainable, ethical, slimming or suitable for everyone.
Care has up to five action/reason/limits entries grounded in the actual material and construction.
The item's care label and maker's instructions take priority. Do not prescribe washing for museum objects
or ceremonial pieces, assume colourfastness, or treat all blends/finishes alike. Empty care is valid.
Include up to four meaningful variations with region_or_period and difference, 1-4 misconceptions with
belief/correction/explanation, 2-5 takeaways and related_topics. Do not pad irrelevant sections.
Every sourced block references resolving source_ids. Prefer museums, textile institutions, scholarship
and credible maker documentation. Do not invent quotations, sources, heritage ownership or exact dates.
References appear only at the bottom. Explain every technical word on first use.
Root compatibility summary, headline_fact, core_mechanics and learning_takeaways agree with the lesson.
Legacy history/impact_on_india/timeline are optional; do not force them into the response.
'''
