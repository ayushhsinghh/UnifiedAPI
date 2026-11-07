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
DRINKS_LESSON_SCHEMA['properties']['content_version']={'type':'INTEGER','enum':[2]}
DRINKS_LESSON_SCHEMA['properties']['production_evolution']=_object({
 era:sourced({'context':_TEXT,'equipment':_strings(),'steps':_strings(),'result':_TEXT})
 for era in ('historical','modern')})
DRINKS_LESSON_SCHEMA['required']+=['content_version','production_evolution']
DRINKS_RESPONSE_SCHEMA['properties']['drinks_lesson']=DRINKS_LESSON_SCHEMA
DRINKS_RESPONSE_SCHEMA['properties']['visual_suggestions']=_object({'cover':_TEXT,'overview':_TEXT,'how_it_works':_TEXT})
PRE_HOOK_DRINKS_RESPONSE_SCHEMA=deepcopy(DRINKS_RESPONSE_SCHEMA)
DRINKS_LESSON_SCHEMA['properties']['opening_hook']=sourced({'heading':_TEXT,'introduction':_TEXT,'intriguing_detail':_TEXT,'bridge_question':_TEXT})
DRINKS_LESSON_SCHEMA['required'].append('opening_hook')
REQUIRED_PHOTO_SECTIONS={'overview','origin','historical_making','modern_making','ingredients','recipe','variations','serving'}

def modern_drinks(f):
 return f.get('drinks_lesson',{}).get('content_version')==2

def simple_id(v):return isinstance(v,str) and bool(re.fullmatch('[a-z][a-z0-9_-]{0,47}',v))
def drink_refs(l):return {s:{p['id'] for p in l[k]} for s,k in [('ingredients','ingredients'),('method','production_steps'),('science','science'),('variations','variations')]}
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

def drinks_photo_entries(f):return [dict(p,key=f'drinks_photo_{i}') for i,p in enumerate(f.get('drinks_lesson',{}).get('photos',[])[:18])]

def validate_drinks_content(f):
 try:
  if f.get('drinks_lesson',{}).get('content_version') not in (None,2):return False
  schema=(DRINKS_RESPONSE_SCHEMA if 'opening_hook' in f.get('drinks_lesson',{}) else PRE_HOOK_DRINKS_RESPONSE_SCHEMA) if modern_drinks(f) else LEGACY_DRINKS_RESPONSE_SCHEMA
  if not _shape(f,schema) or not validate_drinks_images(f):return False
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
  if modern_drinks(f):
   if not REQUIRED_PHOTO_SECTIONS<={p['section_id'] for p in l['photos']}:return False
   if any(not 2<=len(p['queries'])<=3 or len(set(q.casefold() for q in p['queries']))!=len(p['queries']) for p in l['photos']):return False
   if not 1<=len(l['science'])<=3:return False
   for era in l['production_evolution'].values():
    if not 2<=len(era['steps'])<=6 or not 1<=len(era['equipment'])<=8:return False
  return 1<=len(l['troubleshooting'])<=5 and 1<=len(l['knowledge_checks'])<=3 and 2<=len(l['takeaways'])<=5 and 1<=len(l['related_drinks'])<=6
 except (KeyError,ValueError,TypeError,OverflowError):return False

def prepare_drinks_media(f):
 f['images']={};f['image_credits']={};slots=['cover','overview']+(['how_it_works'] if f['drinks_lesson']['science_focus_id'] is not None else [])
 f['drinks_media']={'version':2 if modern_drinks(f) else 1,'generated_limit':len(slots),'generated_slots':slots,'photo_timeout_seconds':720,'photo_plan_source':f.get('drinks_media',{}).get('photo_plan_source','model'),'photo_plan_version':1}
 f['drinks_validation']={'structure_checked':True,'recipe_tested':False,'source_verification':'not_performed'}

DRINKS_IMAGE_INSTRUCTIONS='DRINKS IMAGE PLAN overrides all other image instructions. content_version is 2.\nGenerate exactly THREE AI images: cover, overview and ONE Science of Mixing diagram.\nCover: show the exact drink in its appropriate glassware, a coherent scene with quiet space on the left\nfor the title and a mobile-safe subject near the centre-right. No text or invented historical evidence.\nOverview: a distinct educational composition showing the finished drink and its key ingredients;\nkeep it legible at card size. Label both as illustrations, not documentary photographs. Set how_it_works to a detailed standalone educational diagram prompt\nfor the science_focus_id mechanism. Specify subject, before/after states, physical relationships,\nflow arrows, short accurate labels, composition, colour legend and what must NOT be implied.\nDo not invent molecular bonds, numerical data or laboratory evidence. Explicitly label conceptual scale.\nimage_details contains overview with placement overview and how_it_works with placement explanation;\nboth have alt/caption/learning_purpose. Cover and overview/card use the AI-generated assets.\nWikimedia photographs supplement the article sections and must never overwrite those AI slots.\nProvide 8-18 documentary requests. REQUIRED sections: overview, origin, historical_making,\nmodern_making, ingredients, recipe, variations, serving. Each request has exactly 2-3 DISTINCT\nWikimedia Commons search queries. Include precise regional/local drink names, documented historical\nterms, verified botanical ingredient names, equipment and glassware types where appropriate. Do not\ninvent Latin names. Progress from exact subject to a simpler factual synonym. Avoid long sentences.\nGive each major ingredient and regional variation its own request where possible. entry_id binds only\ningredients/method/science/variations records; all other requests have null entry_id. Use relevant\nhistorical-object queries only for actual documented objects. Never caption a modern photograph as\nhistorical evidence. A search plan is not a guarantee of a relevant photograph. No unrelated filler.\n'

def build_drinks_prompt(blocklist):
 return f'''Create ONE drinks_lesson, category drinks, schema_version 2.0. Avoid recent topics: {blocklist}.
Set drinks_lesson.content_version=2. Expand each main explanation into 2-3 complete short paragraphs.
Begin with opening_hook: heading, introduction, intriguing_detail, bridge_question, source_ids.
This open section appears before the overview. Write a curiosity-led heading, then 60-90 words total
across introduction and intriguing_detail: identify the drink, describe its character and explain one
concrete supported detail. End with a short bridge_question answered explicitly later in this lesson.
Do not repeat the cover hook, overview question or introduction. No clickbait, invented surprise or
unsupported sensory/health claims. Resolve source_ids for factual statements. No image for this section.
Use concrete drink-specific detail, not generic filler or repeated summaries. Explain cultural significance,
country and region and the documented development of the drink. Include an invention story only when supported.
production_evolution has historical and modern objects, each with context, equipment (1-8 names),
steps (2-6 complete explanations), result, source_ids. Compare historical tools, ingredients and constraints
with contemporary craft or commercial techniques and explain their effect on the finished drink.
Retain then_and_now as a short comparison summary, not duplicated paragraphs. Production steps teach
key controls rather than repeat the recipe. Omit unsupported historical details instead of filling paragraphs with what is unknown.
For Indian adaptation prefer the requested drink with accessible local spirits/mixers when alcoholic;
also explain a separately labelled alcohol-free direction. Include practical Desi substitutions, exact amounts,
where the ingredient is commonly available, flavour tradeoffs and equipment alternatives without brand endorsements.
Teach one accessible global cocktail, mocktail, wine, spirit, beer, fermented drink or regional beverage.
Vary continents, alcoholic and non-alcoholic drinks. Use simple language and easy-to-medium depth.
identity gives name/local_names/drink_type/country_names/region/alcohol_status/strength_context.
Use supported origin information; never invent an inventor, date or national claim. One useful historical qualification is enough.
Start hook/question/learning_goal, introduction explanation/what_makes_it_unique/cultural_role, origin
account/evidence_and_uncertainty, then 2-6 history records id/period/event/why_it_changed. Explain the
historical development, not just dates. then_and_now has earlier_method/modern_method/what_changed/
what_remains. production_steps has 2-6 id/title/explanation/what_to_notice. For wine/spirits explain
commercial production conceptually, then give a practical serving or mixing adaptation using a legally
obtained commercial base. Do not instruct home distillation or invent safe fermentation procedures.
Sensory_profile: flavour/aroma/texture/finish/serving_temperature. Ingredients: 2-10 id/name/role/effect.
Science is required, 1-3 id/title/mechanism/explanation/observable_cue/limits: e.g. dilution and cooling,
emulsions, aromatic oils, carbonation or solubility. Avoid forcing a mechanism or pseudo-scientific health
claims. Explain why shaking or stirring matters only when relevant. science_focus_id must identify the one mechanism illustrated by how_it_works. Explain cause, observable effect and practical control, defining technical words. Use only mechanisms relevant to this drink; never force clarify-washing or molecular binding where unsupported.
Recipe follows the shared food recipe shape: title, servings integer1-20, prep/cook/rest_minutes,
equipment, traditional_preparation, adaptation_notes, ingredients id/name/amount/unit/household_measure/
preparation/role/contains_alcohol boolean, substitutions ingredient_id/substitute/quantity/effect, steps
with title/instruction/time_guidance/doneness_cue/ingredient_ids, allergens and relevant safety_notes.
Give 2-20 measured ingredients and 2-12 steps using every ingredient. Include ice/water/soda quantities
when used. Use Indian-available ingredients and practical household equipment; explain substitutions
with the concrete change in acidity, sweetness, aroma or texture. preparation_type is home_mixed, serving_adaptation
or alcohol_free_interpretation. recipe.alcohol_status must agree with its ingredients. Non-alcoholic
recipes cannot use rum, wine, alcoholic bitters or other alcohol-containing ingredients. Label a zero-proof recipe simply Alcohol-free version once; explain what ingredients it uses. Do not claim bitters or fermented
products are alcohol-free without evidence. No invented ABV, health benefits, current prices or local
legal drinking ages. strength_context is optional: use it only for material alcohol-strength information the reader needs. Do not encourage excessive intake.
Variations:1-6 id/name/place/difference/how_it_developed/evidence_and_uncertainty, explain transmission,
local ingredients and cultural adaptation only when sourced. serving_context:glassware/pairing_and_customs/
nullable alcohol_free_option/practical_notes. Give1-5 troubleshooting,1-3 knowledge_checks with answers,
2-5 takeaways and1-6 related_drinks. Factual blocks resolve source_ids. Use credible culinary associations,
producers for methods, museums/archives for history and scientific sources for mechanisms. No invented
sources, quotations or claims of independent verification. Source lists only at the bottom. Root fields
agree with the lesson. Photos never replace complete explanations; every section needs connected prose.

READER-READY EDITORIAL RULES (apply throughout this response, including root compatibility fields):
Write a finished beginner article that teaches the drink. Lead with what happens, how it tastes, how to
make it and why the method works. Every sentence must add a concrete fact, useful explanation or action.
Do not fill required prose with disclaimers, generic variability or statements about missing evidence.
Keep internal source/structure verification separate from article prose; never claim verification you did not perform.
origin.evidence_and_uncertainty, variations[].evidence_and_uncertainty, science[].limits and
identity.strength_context are OPTIONAL and nullable. Omit them or return null when they add nothing useful.
When the origin is genuinely disputed and this changes the story, add one short specific note in origin;
do not repeat it in the timeline, earlier method, variations, recipe or takeaways. Do not manufacture a
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
