"""Global drinks: history, production, mixing science and an India-accessible preparation."""
from copy import deepcopy
import math
import re
from .schemas import _object,_items,_strings,_TEXT,_SOURCE_IDS_SCHEMA
from .physics import PHYSICS_RESPONSE_SCHEMA,_shape,_unique_ids
from .food import FOOD_LESSON_SCHEMA

def sourced(fields):return _object({**fields,'source_ids':_SOURCE_IDS_SCHEMA})
NULL_TEXT={**_TEXT,'nullable':True}
SECTIONS=('overview','origin','history','method','ingredients','science','recipe','variations','serving','historical_making','modern_making')
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
# Notes are optional so the model never has to invent a caveat to fill a field.
for block,key in [(DRINKS_LESSON_SCHEMA['properties']['identity'],'strength_context'),
                  (DRINKS_LESSON_SCHEMA['properties']['origin'],'evidence_and_uncertainty'),
                  (DRINKS_LESSON_SCHEMA['properties']['science']['items'],'limits'),
                  (DRINKS_LESSON_SCHEMA['properties']['variations']['items'],'evidence_and_uncertainty')]:
 block['properties'][key]=NULL_TEXT
 block['required'].remove(key)
DRINKS_RESPONSE_SCHEMA=deepcopy(PHYSICS_RESPONSE_SCHEMA)
del DRINKS_RESPONSE_SCHEMA['properties']['physics_lesson'];DRINKS_RESPONSE_SCHEMA['required'].remove('physics_lesson')
DRINKS_RESPONSE_SCHEMA['properties'].update(article_type={'type':'STRING','enum':['drinks_lesson']},drinks_lesson=DRINKS_LESSON_SCHEMA,
 visual_suggestions=_object({'cover':_TEXT,'overview':_TEXT,'how_it_works':NULL_TEXT}))
DRINKS_RESPONSE_SCHEMA['required'].append('drinks_lesson')


# Versioned content keeps saved first-edition articles readable.
LEGACY_DRINKS_RESPONSE_SCHEMA=deepcopy(DRINKS_RESPONSE_SCHEMA)
DRINKS_LESSON_SCHEMA['properties']['content_version']={'type':'INTEGER'}
DRINKS_LESSON_SCHEMA['properties']['production_evolution']=_object({
 era:sourced({'context':_TEXT,'equipment':_strings(),'steps':_strings(),'result':_TEXT})
 for era in ('historical','modern')})
DRINKS_LESSON_SCHEMA['required']+=['content_version','production_evolution']
DRINKS_RESPONSE_SCHEMA['properties']['drinks_lesson']=DRINKS_LESSON_SCHEMA
DRINKS_RESPONSE_SCHEMA['properties']['visual_suggestions']=_object({'cover':_TEXT,'overview':_TEXT,'how_it_works':_TEXT})
PRE_HOOK_DRINKS_RESPONSE_SCHEMA=deepcopy(DRINKS_RESPONSE_SCHEMA)
DRINKS_LESSON_SCHEMA['properties']['opening_hook']=sourced({'heading':_TEXT,'introduction':_TEXT,'intriguing_detail':_TEXT,'bridge_question':_TEXT})
DRINKS_LESSON_SCHEMA['required'].append('opening_hook')
# Third edition gives each section a single teaching purpose; saved editions remain valid.
VERSION2_DRINKS_RESPONSE_SCHEMA=deepcopy(DRINKS_RESPONSE_SCHEMA)
DRINKS_LESSON_SCHEMA=deepcopy(DRINKS_LESSON_SCHEMA)
for key in ('opening_hook','question','learning_goal','introduction','then_and_now','production_evolution','production_steps','variations','related_drinks'):
 DRINKS_LESSON_SCHEMA['properties'].pop(key,None)
 if key in DRINKS_LESSON_SCHEMA['required']:DRINKS_LESSON_SCHEMA['required'].remove(key)
DRINKS_LESSON_SCHEMA['properties']['content_version']={'type':'INTEGER'}
DRINKS_LESSON_SCHEMA['properties']['identity']['properties']['drink_type']['enum']+=['coffee','tea','cocoa','juice','soft_drink']
DRINKS_LESSON_SCHEMA['properties']['opening']=sourced({'heading':_TEXT,'introduction':_TEXT,'question':_TEXT})
DRINKS_LESSON_SCHEMA['properties']['origin']['properties']['cultural_role']=_TEXT
DRINKS_LESSON_SCHEMA['properties']['origin']['required'].append('cultural_role')
CHANGE_KINDS=['documented_change','continuing_tradition','contemporary_alternative']
DRINKS_LESSON_SCHEMA['properties']['making']=sourced({
 'introduction':_TEXT,'evolution_kind':{'type':'STRING','enum':CHANGE_KINDS},
 'stages':_items(sourced({'id':_TEXT,'title':_TEXT,'action':_TEXT,'why_it_matters':_TEXT,'what_to_notice':_TEXT})),
 'comparisons':_items(sourced({'id':_TEXT,'aspect':_TEXT,'earlier_or_standard':_TEXT,'today_or_alternative':_TEXT,'effect':_TEXT,'relationship':{'type':'STRING','enum':CHANGE_KINDS}})),
 'defining_features':_strings()})
DRINKS_LESSON_SCHEMA['properties']['explore_drinks']=_items(sourced({
 'id':_TEXT,'name':_TEXT,'place':_TEXT,'relationship':{'type':'STRING','enum':['variation','related_drink','documented_influence']},
 'description':_TEXT,'ingredients':_strings(),'preparation':_TEXT,'taste_difference':_TEXT,'connection':_TEXT,
 'development':NULL_TEXT}))
DRINKS_LESSON_SCHEMA['required']+=['opening','making','explore_drinks']
DRINKS_LESSON_SCHEMA['properties']['photos']['maxItems']=30
DRINKS_LESSON_SCHEMA['properties']['photos']['minItems']=12
DRINKS_LESSON_SCHEMA['properties']['photos']['items']['properties']['section_id']['enum']=['overview','origin','history','ingredients','method','science','recipe','explore','serving']
DRINKS_RESPONSE_SCHEMA['properties']['drinks_lesson']=DRINKS_LESSON_SCHEMA
V3_PHOTO_SECTIONS={'overview','origin','method','ingredients','recipe','explore','serving'}

REQUIRED_PHOTO_SECTIONS={'overview','origin','historical_making','modern_making','ingredients','recipe','variations','serving'}

def modern_drinks(f):
 return f.get('drinks_lesson',{}).get('content_version') in (2,3)

def simple_id(v):return isinstance(v,str) and bool(re.fullmatch('[a-z][a-z0-9_-]{0,47}',v))
def drink_refs(l):
 refs={s:{p['id'] for p in l.get(k,[])} for s,k in [('ingredients','ingredients'),('method','production_steps'),('science','science'),('variations','variations'),('explore','explore_drinks')]}
 if l.get('content_version')==3:refs['method']={p['id'] for p in l['making']['stages']}
 return refs
def validate_drinks_images(f):
 try:
  l=f['drinks_lesson'];v=f['visual_suggestions'];focus=l['science_focus_id']
  active={k for k,p in v.items() if isinstance(p,str) and p.strip()}
  expected={'cover','overview'}|({'how_it_works'} if focus is not None else set())
  if modern_drinks(f) and focus is None:return False
  if active!=expected or any(k not in ('cover','overview','how_it_works') for k in v):return False
  if focus is not None and focus not in {s['id'] for s in l['science']}:return False
  details=f['image_details'];slots={d['slot'] for d in details}
  return len(details)==len(expected-{'cover'}) and slots==expected-{'cover'} and all(d['placement']==('overview' if d['slot']=='overview' else 'explanation') and all(isinstance(d.get(k),str) and d[k].strip() for k in ('alt','caption','learning_purpose')) for d in details)
 except (KeyError,TypeError):return False

def ensure_drinks_photo_plan(f):
 if f.get('article_type')!='drinks_lesson':return False
 l=f.get('drinks_lesson')
 if not isinstance(l,dict):return False
 name=(l.get('identity') or {}).get('name') or f.get('topic')
 if not isinstance(name,str) or not name.strip():return False
 if l.get('content_version')==3:return _ensure_v3_photo_plan(f,name)
 if l.get('photos') not in (None,[]):return False
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
 if modern_drinks(f):
  region=l['identity']['region']
  add('origin',None,'named_place',region,[region,region+' '+name])
  add('historical_making',None,'process',name+' traditional preparation',[name+' traditional preparation',name+' preparation'])
  add('modern_making',None,'process',name+' modern preparation',[name+' preparation',name+' mixing'])
  add('serving',None,'drink',name+' serving',[name+' glass',name+' serving'])
  plan=plan[:18]
  for p in plan:p['queries']=p['queries'][:3]
 l['photos']=plan;f.setdefault('drinks_media',{}).update(photo_plan_source='fallback',photo_plan_version=1)
 return True


def _ensure_v3_photo_plan(f,name):
 existing=f['drinks_lesson'].get('photos')
 if existing is None:existing=[]
 if not isinstance(existing,list) or len(existing)>30 or any(not isinstance(p,dict) for p in existing):return False
 l=f['drinks_lesson'];name=' '.join(name.split())[:100];plan=[]
 def add(section,entry,kind,subject,queries):
  if len(plan)>=30:return
  q=list(dict.fromkeys(' '.join(v.split())[:160] for v in queries if isinstance(v,str) and v.strip()))[:3]
  if len(q)<2:q.append(subject+' drink')
  plan.append(dict(id='fallback_'+str(len(plan)),section_id=section,entry_id=entry,kind=kind,subject=subject[:160],queries=q))
 add('overview',None,'drink',name,[name,name+' drink'])
 add('overview',None,'drink',name+' ingredients',[name+' ingredients',name+' glass'])
 add('recipe',None,'drink',name,[name+' preparation',name+' ingredients'])
 region=l.get('identity',{}).get('region') or name;add('origin',None,'named_place',region,[region,region+' '+name])
 add('serving',None,'drink',name,[name+' serving',name+' glass'])
 for p in l.get('ingredients',[]):add('ingredients',p['id'],'ingredient',p['name'],[p['name'],p['name']+' ingredient'])
 for p in l.get('making',{}).get('stages',[]):add('method',p['id'],'process',name+' '+p['title'],[name+' '+p['title'],name+' preparation'])
 for p in l.get('explore_drinks',[]):add('explore',p['id'],'drink',p['name'],[p['name'],p['name']+' drink'])
 # Repair partial plans too. Keep model queries and bindings; add only missing coverage.
 key=lambda p:(p.get('section_id'),p.get('entry_id'))
 merged=list(existing);covered={key(p) for p in merged}
 ids={p.get('id') for p in merged};defaults=plan
 def append(p):
  p=dict(p);base=p['id'];suffix=1
  while p['id'] in ids:
   p['id']=base+'_'+str(suffix);suffix+=1
  ids.add(p['id']);merged.append(p);covered.add(key(p))
 for p in defaults:
  if key(p) not in covered:append(p)
 for p in defaults:
  if len(merged)>=12:break
  append(p)
 if len(merged)>30:
  # Reserve one request for every required subject before retaining optional extras.
  required={key(p) for p in defaults};reserved=[]
  for i,p in enumerate(merged):
   if key(p) in required:reserved.append(i);required.remove(key(p))
  keep=set(reserved)
  for i in range(len(merged)):
   if len(keep)>=30:break
   keep.add(i)
  merged=[p for i,p in enumerate(merged) if i in keep]
 if merged==existing:return False
 l['photos']=merged;f.setdefault('drinks_media',{}).update(photo_plan_source='repaired' if existing else 'fallback',photo_plan_version=3)
 return True

def drinks_photo_entries(f):return [dict(p,key=f'drinks_photo_{i}') for i,p in enumerate(f.get('drinks_lesson',{}).get('photos',[])[:30])]

def _drinks_shape_error(value, schema, path='$'):
 if value is None and schema.get('nullable'):return None
 kind=schema['type']
 if kind=='OBJECT' and isinstance(value,dict):
  for key in schema.get('required',[]):
   if key not in value:return f'{path}.{key}: required field missing'
  for key,child in schema['properties'].items():
   if key in value:
    error=_drinks_shape_error(value[key],child,f'{path}.{key}')
    if error:return error
 elif kind=='ARRAY' and isinstance(value,list):
  if len(value)>100:return f'{path}: too many entries'
  for index,item in enumerate(value):
   error=_drinks_shape_error(item,schema['items'],f'{path}[{index}]')
   if error:return error
 elif not _shape(value,schema):return f'{path}: expected {kind} with allowed value and length'
 return None

def validate_drinks_content(f, errors=None):
 def reject(reason):
  if errors is not None:errors.append(reason)
  return False
 try:
  if f.get('drinks_lesson',{}).get('content_version') not in (None,2,3):return reject('Unsupported drinks_lesson.content_version')
  schema=(VERSION2_DRINKS_RESPONSE_SCHEMA if 'opening_hook' in f.get('drinks_lesson',{}) else PRE_HOOK_DRINKS_RESPONSE_SCHEMA) if modern_drinks(f) else LEGACY_DRINKS_RESPONSE_SCHEMA
  if f.get('drinks_lesson',{}).get('content_version')==3:schema=DRINKS_RESPONSE_SCHEMA
  shape_error=_drinks_shape_error(f,schema)
  if shape_error:return reject(shape_error)
  if not validate_drinks_images(f):return reject('Invalid drinks image plan: cover, overview, science or image_details')
  l=f['drinks_lesson'];sources=f['sources'];ids={s['id'] for s in sources}
  if not sources or not _unique_ids(sources):return reject('sources must contain unique nonempty IDs')
  def check(v):
   if isinstance(v,dict):return ('source_ids' not in v or bool(v['source_ids']) and set(v['source_ids'])<=ids) and all(check(x) for x in v.values())
   if isinstance(v,list):return all(check(x) for x in v)
   return not isinstance(v,str) or bool(v.strip())
  if not check(l):return reject('drinks_lesson contains empty text or unresolved source_ids')
  third=l.get('content_version')==3
  bounds=[('history',0 if third else 2,6),('ingredients',2,10),('science',1 if third else 0,1 if third else 3),('photos',12 if third else 4,30 if third else 18)]
  if third:bounds+=[('explore_drinks',2,8)]
  else:bounds+=[('production_steps',2,6),('variations',1,6)]
  for key,low,high in bounds:
   rows=l[key]
   if not low<=len(rows)<=high or not _unique_ids(rows) or any(not simple_id(p['id']) for p in rows):return reject(f'Invalid count or IDs in drinks_lesson.{key}: expected {low}..{high}')
  if third:
   m=l['making']
   if not 3<=len(m['stages'])<=5 or not _unique_ids(m['stages']) or any(not simple_id(p['id']) for p in m['stages']):return reject('making.stages requires 3..5 entries with unique simple IDs')
   if len(m['comparisons'])>4 or not _unique_ids(m['comparisons']) or any(not simple_id(p['id']) for p in m['comparisons']):return reject('making.comparisons allows at most 4 entries with unique simple IDs')
   if not 2<=len(m['defining_features'])<=4:return reject('making.defining_features requires 2..4 entries')
   names=[p['name'].strip().casefold() for p in l['explore_drinks']]
   if len(set(names))!=len(names) or l['identity']['name'].strip().casefold() in names:return reject('explore_drinks names must be unique and differ from the main drink')
   if any(not 1<=len(p['ingredients'])<=8 for p in l['explore_drinks']):return reject('explore_drinks ingredients requires 1..8 entries')
   for section,entries in [('ingredients',l['ingredients']),('method',m['stages']),('explore',l['explore_drinks'])]:
    if not {p['id'] for p in entries}<={p['entry_id'] for p in l['photos'] if p['section_id']==section}:return reject(f'Missing photo binding for section {section}')
  if not 1<=len(l['identity']['country_names'])<=6 or len(l['identity']['local_names'])>5:return reject('Invalid identity country_names or local_names count')
  r=l['recipe'];ingredients=r['ingredients'];used={i for s in r['steps'] for i in s['ingredient_ids']}
  finite=lambda v:type(v) in (int,float) and math.isfinite(v)
  if not finite(r['servings']) or int(r['servings'])!=r['servings'] or not 1<=r['servings']<=20:return reject('recipe.servings must be an integer from 1 to 20')
  if any(not finite(r[k]) or not 0<=r[k]<=2880 for k in ('prep_minutes','cook_minutes','rest_minutes')):return reject('recipe times must be finite and between 0 and 2880')
  if not 2<=len(ingredients)<=20 or not _unique_ids(ingredients) or any(not simple_id(i['id']) or not finite(i['amount']) or not 0<i['amount']<=100000 for i in ingredients):return reject('Invalid recipe ingredient count, IDs or amounts')
  if not 2<=len(r['steps'])<=12 or not r['equipment'] or used!={i['id'] for i in ingredients}:return reject('recipe requires 2..12 steps, equipment and exact ingredient references')
  if len(r['substitutions'])>12 or any(p['ingredient_id'] not in used for p in r['substitutions']):return reject('Invalid recipe substitutions or ingredient references')
  has_alcohol=any(i['contains_alcohol'] for i in ingredients)
  if has_alcohol!=(r['alcohol_status']=='alcoholic'):return reject('recipe.alcohol_status conflicts with ingredients')
  if l['identity']['alcohol_status']=='non_alcoholic' and has_alcohol:return reject('Non-alcoholic identity conflicts with recipe ingredients')
  if r['preparation_type']=='alcohol_free_interpretation' and has_alcohol:return reject('Alcohol-free recipe contains alcohol')
  refs=drink_refs(l)
  if any((p['section_id']=='science' and not l['science']) or not 1<=len(p['queries'])<=4 or any(len(q)>160 for q in p['queries']) or (p['entry_id'] is not None and p['entry_id'] not in refs.get(p['section_id'],set())) for p in l['photos']):return reject('Invalid photo queries or section entry references')
  if len({p['section_id'] for p in l['photos']})<3:return reject('Photos must cover at least three sections')
  if modern_drinks(f):
   if not (V3_PHOTO_SECTIONS if third else REQUIRED_PHOTO_SECTIONS)<={p['section_id'] for p in l['photos']}:return reject('Missing required photo sections')
   if any(not 2<=len(p['queries'])<=3 or len(set(q.casefold() for q in p['queries']))!=len(p['queries']) for p in l['photos']):return reject('Photos require 2..3 distinct queries')
   if not 1<=len(l['science'])<=3:return reject('science requires 1..3 entries')
   for era in ([] if third else l['production_evolution'].values()):
    if not 2<=len(era['steps'])<=6 or not 1<=len(era['equipment'])<=8:return reject('Invalid production_evolution steps or equipment count')
  if not (1<=len(l['troubleshooting'])<=5 and 1<=len(l['knowledge_checks'])<=3 and 2<=len(l['takeaways'])<=5 and (third or 1<=len(l['related_drinks'])<=6)):return reject('Invalid troubleshooting, knowledge check, takeaway or related-drink count')
  return True
 except (KeyError,ValueError,TypeError,OverflowError):return reject('Invalid field type or missing field in drinks_lesson')

def prepare_drinks_media(f):
 f['images']={};f['image_credits']={};slots=['cover','overview']+(['how_it_works'] if f['drinks_lesson']['science_focus_id'] is not None else [])
 f['drinks_media']={'version':f['drinks_lesson'].get('content_version',1),'generated_limit':len(slots),'generated_slots':slots,'photo_timeout_seconds':720,'photo_plan_source':f.get('drinks_media',{}).get('photo_plan_source','model'),'photo_plan_version':3 if f['drinks_lesson'].get('content_version')==3 else 1}
 f['drinks_validation']={'structure_checked':True,'recipe_tested':False,'source_verification':'not_performed'}

DRINKS_IMAGE_INSTRUCTIONS='DRINKS IMAGE PLAN overrides the ordinary image plan. content_version is 3.\nGenerate exactly THREE AI illustrations: cover, overview and one how_it_works science diagram.\nCover: exact drink, appropriate glassware, coherent scene, quiet left title space, centre-right mobile-safe\nsubject. Overview: a distinct visual summary with key ingredients, legible at card size. Never fabricate\nhistorical evidence. Science: one detailed standalone mechanism prompt, accurate components and causal\nrelationships, arrows, short accurate labels, legend and conceptual scale. No invented molecular bonds,\nmeasurements, medical claims or laboratory evidence. image_details has overview/placement overview and\nhow_it_works/placement explanation with alt/caption/learning_purpose labelled as illustrations.\nRequest 12-30 section photographs from Wikimedia. Cover overview, origin, ingredients, method, recipe,\nexplore and serving. Give EACH main ingredient a photo request bound to its ingredient ID and EACH\nexplore drink its own photo request bound to that entry ID. Include process stages, equipment, cultural\nsettings, named origin places and glassware where useful. Multiple photos can bind one subject.\nEach request has 2-3 distinct concise Commons queries: exact/local name, specific botanical/equipment\nterm when verified, and a simpler factual synonym. Never invent scientific names. entry_id binds only\ningredients, method (making.stages), science or explore; other sections use null entry_id.\nSmall ingredient photos are thumbnails beside their explanations. Methods, settings and drinks can use\nlarger photographs. Keep original truthful captions: a modern photo cannot document historical events.\nA separate Unsplash/Pixabay pool provides the end carousel with text-only AI ranking. It never replaces\nsection photographs or the three AI slots. No unrelated stock filler. No extra AI-generated images.\n'

def build_drinks_prompt(blocklist):
 return f'''Create ONE drinks_lesson, category drinks, schema_version 2.0, content_version 3.
Avoid recent topics: {blocklist}. Teach one accessible global drink to curious beginners, with simple
language and easy-to-medium detail. Cover cocktails, mocktails, coffee, tea, wine, spirits, beer and
regional beverages. Each section has ONE purpose. Do not repeat the same definition, ingredient list,
origin date, method or science explanation in several sections.
READING ORDER: cover; opening; Meet the drink; story; making and meaningful changes; one science
explanation; India recipe; variations and related drinks; serving; documentary carousel; recall; sources.
identity: name/local_names/drink_type/country_names/region/alcohol_status and optional strength_context.
hook is a short cover subtitle. opening has heading, introduction, question, source_ids. Write ONE
50-70 word introduction with a specific intriguing detail, not an overview repeated under two headings.
The closing question must remain UNANSWERED there; a later section answers it. No learning-goal paragraph.
Meet the drink uses identity, sensory_profile and ingredients, without a second introductory paragraph.
sensory_profile teaches flavour/aroma/texture/finish/serving_temperature. ingredients has
2-10 id/name/role/effect/source_ids entries: explain each ingredient's contribution and observable effect.
origin has account, cultural_role, optional evidence_and_uncertainty and source_ids. Tell a connected
supported story and explain its social setting. history has 0-6 id/period/event/why_it_changed/source_ids
records ONLY for meaningful milestones; avoid a forced timeline or repeating the origin prose.
making has introduction, evolution_kind, stages, comparisons, defining_features, source_ids.
evolution_kind is documented_change, continuing_tradition or contemporary_alternative. For coffee,
a traditional filter still used today is continuity; a pour-over option is an alternative, not proof of
historical progress. For wine/spirits explain commercial production conceptually and use a commercial
base for the practical recipe. Never instruct home distillation or invent safe fermentation procedures.
stages has 3-5 sourced id/title/action/why_it_matters/what_to_notice entries that teach what happens
and why. Do NOT give three separate historical, modern and process step lists. Put measured quantities
and full instructions only in recipe. comparisons has 0-4 sourced id/aspect/earlier_or_standard/
today_or_alternative/effect/relationship records, with relationship using the same three evolution kinds.
Compare specific tools, ingredients, technique or service and explain the resulting difference. Never
present a predecessor as the same named cocktail or make up historical methods. defining_features has
2-4 short features that identify the drink today; no generic What changed/What remains repetition.
science has EXACTLY ONE id/title/mechanism/explanation/observable_cue/optional limits/source_ids block.
science_focus_id resolves it. Teach cause and effect with observable examples, not the recipe again.
Recipe follows the shared food recipe shape: title, servings integer1-20, prep/cook/rest_minutes,
equipment, traditional_preparation, adaptation_notes, ingredients id/name/amount/unit/household_measure/
preparation/role/contains_alcohol boolean, substitutions ingredient_id/substitute/quantity/effect, steps
with title/instruction/time_guidance/doneness_cue/ingredient_ids, allergens and relevant safety_notes.
Give 2-20 measured ingredients and 2-12 steps using every ingredient, including measured ice/water/soda
when used. Use Indian-available ingredients, local spirits/mixers and household equipment; explain exact
substitution amounts and taste effects. preparation_type is home_mixed, serving_adaptation or
alcohol_free_interpretation. recipe.alcohol_status must match its ingredients. Non-alcoholic recipes
cannot contain alcoholic bitters or fermented products assumed to be alcohol-free. Label alcohol clearly.
explore_drinks has 2-8 sourced entries; AIM FOR SIX TO EIGHT useful, distinct entries when supported.
Each has id/name/place/relationship/description/ingredients/preparation/taste_difference/connection/
nullable development/source_ids. relationship is variation, related_drink or documented_influence.
Group genuine versions in Variations; use Related drinks for other traditions and comparisons. Similarity
is not evidence of descent. Explain each drink in 40-70 useful words across its fields: what it is,
how made, what tastes different and why it is worth comparing. Explain historical/cultural development
ONLY when supported; otherwise development is null, not invented lineage or caveats. Do not list the
main drink itself, duplicate versions, garnish-only filler or names with no explanation. Do not force
six entries if sources cannot support them. Each has its own Wikimedia photo-search request.
serving_context has glassware/pairing_and_customs/nullable alcohol_free_option/practical_notes/source_ids.
For naturally non-alcoholic coffee, tea or other drinks, alcohol_free_option is null: do not add a redundant
section explaining that the drink is already alcohol-free. Use the specific drink_type coffee/tea/cocoa/
juice/soft_drink where appropriate, rather than using non_alcoholic as its only identity.
Explain service rituals, suitable pairings and how to adjust the result, without repeating recipe steps.
Give 1-5 troubleshooting entries, 1-3 knowledge_checks with answers, and 2-5 takeaways.
All factual blocks resolve source_ids. Sources stay at the bottom. Use credible culinary associations,
producers for methods, archives for history and primary scientific sources. No invented sources, quotes,
ABV, prices, legal ages, health benefits or claims of independent verification. Root compatibility fields
agree with the lesson, but do not emit the old opening_hook/introduction/production_evolution/
then_and_now/production_steps/variations/related_drinks lesson fields in this version.

READER-READY EDITORIAL RULES (apply throughout this response, including root compatibility fields):
Write a finished beginner article that teaches the drink. Lead with what happens, how it tastes, how to
make it and why the method works. Every sentence must add a concrete fact, useful explanation or action.
Do not fill required prose with disclaimers, generic variability or statements about missing evidence.
Keep internal source/structure verification separate from article prose; never claim verification you did not perform.
origin.evidence_and_uncertainty, science[].limits and
identity.strength_context are OPTIONAL and nullable. Omit them or return null when they add nothing useful.
When the origin is genuinely disputed and this changes the story, add one short specific note in origin;
do not repeat it in the timeline, making, comparisons, recipe or takeaways. Do not manufacture a
first recipe, ratio or inventor to sound certain. If historical preparation is poorly documented, describe
a supported early published preparation, with its period/source, rather than guessing or listing unknowns.
For product differences explain their direction and practical effect: which ingredient adds sweetness,
bitterness, citrus aroma or body, and how the reader can adjust it. Avoid bare 'varies by gin' or
'formulations vary'. For substitutions state the amount and actual taste effect, not 'not an exact match'.
Explain science with observable cause and effect and an action when useful. Do not append artificial
limitations such as 'not a prediction of exact bubble counts'. Use science.limits only for a specific
condition that changes the explanation or a preparation choice; keep relevant handling guidance in the main text.
For an alcoholic requested drink, keep the primary India recipe alcoholic with accessible commercial
spirits and mixers. Offer an alcohol-free version separately; do not default to replacing the main drink.
Use the label Alcohol-free version once, without repeatedly comparing it negatively with the classic.
Keep actual allergen, alcohol-content and preparation cautions where they affect use. Do not insert
unsolicited medicine comparisons such as 'modern tonic is a mixer, not medicine' into an ordinary recipe;
if historical medicinal use is central, explain it accurately in its historical context, without health claims.
Do not hide relevant uncertainty or make unsupported positive claims. Omit a weak, nonessential claim
rather than replacing it with generic hedging. End with an editorial pass to remove repeated caveats,
negative comparisons, filler and duplicated explanations. This review must not appear in the response.
'''
