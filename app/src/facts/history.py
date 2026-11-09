"""Chronology-led History lessons with explicit contemporary/modern evidence context."""
from copy import deepcopy
from datetime import date
from .schemas import _object,_items,_strings,_TEXT
from .physics import PHYSICS_RESPONSE_SCHEMA,_shape,_unique_ids
from .culture import sourced,NULL_TEXT,validate_culture_images
from .drinks import simple_id
YEAR={'type':'INTEGER'}
def period(fields):return sourced({'date_label':_TEXT,'start_year':YEAR,'end_year':YEAR,**fields})
SECTIONS=('overview','setting','causes','chronology','people','evidence','india','mechanism','consequences','legacy')
KINDS=('historical_map','painting','manuscript','artifact','archival_photo','person','named_place','modern_context')
HISTORY_LESSON_SCHEMA=_object({
 'content_version':YEAR,
 'identity':period({'name':_TEXT,'historical_region':_TEXT,'modern_location':_TEXT,'scope':_TEXT,'topic_type':{'type':'STRING','enum':['event','era','movement','transformation']}}),
 'hook':_TEXT,'opening':sourced({'heading':_TEXT,'scene':_TEXT,'question':_TEXT}),
 'setting':sourced({'geography':_TEXT,'political_climate':_TEXT,'everyday_conditions':_TEXT,'locations':_strings()}),
 'causes':_items(sourced({'id':_TEXT,'title':_TEXT,'kind':{'type':'STRING','enum':['structural','trigger']},'explanation':_TEXT,'connection':_TEXT})),
 'figures':_items(sourced({'id':_TEXT,'name':_TEXT,'kind':{'type':'STRING','enum':['person','collective']},'role':_TEXT,'objective':_TEXT,'actions':_TEXT,'impact':_TEXT})),
 'chronology':_items(period({'id':_TEXT,'title':_TEXT,'what_happened':_TEXT,'why_it_matters':_TEXT,'figure_ids':_strings()})),
 'decisions':_items(sourced({'id':_TEXT,'title':_TEXT,'figure_id':_TEXT,'chronology_id':_TEXT,'options':_TEXT,'choice':_TEXT,'consequence':_TEXT})),
 'evidence':sourced({'introduction':_TEXT,'records':_items(sourced({'id':_TEXT,'title':_TEXT,'creator':_TEXT,'created_when':_TEXT,
  'relationship':{'type':'STRING','enum':['contemporary','later_memory','later_depiction']},'account':_TEXT,'what_it_shows':_TEXT,'limits':_TEXT})),
  'modern_understanding':_TEXT,'updates':_items(sourced({'id':_TEXT,'title':_TEXT,'method':{'type':'STRING','enum':['archaeology','declassified_record','scientific_analysis','archival_research','historical_reinterpretation']},'finding':_TEXT,'what_changed':_TEXT,'remaining_question':NULL_TEXT}))}),
 'india':sourced({'introduction':_TEXT,'connections':_items(period({'id':_TEXT,'title':_TEXT,
  'relationship':{'type':'STRING','enum':['contemporary_context','documented_impact','indirect_effect']},'what_happened':_TEXT,'connection':_TEXT,'distinction':_TEXT}))}),
 'mechanism':sourced({'title':_TEXT,'domain':{'type':'STRING','enum':['strategy','logistics','engineering','economics','disease_transmission','social_organisation']},
  'problem':_TEXT,'explanation':_TEXT,'steps':_items(sourced({'id':_TEXT,'factor':_TEXT,'effect':_TEXT})),
  'why_it_mattered':_TEXT,'limits':NULL_TEXT,'diagram_prompt':_TEXT}),
 'outcome':sourced({'immediate_result':_TEXT,'why_distinctive':_TEXT}),
 'consequences':_items(sourced({'id':_TEXT,'title':_TEXT,'domain':{'type':'STRING','enum':['borders','law','culture','economy','society','knowledge']},'place_and_period':_TEXT,'change':_TEXT,'causal_connection':_TEXT})),
 'legacy':_items(sourced({'id':_TEXT,'title':_TEXT,'place':_TEXT,'trace':_TEXT,'relationship':{'type':'STRING','enum':['direct_continuity','indirect_influence','commemoration']},'explanation':_TEXT})),
 'key_terms':_items(sourced({'term':_TEXT,'meaning':_TEXT})),
 'knowledge_checks':_items(_object({'question':_TEXT,'answer':_TEXT,'explanation':_TEXT})),
 'takeaways':_strings(),'related_topics':_strings(),
 'photos':_items(_object({'id':_TEXT,'section_id':{'type':'STRING','enum':list(SECTIONS)},'entry_id':NULL_TEXT,
  'kind':{'type':'STRING','enum':list(KINDS)},'subject':_TEXT,'target_period':_TEXT,'queries':_strings()}))})
HISTORY_LESSON_SCHEMA['properties']['photos'].update(minItems=12,maxItems=30)
HISTORY_RESPONSE_SCHEMA=deepcopy(PHYSICS_RESPONSE_SCHEMA)
del HISTORY_RESPONSE_SCHEMA['properties']['physics_lesson'];HISTORY_RESPONSE_SCHEMA['required'].remove('physics_lesson')
HISTORY_RESPONSE_SCHEMA['properties'].update(article_type={'type':'STRING','enum':['history_lesson']},history_lesson=HISTORY_LESSON_SCHEMA)
HISTORY_RESPONSE_SCHEMA['required'].append('history_lesson')
HISTORY_RESPONSE_SCHEMA['properties']['visual_suggestions']=_object({'cover':_TEXT,'overview':_TEXT,'how_it_works':_TEXT})

def history_refs(l):return {'causes':l['causes'],'chronology':l['chronology'],'people':l['figures']+l['decisions'],
 'evidence':l['evidence']['records']+l['evidence']['updates'],'india':l['india']['connections'],
 'mechanism':l['mechanism']['steps'],'consequences':l['consequences'],'legacy':l['legacy']}
def history_photo_entries(f):return [dict(p,key=f'history_photo_{i}') for i,p in enumerate(f.get('history_lesson',{}).get('photos',[])[:30])]
def valid_period(p):return all(type(p.get(k)) is int and p[k]!=0 and -100000<=p[k]<=date.today().year for k in ('start_year','end_year')) and p['start_year']<=p['end_year']

def ensure_history_photo_plan(f):
 """Repair missing section and chronology bindings without renumbering existing requests."""
 l=f.get('history_lesson')
 if f.get('article_type')!='history_lesson' or not isinstance(l,dict):return False
 try:
  existing=l.get('photos') or []
  if not isinstance(existing,list) or len(existing)>30 or any(not isinstance(p,dict) for p in existing):return False
  name=l['identity']['name'];period=l['identity']['date_label'];defaults=[]
  def add(section,entry,kind,subject,alternate,when=period):
   queries=list(dict.fromkeys(q.strip()[:160] for q in (subject,alternate) if isinstance(q,str) and q.strip()))
   if len(queries)<2:queries.append((subject+' history')[:160])
   defaults.append(dict(id='fallback_'+str(len(defaults)),section_id=section,entry_id=entry,kind=kind,subject=subject[:160],target_period=when,queries=queries))
  for section,kind,subject,alt in [('overview','artifact',name,name+' artifacts'),('setting','historical_map',l['identity']['historical_region']+' '+period+' map',name+' historical map'),
   ('causes','manuscript',name+' historical records',name+' causes'),('people','painting' if l['identity']['end_year']<1839 else 'archival_photo',name+' participants',name+' historical figures'),
   ('evidence','manuscript',name+' primary sources',name+' documents'),('mechanism','artifact',name+' '+l['mechanism']['domain'].replace('_',' '),name+' museum artifacts'),
   ('consequences','historical_map',name+' consequences',name+' aftermath map'),('legacy','modern_context',l['identity']['modern_location'],l['identity']['modern_location']+' heritage site')]:
   add(section,None,kind,subject,alt,'Present-day site context' if kind=='modern_context' else period)
  for p in l['chronology']:add('chronology',p['id'],'manuscript',name+' '+p['title'],name+' '+p['date_label'])
  for p in l['india']['connections']:add('india',p['id'],'historical_map','India '+p['date_label']+' map',p['title']+' India',p['date_label'])
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
  l['photos']=merged;f.setdefault('history_media',{}).update(photo_plan_source='repaired' if existing else 'fallback',photo_plan_version=1)
  return True
 except (KeyError,ValueError,TypeError):return False

def validate_history_content(f):
 try:
  if not _shape(f,HISTORY_RESPONSE_SCHEMA):return False
  l=f['history_lesson'];sources=f['sources'];ids={s['id'] for s in sources}
  if l['content_version']!=1 or not sources or not _unique_ids(sources) or not valid_period(l['identity']):return False
  def check(v):
   if isinstance(v,dict):return ('source_ids' not in v or bool(v['source_ids']) and set(v['source_ids'])<=ids) and all(check(x) for x in v.values())
   if isinstance(v,list):return all(check(x) for x in v)
   return not isinstance(v,str) or bool(v.strip())
  if not check(l):return False
  groups=[(l['causes'],2,5),(l['figures'],2,8),(l['chronology'],4,10),(l['decisions'],1,4),(l['evidence']['records'],1,5),
   (l['evidence']['updates'],0,4),(l['india']['connections'],1,5),(l['mechanism']['steps'],2,5),(l['consequences'],2,6),(l['legacy'],1,4),(l['photos'],12,30)]
  if any(not low<=len(rows)<=high or not _unique_ids(rows) or any(not simple_id(p['id']) for p in rows) for rows,low,high in groups):return False
  refs=history_refs(l)
  if any(not _unique_ids(rows) for rows in refs.values()):return False
  figure_ids={p['id'] for p in l['figures']};timeline_ids={p['id'] for p in l['chronology']}
  events=l['chronology']
  if any(not valid_period(p) or not set(p['figure_ids'])<=figure_ids or not l['identity']['start_year']<=p['start_year']<=p['end_year']<=l['identity']['end_year'] for p in events):return False
  if [p['start_year'] for p in events]!=sorted(p['start_year'] for p in events):return False
  if any(p['figure_id'] not in figure_ids or p['chronology_id'] not in timeline_ids for p in l['decisions']):return False
  if any(not valid_period(p) or p['relationship']=='contemporary_context' and (p['end_year']<l['identity']['start_year'] or p['start_year']>l['identity']['end_year']) for p in l['india']['connections']):return False
  if not any(p['relationship']=='contemporary_context' for p in l['india']['connections']):return False
  if not 1<=len(l['setting']['locations'])<=5 or len(l['key_terms'])>6 or not 1<=len(l['knowledge_checks'])<=3 or not 3<=len(l['takeaways'])<=6 or not 1<=len(l['related_topics'])<=6:return False
  if not set(SECTIONS)<={p['section_id'] for p in l['photos']}:return False
  if not timeline_ids<={p['entry_id'] for p in l['photos'] if p['section_id']=='chronology'}:return False
  for p in l['photos']:
   if not 2<=len(p['queries'])<=3 or len({q.casefold() for q in p['queries']})!=len(p['queries']) or any(len(q)>160 for q in p['queries']):return False
   if p['entry_id'] is not None and p['entry_id'] not in {r['id'] for r in refs.get(p['section_id'],[])}:return False
  return validate_culture_images(f)
 except (KeyError,TypeError,ValueError,OverflowError):return False

def prepare_history_media(f):
 f['visual_suggestions']['how_it_works']=f['history_lesson']['mechanism']['diagram_prompt']
 f['images']={};f['image_credits']={}
 f['history_media']={'version':1,'generated_limit':3,'generated_slots':['cover','overview','how_it_works'],'photo_timeout_seconds':720,
  'photo_plan_version':1,'photo_plan_source':f.get('history_media',{}).get('photo_plan_source','model')}
 f['history_validation']={'structure_checked':True,'year_bounds_and_order_checked':True,'source_verification':'not_performed','historical_review':'not_performed'}

HISTORY_IMAGE_INSTRUCTIONS='''HISTORY IMAGE PLAN: exactly THREE AI illustrations: cover, overview/card,
and how_it_works (copies mechanism.diagram_prompt). Cover preserves known region, period, clothing and
technology, one coherent scene, quiet left title space, mobile-safe subject. Do not fabricate documentary
photographs, portraits of named people, archival records, dates, statistics, historical maps or evidence.
Overview is a distinct conceptual summary. The diagram explains one actual historical mechanism with
short accurate labels, relationships, a legend and explicitly conceptual scale. Do not turn a diagram
into modern weapon-building instructions. image_details includes overview/placement overview and
how_it_works/placement explanation, descriptive alt/caption/learning_purpose labelled as illustrations.
12-30 Wikimedia requests cover EVERY section; EACH chronology entry has its own bound request. Prioritize
historical maps, manuscripts, museum artifacts, paintings and period photographs as appropriate to the
era. Never ask for photographs of events before photography existed. photos: id/section_id/entry_id/
kind/subject/target_period/2-3 distinct concise queries. Exact person, artifact, place, document and period
names first, simpler verified alternatives second. target_period is search intent, NOT proof of provenance.
A later painting is not an eyewitness record; a present-day ruin is not its original condition. Preserve
source captions, object context and discreet credits. Do not infer precise dates from visual appearance.
Historical section images come ONLY from Commons. Any separate Unsplash/Pixabay gallery shows present-day
places and material context only, labelled as such; never imply it records the original events.
'''

def build_history_prompt(blocklist):
 return f'''Create ONE global history_lesson, category history, schema_version 2.0, content_version 1.
Avoid recent topics: {blocklist}. Teach one event, focused era, movement or transformation to curious
beginners with complete simple explanations and an accessible 8-12 minute flow. No world-history list,
advanced specialist debate or assumption the reader knows the actors. Do not make military victory the
only kind of historical outcome. Use documented history, not legend presented as fact.
identity: name/date_label/start_year/end_year/historical_region/modern_location/scope/topic_type.
Signed integer years: negative=BCE, positive=CE, no year zero; no future dates. A circa/range date_label
preserves uncertainty instead of invented precision. Map modern locations separately from period borders.
hook is a brief cover subtitle. opening has heading/scene/question/source_ids, no invented eyewitness
scene, dialogue, motives or exact details. A sourced setting is valid; do not repeat it as an overview.
setting: geography/political_climate/everyday_conditions/1-5 actual locations. causes: 2-5 id/title/kind
structural or trigger/explanation/connection; connect long-term pressures and triggers without claiming
inevitable outcomes. figures: 2-8 id/name/kind person or collective/role/objective/actions/impact.
Include affected people and institutions, not only rulers. Do not invent personal psychology.
chronology: 4-10 id/date_label/start_year/end_year/title/what_happened/why_it_matters/figure_ids/source_ids.
Sort ascending by start_year, dates within identity range, figures resolve. A multi-year entry is valid;
explain sequence inside the prose rather than forcing false exact dates. decisions: 1-4 id/title/
figure_id/chronology_id/options/choice/consequence; reference actual actors and events. Explain what was
known at the time, not only hindsight. Never invent available options or formal meetings.
evidence: introduction; 1-5 records id/title/creator/created_when/relationship contemporary,later_memory,
later_depiction/account/what_it_shows/limits/source_ids; modern_understanding; 0-4 updates id/title/method
archaeology,declassified_record,scientific_analysis,archival_research,historical_reinterpretation/finding/
what_changed/nullable remaining_question/source_ids. Paraphrase records; do not invent quotations. Show
perspective and survival bias concretely. New evidence may refine or corroborate an older account; never
invent an archaeological discovery or declassification just to fill a section. Empty updates is valid.
When no contemporary record survives, explain this in the introduction rather than inventing one.
india: introduction and 1-5 period-dated connections id/title/relationship/what_happened/connection/
distinction/source_ids. Include at least one contemporary_context whose dates OVERLAP the event/era.
Explain actual Indian polities/communities/trade at the same time. Other relationships documented_impact
or indirect_effect need sourced causal links; simultaneity is NOT causation. Name period geography, not
anachronistic national borders. If there is no meaningful impact, use honest contemporary context only.
mechanism: title/domain strategy,logistics,engineering,economics,disease_transmission,social_organisation/
problem/explanation/2-5 steps id/factor/effect/source_ids/why_it_mattered/nullable limits/diagram_prompt.
Explain how interacting factors affected the outcome. Prefer a genuine mechanism to a decorative flowchart;
no invented measurements, casualty counts or single-cause certainty. Null limits unless they change meaning.
outcome: immediate_result and why_distinctive; explain what makes this moment important without claiming
unsupported historical firsts. consequences: 2-6 id/title/domain borders,law,culture,economy,society,knowledge/
place_and_period/change/causal_connection/source_ids. Explain the chain from event to consequence.
legacy: 1-4 id/title/place/trace/relationship direct_continuity,indirect_influence,commemoration/explanation/
source_ids. Separate surviving institutions, later influence and memorialisation. Avoid treating a modern
memorial as an unchanged survival or drawing a straight causal line through unrelated later history.
0-6 key_terms,1-3 knowledge_checks question/answer/explanation,3-6 takeaways,1-6 related_topics.
Unique lowercase simple slug IDs (max48) within each record group; combined people/evidence IDs also unique.
All factual blocks use resolving source_ids. Prefer archives, museums, peer-reviewed historians and
archaeology institutions; distinguish primary records from interpretation. Do not claim retrieval or
independent verification. No fabricated sources, URLs, quotations or politically convenient origin myths.
Sources only at the bottom. Root compatibility text agrees with the structured lesson. Photos section_id
is overview,setting,causes,chronology,people,evidence,india,mechanism,consequences,legacy. entry_id is null
or a record ID in that section; people permits figures/decisions, evidence permits records/updates.
'''
