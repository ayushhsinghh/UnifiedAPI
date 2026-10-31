"""Global food lessons with complete, India-accessible recipes and bounded media."""
import re
from copy import deepcopy
from .schemas import _object,_items,_strings,_TEXT,_SOURCE_IDS_SCHEMA
from .physics import PHYSICS_RESPONSE_SCHEMA,_shape,_unique_ids
from .india import validate_india_images

def sourced(fields):return _object({**fields,'source_ids':_SOURCE_IDS_SCHEMA})
NUMBER={'type':'NUMBER'}
FOOD_LESSON_SCHEMA=_object({
    'identity':sourced({'name':_TEXT,'local_name':_TEXT,'region':_TEXT,'country_names':_strings(),'food_type':_TEXT}),
    'hook':_TEXT,'question':_TEXT,'learning_goal':_TEXT,
    'introduction':sourced({'explanation':_TEXT,'how_it_is_served':_TEXT,'why_it_is_interesting':_TEXT}),
    'origin_and_context':sourced({'explanation':_TEXT,'regional_variation':_TEXT,'uncertainty':_TEXT}),
    'sensory_profile':sourced({'flavour':_TEXT,'aroma':_TEXT,'texture':_TEXT,'heat':_TEXT,'serving_temperature':_TEXT}),
    'key_ingredients':_items(sourced({'name':_TEXT,'role':_TEXT,'effect_on_taste':_TEXT})),
    'food_science':_items(sourced({'title':_TEXT,'explanation':_TEXT,'kitchen_cue':_TEXT})),
    'recipe':sourced({'title':_TEXT,'servings':NUMBER,'prep_minutes':NUMBER,'cook_minutes':NUMBER,'rest_minutes':NUMBER,
        'equipment':_strings(),'traditional_preparation':_TEXT,'adaptation_notes':_TEXT,
        'ingredients':_items(_object({'id':_TEXT,'name':_TEXT,'amount':NUMBER,'unit':_TEXT,'household_measure':_TEXT,'preparation':_TEXT,'role':_TEXT})),
        'substitutions':_items(_object({'ingredient_id':_TEXT,'substitute':_TEXT,'quantity':_TEXT,'effect':_TEXT})),
        'steps':_items(_object({'title':_TEXT,'instruction':_TEXT,'time_guidance':_TEXT,'doneness_cue':_TEXT,'ingredient_ids':_strings()})),
        'allergens':_strings(),'safety_notes':_strings()}),
    'nutrition_context':sourced({'explanation':_TEXT,'tradeoffs':_TEXT,'portion_context':_TEXT,
        'estimate_status':{'type':'STRING','enum':['estimated','not_estimated']},'serving_basis':_TEXT,'assumptions':_strings(),
        'nutrients':_items(_object({'name':_TEXT,'amount':NUMBER,'unit':_TEXT}))}),
    'serving_ideas':_items(sourced({'title':_TEXT,'explanation':_TEXT})),
    'variations':_items(sourced({'name':_TEXT,'region':_TEXT,'difference':_TEXT})),
    'troubleshooting':_items(_object({'problem':_TEXT,'cause':_TEXT,'fix':_TEXT})),
    'takeaways':_strings(),'related_foods':_strings(),
    'photos':_items(_object({'id':_TEXT,'section_id':{'type':'STRING','enum':['overview','context','taste','science','recipe','serving']},
        'subject':_TEXT,'queries':_strings()})),
})
FOOD_RESPONSE_SCHEMA=deepcopy(PHYSICS_RESPONSE_SCHEMA)
del FOOD_RESPONSE_SCHEMA['properties']['physics_lesson']
FOOD_RESPONSE_SCHEMA['required'].remove('physics_lesson')
FOOD_RESPONSE_SCHEMA['properties'].update({'article_type':{'type':'STRING','enum':['food_lesson']},'food_lesson':FOOD_LESSON_SCHEMA})
FOOD_RESPONSE_SCHEMA['required'].append('food_lesson')
FOOD_RESPONSE_SCHEMA['properties']['visual_suggestions']=_object({'cover':_TEXT,'overview':_TEXT})

FOOD_IMAGE_INSTRUCTIONS='''FOOD IMAGE PLAN overrides the ordinary generated-image plan.
Generate exactly TWO images: cover and overview. Return one image_details record for overview,
placement overview, with alt, caption and learning_purpose. The cover is a full-screen food editorial
illustration: an accurate version of the named dish, subject center-right, quiet left for the title,
safe mobile crop, no lettering. The overview explains the whole dish through a different composition.
Label these as illustrations. They do not document an authentic restaurant or recipe result.
Request 2-6 documentary photos bound to distinct sections using exact dish/ingredient/process searches.
Avoid generic restaurant, travel, or unrelated cuisine images. Photos never trigger extra AI generation.
'''

def validate_food_content(fact):
    try:
        if not _shape(fact,FOOD_RESPONSE_SCHEMA) or not validate_india_images(fact):return False
        l=fact['food_lesson'];r=l['recipe'];sources=fact['sources']
        if not sources or not _unique_ids(sources):return False
        ids={s['id'] for s in sources}
        def check(value):
            if isinstance(value,dict):
                if 'source_ids' in value and (not value['source_ids'] or not set(value['source_ids'])<=ids):return False
                return all(check(v) for v in value.values())
            if isinstance(value,list):return all(check(v) for v in value)
            return not isinstance(value,str) or bool(value.strip())
        if not check(l):return False
        if not 1<=r['servings']<=20 or int(r['servings'])!=r['servings']:return False
        if any(not 0<=r[k]<=2880 for k in ('prep_minutes','cook_minutes','rest_minutes')):return False
        if not 3<=len(r['ingredients'])<=25 or not _unique_ids(r['ingredients']):return False
        ingredient_ids={p['id'] for p in r['ingredients']}
        if any(p['amount']<=0 or not re.fullmatch('[a-z][a-z0-9_-]{0,47}',p['id']) for p in r['ingredients']):return False
        if not 3<=len(r['steps'])<=15 or not r['equipment']:return False
        used={i for step in r['steps'] for i in step['ingredient_ids']}
        if used!=ingredient_ids or any(s['ingredient_id'] not in ingredient_ids for s in r['substitutions']):return False
        if not 2<=len(l['key_ingredients'])<=8 or not 1<=len(l['food_science'])<=4:return False
        if not 1<=len(l['serving_ideas'])<=4 or not 1<=len(l['variations'])<=4:return False
        if not 1<=len(l['troubleshooting'])<=5 or not 2<=len(l['takeaways'])<=5:return False
        n=l['nutrition_context']
        if n['estimate_status']=='estimated' and (not n['nutrients'] or not n['assumptions']):return False
        if n['estimate_status']=='not_estimated' and n['nutrients']:return False
        if any(x['amount']<0 for x in n['nutrients']):return False
        photos=l['photos']
        if not 2<=len(photos)<=6 or not _unique_ids(photos) or len({p['section_id'] for p in photos})!=len(photos):return False
        if any(not 1<=len(p['queries'])<=2 or any(len(q)>160 for q in p['queries']) for p in photos):return False
        return True
    except (KeyError,TypeError,ValueError):return False

def food_photo_entries(fact):
    return [dict(p,key=f'food_photo_{i}') for i,p in enumerate(fact.get('food_lesson',{}).get('photos',[])[:6])]

def prepare_food_media(fact):
    fact['visual_suggestions']={k:v for k,v in fact['visual_suggestions'].items() if k in ('cover','overview')}
    fact['images']={};fact['image_credits']={}
    fact['food_media']={'version':1,'generated_limit':2,'generated_slots':['cover','overview'],'photo_timeout_seconds':720}
    fact['food_validation']={'structure_checked':True,'recipe_tested':False,'source_verification':'not_performed'}

def build_food_prompt(blocklist):
    return f'''Create ONE global food_lesson, category food, schema_version 2.0.
Avoid these recent topics: {blocklist}. Explore cuisines across continents; do not require an Indian
origin or Indian cultural connection. Indian dishes remain eligible, but do not dominate selection.
Choose one accessible dish or food with a concrete recipe. Vary regions, ingredients and methods.
Teach a curious beginner in simple language: meet the food, understand its taste and cultural setting,
learn why its ingredients and process work, then cook a practical adaptation in an Indian home kitchen.
Use the food's proper name as topic. identity includes name, local_name (use the same name if needed),
region, country_names and food_type. Do not assign disputed dishes an invented single birthplace.
Write complete explanations, not fragments. Sensory_profile describes flavour, aroma, texture, heat,
and serving_temperature in words, without arbitrary scores. Explain culinary and cultural value,
not just nutrition. Food_science has 1-4 clear mechanisms with observable kitchen cues.
Recipe is complete for 1-20 integer servings: grams/ml where useful, household equivalents, ingredient
preparation and role, equipment, prep/cook/rest times, and 3-15 ordered steps. Each step has time_guidance,
doneness_cue and ingredient_ids. Every ingredient appears in a step. Include water/oil/salt in quantities.
The adapted recipe uses ingredients realistically available in India. Keep traditional_preparation and
adaptation_notes explicit. Each substitution references an ingredient_id and gives quantity and effect;
never claim replacements are identical. Use an empty substitutions array when unnecessary.
Allergens describe the actual recipe and substitutions; an empty list means none identified, not a
certified allergen-free claim. Safety_notes address relevant cooking hazards with credible sources.
Use well-established preparation methods. Never invent safe storage durations or undercooked meat advice.
Nutrition_context explains useful qualities, tradeoffs and portion_context without superfood claims,
health scores, medical advice or promises. Nutrients are optional estimates for the stated serving_basis,
with assumptions and credible composition sources. Use not_estimated and an empty nutrients array
when reliable numbers are unavailable. Explain uncertainty rather than inventing precision.
Give 1-4 serving ideas and regional variations, 1-5 troubleshooting items, 2-5 takeaways and related_foods.
All sourced blocks contain resolving source_ids. Use credible culinary, cultural and food-science sources;
do not invent quotations, nutritional data or source links. References appear only at the article bottom.
Root compatibility summary/headline_fact/core_mechanics/learning_takeaways must agree with food_lesson.
Legacy historical fields are optional. Do not force impact_on_india or an unrelated timeline.
'''
