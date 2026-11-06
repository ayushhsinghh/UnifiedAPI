"""Global drinks: history, production, mixing science and an India-accessible preparation."""
from copy import deepcopy
import math
import re
from .schemas import _object,_items,_strings,_TEXT,_SOURCE_IDS_SCHEMA
from .physics import PHYSICS_RESPONSE_SCHEMA,_shape,_unique_ids
from .food import FOOD_LESSON_SCHEMA

def sourced(fields):return _object({**fields,'source_ids':_SOURCE_IDS_SCHEMA})
NULL_TEXT={**_TEXT,'nullable':True}
SECTIONS=('overview','origin','history','method','ingredients','science','recipe','variations','serving')
RECIPE=deepcopy(FOOD_LESSON_SCHEMA['properties']['recipe'])
RECIPE['properties']['alcohol_status']={'type':'STRING','enum':['alcoholic','non_alcoholic']}
RECIPE['properties']['preparation_type']={'type':'STRING','enum':['home_mixed','serving_adaptation','alcohol_free_interpretation']}
RECIPE['required']+=['alcohol_status','preparation_type']
RECIPE['properties']['ingredients']['items']['properties']['contains_alcohol']={'type':'BOOLEAN'}
RECIPE['properties']['ingredients']['items']['required'].append('contains_alcohol')
DRINKS_LESSON_SCHEMA=_object({
 'identity':sourced({'name':_TEXT,'local_names':_strings(),'drink_type':{'type':'STRING','enum':['cocktail','mocktail','wine','spirit','beer','fermented_drink','traditional_beverage','non_alcoholic']},'country_names':_strings(),'region':_TEXT,'alcohol_status':{'type':'STRING','enum':['alcoholic','non_alcoholic','varies']},'strength_context':_TEXT}),
 'hook':_TEXT,'question':_TEXT,'learning_goal':_TEXT,
 'introduction':sourced({'explanation':_TEXT,'what_makes_it_unique':_TEXT,'cultural_role':_TEXT}),
 'origin':sourced({'account':_TEXT,'evidence_and_uncertainty':_TEXT}),
 'history':_items(sourced({'id':_TEXT,'period':_TEXT,'event':_TEXT,'why_it_changed':_TEXT})),
 'then_and_now':sourced({'earlier_method':_TEXT,'modern_method':_TEXT,'what_changed':_TEXT,'what_remains':_TEXT}),
 'sensory_profile':sourced({'flavour':_TEXT,'aroma':_TEXT,'texture':_TEXT,'finish':_TEXT,'serving_temperature':_TEXT}),
 'ingredients':_items(sourced({'id':_TEXT,'name':_TEXT,'role':_TEXT,'effect':_TEXT})),
 'production_steps':_items(sourced({'id':_TEXT,'title':_TEXT,'explanation':_TEXT,'what_to_notice':_TEXT})),
 'science':_items(sourced({'id':_TEXT,'title':_TEXT,'mechanism':_TEXT,'explanation':_TEXT,'observable_cue':_TEXT,'limits':_TEXT})),
 'science_focus_id':NULL_TEXT,'recipe':RECIPE,
 'variations':_items(sourced({'id':_TEXT,'name':_TEXT,'place':_TEXT,'difference':_TEXT,'how_it_developed':_TEXT,'evidence_and_uncertainty':_TEXT})),
 'serving_context':sourced({'glassware':_TEXT,'pairing_and_customs':_TEXT,'alcohol_free_option':NULL_TEXT,'practical_notes':_TEXT}),
 'troubleshooting':_items(_object({'problem':_TEXT,'cause':_TEXT,'fix':_TEXT})),
 'knowledge_checks':_items(_object({'question':_TEXT,'answer':_TEXT,'explanation':_TEXT})),
 'takeaways':_strings(),'related_drinks':_strings(),
 'photos':{**_items(_object({'id':_TEXT,'section_id':{'type':'STRING','enum':list(SECTIONS)},'entry_id':NULL_TEXT,
     'kind':{'type':'STRING','enum':['drink','ingredient','process','named_place','person','historical_object']},'subject':_TEXT,'queries':_strings()})),'minItems':4,'maxItems':18}})
DRINKS_RESPONSE_SCHEMA=deepcopy(PHYSICS_RESPONSE_SCHEMA)
del DRINKS_RESPONSE_SCHEMA['properties']['physics_lesson'];DRINKS_RESPONSE_SCHEMA['required'].remove('physics_lesson')
DRINKS_RESPONSE_SCHEMA['properties'].update(article_type={'type':'STRING','enum':['drinks_lesson']},drinks_lesson=DRINKS_LESSON_SCHEMA,
 visual_suggestions=_object({'cover':_TEXT,'overview':_TEXT,'how_it_works':NULL_TEXT}))
DRINKS_RESPONSE_SCHEMA['required'].append('drinks_lesson')

def simple_id(v):return isinstance(v,str) and bool(re.fullmatch('[a-z][a-z0-9_-]{0,47}',v))
def drink_refs(l):return {s:{p['id'] for p in l[k]} for s,k in [('ingredients','ingredients'),('method','production_steps'),('science','science'),('variations','variations')]}
def validate_drinks_images(f):
 try:
  l=f['drinks_lesson'];v=f['visual_suggestions'];focus=l['science_focus_id']
  active={k for k,p in v.items() if isinstance(p,str) and p.strip()}
  expected={'cover','overview'}|({'how_it_works'} if focus is not None else set())
  if active!=expected or any(k not in ('cover','overview','how_it_works') for k in v):return False
  if focus is not None and focus not in {s['id'] for s in l['science']}:return False
  details=f['image_details'];slots={d['slot'] for d in details}
  return len(details)==len(expected)-1 and slots==expected-{'cover'} and all(d['placement']==('overview' if d['slot']=='overview' else 'explanation') and all(isinstance(d.get(k),str) and d[k].strip() for k in ('alt','caption','learning_purpose')) for d in details)
 except (KeyError,TypeError):return False

def ensure_drinks_photo_plan(f):
 if f.get('article_type')!='drinks_lesson':return False
 l=f.get('drinks_lesson')
 if not isinstance(l,dict) or l.get('photos') not in (None,[]):return False
 name=(l.get('identity') or {}).get('name') or f.get('topic')
 if not isinstance(name,str) or not name.strip():return False
 name=' '.join(name.split())[:100];plan=[]
 def add(section,entry,kind,subject,queries):
  q=list(dict.fromkeys(' '.join(v.split())[:160] for v in queries if isinstance(v,str) and v.strip()))[:4]
  if q:plan.append(dict(id='fallback_'+str(len(plan)),section_id=section,entry_id=entry,kind=kind,subject=subject[:160],queries=q))
 add('overview',None,'drink',name,[name,name+' drink',name+' cocktail'])
 add('recipe',None,'drink',name,[name+' preparation',name+' ingredients'])
 for section,key,kind,limit in [('ingredients','ingredients','ingredient',3),('method','production_steps','process',2),('variations','variations','drink',3)]:
  for p in l.get(key,[])[:limit]:
   label=p.get('name') or p.get('title')
   if simple_id(p.get('id')) and isinstance(label,str) and label.strip():add(section,p['id'],kind,label if kind=='ingredient' else name+' '+label,[name+' '+label,label if kind=='ingredient' else name+' preparation'])
 l['photos']=plan;f.setdefault('drinks_media',{}).update(photo_plan_source='fallback',photo_plan_version=1)
 return True

def drinks_photo_entries(f):return [dict(p,key=f'drinks_photo_{i}') for i,p in enumerate(f.get('drinks_lesson',{}).get('photos',[])[:18])]

def validate_drinks_content(f):
 try:
  if not _shape(f,DRINKS_RESPONSE_SCHEMA) or not validate_drinks_images(f):return False
  l=f['drinks_lesson'];sources=f['sources'];ids={s['id'] for s in sources}
  if not sources or not _unique_ids(sources):return False
  def check(v):
   if isinstance(v,dict):return ('source_ids' not in v or bool(v['source_ids']) and set(v['source_ids'])<=ids) and all(check(x) for x in v.values())
   if isinstance(v,list):return all(check(x) for x in v)
   return not isinstance(v,str) or bool(v.strip())
  if not check(l):return False
  for key,low,high in [('history',2,6),('ingredients',2,10),('production_steps',2,6),('science',0,3),('variations',1,6),('photos',4,18)]:
   rows=l[key]
   if not low<=len(rows)<=high or not _unique_ids(rows) or any(not simple_id(p['id']) for p in rows):return False
  if not 1<=len(l['identity']['country_names'])<=6 or len(l['identity']['local_names'])>5:return False
  r=l['recipe'];ingredients=r['ingredients'];used={i for s in r['steps'] for i in s['ingredient_ids']}
  finite=lambda v:type(v) in (int,float) and math.isfinite(v)
  if not finite(r['servings']) or int(r['servings'])!=r['servings'] or not 1<=r['servings']<=20:return False
  if any(not finite(r[k]) or not 0<=r[k]<=2880 for k in ('prep_minutes','cook_minutes','rest_minutes')):return False
  if not 2<=len(ingredients)<=20 or not _unique_ids(ingredients) or any(not simple_id(i['id']) or not finite(i['amount']) or not 0<i['amount']<=100000 for i in ingredients):return False
  if not 2<=len(r['steps'])<=12 or not r['equipment'] or used!={i['id'] for i in ingredients}:return False
  if len(r['substitutions'])>12 or any(p['ingredient_id'] not in used for p in r['substitutions']):return False
  has_alcohol=any(i['contains_alcohol'] for i in ingredients)
  if has_alcohol!=(r['alcohol_status']=='alcoholic'):return False
  if l['identity']['alcohol_status']=='non_alcoholic' and has_alcohol:return False
  if r['preparation_type']=='alcohol_free_interpretation' and has_alcohol:return False
  refs=drink_refs(l)
  if any((p['section_id']=='science' and not l['science']) or not 1<=len(p['queries'])<=4 or any(len(q)>160 for q in p['queries']) or (p['entry_id'] is not None and p['entry_id'] not in refs.get(p['section_id'],set())) for p in l['photos']):return False
  if len({p['section_id'] for p in l['photos']})<3:return False
  return 1<=len(l['troubleshooting'])<=5 and 1<=len(l['knowledge_checks'])<=3 and 2<=len(l['takeaways'])<=5 and 1<=len(l['related_drinks'])<=6
 except (KeyError,ValueError,TypeError,OverflowError):return False

def prepare_drinks_media(f):
 f['images']={};f['image_credits']={};slots=['cover','overview']+(['how_it_works'] if f['drinks_lesson']['science_focus_id'] is not None else [])
 f['drinks_media']={'version':1,'generated_limit':len(slots),'generated_slots':slots,'photo_timeout_seconds':720,'photo_plan_source':f.get('drinks_media',{}).get('photo_plan_source','model'),'photo_plan_version':1}
 f['drinks_validation']={'structure_checked':True,'recipe_tested':False,'source_verification':'not_performed'}

DRINKS_IMAGE_INSTRUCTIONS='''DRINKS IMAGE PLAN overrides the ordinary image plan. Generate cover and overview/card illustrations,
plus at most ONE optional how_it_works image for the science_focus_id mechanism. When none helps, set
science_focus_id and how_it_works to null. No other AI slots. Cover: coherent exact drink, quiet left for
headline, center-right subject, mobile-safe crop. Overview is a different summary. Science image is a
conceptual explanation with accurate visible relationships, not invented molecular data or labels.
image_details has overview/placement overview and optional how_it_works/placement explanation, with
alt/caption/learning_purpose, labelled as illustrations. Require 4-18 documentary search requests across
at least three sections: exact drink, historical context, ingredients, preparation, serving and global
variations. Use 2-4 distinct concise queries per request, including local names, ingredient names and
simpler terms. Wikimedia is preferred. Named places, people, historical objects use Commons only.
entry_id binds only ingredients/method/science/variations records by exact ID. Multiple photos may bind
the same section; do not repeat subjects merely to fill slots. No generic unrelated bar photographs.
'''

def build_drinks_prompt(blocklist):
 return f'''Create ONE drinks_lesson, category drinks, schema_version 2.0. Avoid recent topics: {blocklist}.
Teach one accessible global cocktail, mocktail, wine, spirit, beer, fermented drink or regional beverage.
Vary continents, alcoholic and non-alcoholic drinks. Use simple language and easy-to-medium depth.
identity gives name/local_names/drink_type/country_names/region/alcohol_status/strength_context.
Distinguish documented origin from disputed stories; never invent an inventor, date or national claim.
Start hook/question/learning_goal, introduction explanation/what_makes_it_unique/cultural_role, origin
account/evidence_and_uncertainty, then 2-6 history records id/period/event/why_it_changed. Explain the
historical development, not just dates. then_and_now has earlier_method/modern_method/what_changed/
what_remains. production_steps has 2-6 id/title/explanation/what_to_notice. For wine/spirits explain
commercial production conceptually, then give a practical serving or mixing adaptation using a legally
obtained commercial base. Do not instruct home distillation or invent safe fermentation procedures.
Sensory_profile: flavour/aroma/texture/finish/serving_temperature. Ingredients: 2-10 id/name/role/effect.
Science is optional, 0-3 id/title/mechanism/explanation/observable_cue/limits: e.g. dilution and cooling,
emulsions, aromatic oils, carbonation or solubility. Avoid forcing a mechanism or pseudo-scientific health
claims. Explain why shaking or stirring matters only when relevant. science_focus_id is nullable.
Recipe follows the shared food recipe shape: title, servings integer1-20, prep/cook/rest_minutes,
equipment, traditional_preparation, adaptation_notes, ingredients id/name/amount/unit/household_measure/
preparation/role/contains_alcohol boolean, substitutions ingredient_id/substitute/quantity/effect, steps
with title/instruction/time_guidance/doneness_cue/ingredient_ids, allergens and relevant safety_notes.
Give 2-20 measured ingredients and 2-12 steps using every ingredient. Include ice/water/soda quantities
when used. Use Indian-available ingredients and practical household equipment; explain substitutions
and their effect rather than claiming exact equivalence. preparation_type is home_mixed, serving_adaptation
or alcohol_free_interpretation. recipe.alcohol_status must agree with its ingredients. Non-alcoholic
recipes cannot use rum, wine, alcoholic bitters or other alcohol-containing ingredients. Explicitly label
an alcohol-free interpretation rather than silently changing a classic. Do not claim bitters or fermented
products are alcohol-free without evidence. No invented ABV, health benefits, current prices or local
legal drinking ages. strength_context explains recipe/brand variation. Do not encourage excessive intake.
Variations:1-6 id/name/place/difference/how_it_developed/evidence_and_uncertainty, explain transmission,
local ingredients and cultural adaptation only when sourced. serving_context:glassware/pairing_and_customs/
nullable alcohol_free_option/practical_notes. Give1-5 troubleshooting,1-3 knowledge_checks with answers,
2-5 takeaways and1-6 related_drinks. Factual blocks resolve source_ids. Use credible culinary associations,
producers for methods, museums/archives for history and scientific sources for mechanisms. No invented
sources, quotations or claims of independent verification. Source lists only at the bottom. Root fields
agree with the lesson. Photos never replace complete explanations; every section needs connected prose.
'''
