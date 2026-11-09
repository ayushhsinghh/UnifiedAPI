"""Nonpartisan, institution-led Indian Politics lessons for curious beginners."""
from copy import deepcopy
from datetime import date
from .schemas import _object,_items,_strings,_TEXT
from .physics import PHYSICS_RESPONSE_SCHEMA,_shape,_unique_ids
from .culture import sourced,NULL_TEXT,validate_culture_images
from .drinks import simple_id
SECTIONS=('overview','context','actors','process','rules','example','accountability','tradeoffs','changes','citizen','confusions')
KINDS=('institution','document','person','historical_object','named_place','election_equipment','public_process','modern_context')
BASIS_TYPES=('legal_rule','procedure','convention','observed_practice')
POLITICS_LESSON_SCHEMA=_object({
 'content_version':{'type':'INTEGER'},
 'identity':sourced({'name':_TEXT,'topic_type':{'type':'STRING','enum':['elections','government_formation','parliament','federal_relations','local_government','representation','public_decisions']},
  'level':{'type':'STRING','enum':['union','state','local','cross_level']},'institutions':_strings(),'scope':_TEXT,'period':_TEXT,'as_of':NULL_TEXT}),
 'hook':_TEXT,'opening':sourced({'heading':_TEXT,'situation':_TEXT,'question':_TEXT,'kind':{'type':'STRING','enum':['illustrative','documented']}}),
 'core_idea':sourced({'explanation':_TEXT,'why_it_matters':_TEXT}),
 'context':sourced({'setting':_TEXT,'when_it_applies':_TEXT,'what_it_does_not_cover':_TEXT}),
 'actors':_items(sourced({'id':_TEXT,'name':_TEXT,'kind':{'type':'STRING','enum':['institution','office','political_group','public']},'role':_TEXT,'authority':_TEXT,'limits':_TEXT})),
 'rules':_items(sourced({'id':_TEXT,'title':_TEXT,'basis_type':{'type':'STRING','enum':list(BASIS_TYPES)},'reference':_TEXT,'formal_position':_TEXT,'practice':_TEXT,'scope_or_variation':_TEXT})),
 'process':sourced({'starts_when':_TEXT,'ends_with':_TEXT,'steps':_items(sourced({'id':_TEXT,'title':_TEXT,'actor_ids':_strings(),'rule_ids':_strings(),'action':_TEXT,'result':_TEXT,'conditions':_TEXT}))}),
 'worked_example':sourced({'title':_TEXT,'kind':{'type':'STRING','enum':['illustrative','dated_real']},'date':NULL_TEXT,'setting':_TEXT,
  'steps':_items(sourced({'process_step_id':_TEXT,'explanation':_TEXT})),'outcome':_TEXT,'what_it_shows':_TEXT}),
 'accountability':_items(sourced({'id':_TEXT,'title':_TEXT,'actor_ids':_strings(),'check':_TEXT,'what_can_change':_TEXT,'limits':_TEXT})),
 'tradeoffs':_items(sourced({'id':_TEXT,'title':_TEXT,'benefit':_TEXT,'cost':_TEXT,'when_it_matters':_TEXT})),
 'changes':_items(sourced({'id':_TEXT,'date':_TEXT,'title':_TEXT,'change':_TEXT,'why_it_matters':_TEXT})),
 'citizen_view':sourced({'why_it_matters':_TEXT,'channels':_items(sourced({'id':_TEXT,'name':_TEXT,'what_it_does':_TEXT,'scope':_TEXT}))}),
 'confusions':_items(sourced({'id':_TEXT,'belief':_TEXT,'correction':_TEXT,'explanation':_TEXT})),
 'key_terms':_items(sourced({'term':_TEXT,'meaning':_TEXT})),
 'knowledge_checks':_items(_object({'question':_TEXT,'answer':_TEXT,'explanation':_TEXT})),
 'takeaways':_strings(),'related_topics':_strings(),
 'diagram_prompt':_TEXT,
 'photos':_items(_object({'id':_TEXT,'section_id':{'type':'STRING','enum':list(SECTIONS)},'entry_id':NULL_TEXT,
  'kind':{'type':'STRING','enum':list(KINDS)},'subject':_TEXT,'queries':_strings()}))})
POLITICS_LESSON_SCHEMA['properties']['photos'].update(minItems=12,maxItems=30)
POLITICS_RESPONSE_SCHEMA=deepcopy(PHYSICS_RESPONSE_SCHEMA)
del POLITICS_RESPONSE_SCHEMA['properties']['physics_lesson'];POLITICS_RESPONSE_SCHEMA['required'].remove('physics_lesson')
POLITICS_RESPONSE_SCHEMA['properties'].update(article_type={'type':'STRING','enum':['indian_politics_lesson']},indian_politics_lesson=POLITICS_LESSON_SCHEMA)
POLITICS_RESPONSE_SCHEMA['required'].append('indian_politics_lesson')
POLITICS_RESPONSE_SCHEMA['properties']['category']={'type':'STRING','enum':['indian_politics']}
POLITICS_RESPONSE_SCHEMA['properties']['visual_suggestions']=_object({'cover':_TEXT,'overview':_TEXT,'how_it_works':_TEXT})

def valid_politics_date(value):
 try:return isinstance(value,str) and len(value)==10 and date.fromisoformat(value).isoformat()==value and date.fromisoformat(value)<=date.today()
 except (ValueError,TypeError):return False

def politics_refs(l):return {'actors':l['actors'],'rules':l['rules'],'process':l['process']['steps'],'accountability':l['accountability'],
 'tradeoffs':l['tradeoffs'],'changes':l['changes'],'citizen':l['citizen_view']['channels'],'confusions':l['confusions']}
def politics_photo_entries(f):return [dict(p,key=f'indian_politics_photo_{i}') for i,p in enumerate(f.get('indian_politics_lesson',{}).get('photos',[])[:30])]

def ensure_politics_photo_plan(f):
 l=f.get('indian_politics_lesson')
 if f.get('article_type')!='indian_politics_lesson' or not isinstance(l,dict):return False
 try:
  existing=l.get('photos') or []
  if not isinstance(existing,list) or len(existing)>30 or any(not isinstance(p,dict) for p in existing):return False
  name=l['identity']['name'];institution=l['identity']['institutions'][0];defaults=[]
  def add(section,entry,kind,subject,alternate):
   queries=list(dict.fromkeys(q.strip()[:160] for q in (subject,alternate) if isinstance(q,str) and q.strip()))
   if len(queries)<2:queries.append((subject+' India')[:160])
   defaults.append(dict(id='fallback_'+str(len(defaults)),section_id=section,entry_id=entry,kind=kind,subject=subject[:160],queries=queries))
  for section,kind,subject,alt in [('overview','institution',institution,institution+' India'),('context','institution',institution+' building',institution+' India'),
   ('rules','document',institution+' rules of procedure',institution+' procedure'),('example','public_process',institution+' proceedings',name+' India'),
   ('accountability','institution',institution+' proceedings',institution+' questions'),('tradeoffs','public_process',institution+' deliberation',institution+' debate'),
   ('citizen','modern_context',institution+' India',institution+' building India'),('confusions','institution',institution,institution+' procedure')]:add(section,None,kind,subject,alt)
  for p in l['actors']:add('actors',p['id'],'institution',institution+' '+p['name'],institution+' building India')
  for p in l['process']['steps']:add('process',p['id'],'public_process',institution+' '+p['title'],institution+' proceedings')
  for p in l['changes']:add('changes',p['id'],'document',p['title']+' India',institution+' history')
  key=lambda p:(p.get('section_id'),p.get('entry_id'))
  merged=list(existing);covered={key(p) for p in merged};ids={p.get('id') for p in merged}
  for p in defaults:
   if key(p) in covered:continue
   while p['id'] in ids:p['id']+='x'
   merged.append(p);covered.add(key(p));ids.add(p['id'])
  if len(merged)>30:
   required={key(p) for p in defaults};keep=set()
   for i,p in enumerate(merged):
    if key(p) in required:keep.add(i);required.remove(key(p))
   for i in range(len(merged)):
    if len(keep)>=30:break
    keep.add(i)
   merged=[p for i,p in enumerate(merged) if i in keep]
  if merged==existing:return False
  l['photos']=merged;f.setdefault('indian_politics_media',{}).update(photo_plan_source='repaired' if existing else 'fallback',photo_plan_version=1)
  return True
 except (KeyError,TypeError,ValueError,IndexError):return False

def validate_politics_content(f):
 try:
  if not _shape(f,POLITICS_RESPONSE_SCHEMA):return False
  l=f['indian_politics_lesson'];sources=f['sources'];source_ids={s['id'] for s in sources}
  if l['content_version']!=1 or not sources or not _unique_ids(sources):return False
  if l['identity']['as_of'] is not None and not valid_politics_date(l['identity']['as_of']):return False
  def check(v):
   if isinstance(v,dict):return ('source_ids' not in v or bool(v['source_ids']) and set(v['source_ids'])<=source_ids) and all(check(x) for x in v.values())
   if isinstance(v,list):return all(check(x) for x in v)
   return not isinstance(v,str) or bool(v.strip())
  if not check(l):return False
  groups=[(l['actors'],2,6),(l['rules'],1,5),(l['process']['steps'],3,6),(l['accountability'],1,5),(l['tradeoffs'],1,3),
   (l['changes'],0,4),(l['citizen_view']['channels'],1,4),(l['confusions'],2,4),(l['photos'],12,30)]
  if any(not low<=len(rows)<=high or not _unique_ids(rows) or any(not simple_id(p['id']) for p in rows) for rows,low,high in groups):return False
  actors={p['id'] for p in l['actors']};rules={p['id'] for p in l['rules']};steps={p['id'] for p in l['process']['steps']}
  if any(not p['actor_ids'] or not set(p['actor_ids'])<=actors or not p['rule_ids'] or not set(p['rule_ids'])<=rules for p in l['process']['steps']):return False
  if any(not p['actor_ids'] or not set(p['actor_ids'])<=actors for p in l['accountability']):return False
  example=l['worked_example']
  if not 2<=len(example['steps'])<=6 or any(p['process_step_id'] not in steps for p in example['steps']):return False
  if example['kind']=='dated_real' and (not valid_politics_date(example['date']) or not valid_politics_date(l['identity']['as_of']) or example['date']>l['identity']['as_of']):return False
  if example['kind']=='illustrative' and example['date'] is not None:return False
  if any(not valid_politics_date(p['date']) for p in l['changes']):return False
  if [p['date'] for p in l['changes']]!=sorted(p['date'] for p in l['changes']):return False
  if l['identity']['as_of'] and any(p['date']>l['identity']['as_of'] for p in l['changes']):return False
  if not 1<=len(l['identity']['institutions'])<=6 or len(l['key_terms'])>6 or not 1<=len(l['knowledge_checks'])<=3 or not 3<=len(l['takeaways'])<=6 or not 1<=len(l['related_topics'])<=6:return False
  active=set(SECTIONS)-({'changes'} if not l['changes'] else set())
  if not active<={p['section_id'] for p in l['photos']}:return False
  refs=politics_refs(l)
  for section,entries in [('actors',l['actors']),('process',l['process']['steps'])]:
   if not {p['id'] for p in entries}<={p['entry_id'] for p in l['photos'] if p['section_id']==section}:return False
  for p in l['photos']:
   if not 2<=len(p['queries'])<=3 or len({q.casefold() for q in p['queries']})!=len(p['queries']) or any(len(q)>160 for q in p['queries']):return False
   if p['entry_id'] is not None and p['entry_id'] not in {r['id'] for r in refs.get(p['section_id'],[])}:return False
   if p['section_id']=='changes' and not l['changes']:return False
  return validate_culture_images(f)
 except (KeyError,ValueError,TypeError,OverflowError):return False

def prepare_politics_media(f):
 f['visual_suggestions']['how_it_works']=f['indian_politics_lesson']['diagram_prompt']
 f['images']={};f['image_credits']={}
 f['indian_politics_media']={'version':1,'generated_limit':3,'generated_slots':['cover','overview','how_it_works'],'photo_timeout_seconds':720,
  'photo_plan_version':1,'photo_plan_source':f.get('indian_politics_media',{}).get('photo_plan_source','model')}
 f['indian_politics_validation']={'structure_checked':True,'references_checked':True,'date_bounds_checked':True,
  'source_verification':'not_performed','legal_currency_check':'not_performed','example_verification':'not_performed'}

POLITICS_IMAGE_INSTRUCTIONS='''INDIAN POLITICS IMAGE PLAN: exactly THREE AI illustrations: cover,
overview/card and how_it_works (copies diagram_prompt). Cover is a coherent institutional scene, subject
centre-right/mobile safe, quiet left title area. Overview is a distinct conceptual summary. Diagram
shows actual roles, actions and outcomes with concise labels and a legend. No decorative numbered dots.
Do not generate portraits of named politicians, party symbols, fake ballot papers, seals, signatures,
official forms or invented election results. Generated scenes are illustrations, never event evidence.
image_details: overview/placement overview and how_it_works/placement explanation, alt/caption/learning_purpose.
Require 12-30 Commons photo requests covering active sections; EVERY actor and process step has a bound
request. 2-3 distinct concise queries each, exact institution/place/object first then simpler verified
alternative. A building can illustrate institutional setting, not prove a specific vote or meeting.
Named politicians require actual identified portraits from Commons, never generic stock or AI faces.
Preserve actual caption, place, date and original source context; a photo does not prove a political
claim. Separate Unsplash/Pixabay end-gallery uses modern_context institutional/place requests only,
not named politician identity, party events or evidence of alleged behaviour. Keep discreet credits.
'''

def build_politics_prompt(blocklist):
 return f'''Create ONE indian_politics_lesson, category indian_politics, schema_version 2.0, content_version 1.
Avoid recent topics:{blocklist}. Teach ONE easy-to-medium Indian political process, institution or
representation concept to a curious beginner in 8-12 minutes. Be nonpartisan and concrete. Explain power,
authority, responsibility and practical consequences. Not a party ranking, campaign pitch, current-news
roundup or duplicate Constitution/Indian Laws lesson. Prefer stable institutional concepts to breaking
results or current officeholders. Never advise which party/candidate to support or target demographic groups.
identity:name/topic_type elections,government_formation,parliament,federal_relations,local_government,
representation,public_decisions/level union,state,local,cross_level/institutions/scope/period/as_of.
as_of is a valid nonfuture YYYY-MM-DD only when describing a specific dated context; otherwise null.
It describes the lesson context, not a claim that current rules were independently checked. Explain
Union/State/local and Lok Sabha/Rajya Sabha distinctions correctly; do not generalise one chamber's
procedure to every legislature or a Union rule to every state. Scope rules to the actual institution.
hook:short cover subtitle. opening:heading/situation/question/kind illustrative or documented/source_ids.
Label invented teaching situations illustrative; never fabricate politician dialogue, motives or events.
core_idea:explanation/why_it_matters. Answer the question simply without repeating the opening situation.
context:setting/when_it_applies/what_it_does_not_cover. Explain background before detail.
actors: 2-6:id/name/kind institution,office,political_group,public/role/authority/limits/source_ids. Prefer
offices/institutions to unnecessary current personal names. Include affected people and checks on power.
rules: 1-5:id/title/basis_type legal_rule,procedure,convention,observed_practice/reference/formal_position/
practice/scope_or_variation/source_ids. Distinguish legal authority, parliamentary procedure, convention
and observed political behaviour. Do not turn a convention into a law or anecdote into a universal rule.
Reference exact official provisions/rules when known without fabricated numbers; explain their meaning.
process:starts_when/ends_with/3-6steps id/title/actor_ids/rule_ids/action/result/conditions/source_ids.
Resolve all IDs. Describe an understandable ordered path with the conditions that change an outcome,
not a generic one-to-four line. One process can be illustrative; do not imply every case follows it.
worked_example:title/kind illustrative or dated_real/date/setting/2-6steps process_step_id/explanation/
outcome/what_it_shows/source_ids. Illustrative examples have date:null and neutral unnamed actors.
Dated real cases need valid nonfuture ISO date, identity.as_of at or after case date and reliable sources.
Avoid invented seat counts, vote results or political claims. If using arithmetic, state the actual
relevant denominator (membership, present-and-voting, vacancies/abstentions where applicable) and explain
exceptions; do not equate the largest party with an automatic right to form government.
accountability: 1-5:id/title/actor_ids/check/what_can_change/limits/source_ids. Explain real checks and their
scope, not just a list of institutions. tradeoffs: 1-3:id/title/benefit/cost/when_it_matters/source_ids.
Explain procedural tradeoffs through consequences and evidence; no false balance or fabricated opinions.
changes: 0-4:id/date/title/change/why_it_matters/source_ids. Only sourced meaningful changes, exact known
ISO dates, sorted ascending and no later than as_of when present. If exact dates are unknown, explain
background in context and omit the dated change. No forced chronology or claimed latest developments.
citizen_view:why_it_matters and 1-4 channels id/name/what_it_does/scope/source_ids. Teach universal civic
understanding, sources of information and representative roles, not personalised electoral persuasion.
confusions: 2-4:id/belief/correction/explanation/source_ids, concrete mixups rather than generic disclaimers.
0-6 key_terms, 1-3 knowledge_checks question/answer/explanation,3-6 takeaways, 1-6 related_topics. diagram_prompt
explains the actual process roles, decision and result in one educational figure, concise meaningful labels.
Every factual block uses resolving source_ids. Prefer official ECI, Parliament/Sansad, state legislature,
local election authority, government and court records for rules and cases; label interpretations and
reported practice. Never invent quotes, sources, URLs, provision numbers, corruption claims or results.
Keep clear essential qualifications; avoid repeated 'may vary'/'not guaranteed'/'not legal advice' filler.
Do not claim live retrieval, independent verification, current officeholders or legal-currency checks.
Sources only at bottom. Root compatibility fields agree. All repeatable rows have unique simple lower
case slug IDs max48. Photos:id/section_id overview,context,actors,process,rules,example,accountability,
tradeoffs,changes,citizen,confusions/entry_id null or matching section record/kind/subject/queries.
kind:institution,document,person,historical_object,named_place,election_equipment,public_process,modern_context.
Omit changes photos if changes is empty. Use modern_context only for contextual places, not named people.
'''
