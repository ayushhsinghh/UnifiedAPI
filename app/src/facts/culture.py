"""Place-led, people-led cultural learning with documentary section photography."""
from copy import deepcopy
from .schemas import _object, _items, _strings, _TEXT, _SOURCE_IDS_SCHEMA
from .physics import PHYSICS_RESPONSE_SCHEMA, _shape, _unique_ids
from .drinks import simple_id

def sourced(fields):return _object({**fields,'source_ids':_SOURCE_IDS_SCHEMA})
NULL_TEXT={**_TEXT,'nullable':True}
MARKERS=('clothing','architecture','food','music','celebration')
SECTIONS=('overview','origins','daily_life','worldview','markers','india','explanation','spread','living')
CULTURE_LESSON_SCHEMA=_object({
 'content_version':{'type':'INTEGER'},
 'identity':sourced({'name':_TEXT,'local_names':_strings(),'peoples':_strings(),'heartland':_TEXT,'languages':_strings(),'scope':_TEXT}),
 'hook':_TEXT,
 'opening':sourced({'heading':_TEXT,'scene':_TEXT,'question':_TEXT}),
 'origins':sourced({'heartland':_TEXT,'climate_and_terrain':_TEXT,'adaptation':_TEXT,'historical_origins':_TEXT,'time_context':_TEXT}),
 'milestones':_items(sourced({'id':_TEXT,'period':_TEXT,'event':_TEXT,'significance':_TEXT})),
 'daily_life':sourced({'introduction':_TEXT,'comparisons':_items(sourced({'id':_TEXT,'domain':_TEXT,'historical_context':_TEXT,'then':_TEXT,'now':_TEXT,'why_changed':_TEXT,'who_and_where':_TEXT}))}),
 'worldview':sourced({'introduction':_TEXT,'concepts':_items(sourced({'id':_TEXT,'term':_TEXT,'local_term':NULL_TEXT,'meaning':_TEXT,'everyday_example':_TEXT,'scope':_TEXT})),
   'etiquette':_items(sourced({'id':_TEXT,'situation':_TEXT,'practice':_TEXT,'reason':_TEXT,'context':_TEXT}))}),
 'markers':_items(sourced({'id':_TEXT,'kind':{'type':'STRING','enum':list(MARKERS)},'name':_TEXT,'place_or_community':_TEXT,'description':_TEXT,'meaning':_TEXT,'experience':_TEXT,'today':_TEXT})),
 'india_connections':sourced({'introduction':_TEXT,'connections':_items(sourced({'id':_TEXT,'title':_TEXT,'relationship':{'type':'STRING','enum':['documented_contact','shared_roots','comparison']},'explanation':_TEXT,'indian_example':_TEXT,'distinction':_TEXT}))}),
 'why_custom':sourced({'title':_TEXT,'custom':_TEXT,'explanation':_TEXT,'drivers':_items(sourced({'id':_TEXT,'factor':_TEXT,'effect':_TEXT})),
   'what_it_explains':_TEXT,'limits':NULL_TEXT,'infographic_prompt':_TEXT}),
 'spread':sourced({'introduction':_TEXT,'pathways':_items(sourced({'id':_TEXT,'destination':_TEXT,'period':_TEXT,'route':_TEXT,'what_changed':_TEXT,'what_continues':_TEXT})),
   'influences':_items(sourced({'id':_TEXT,'name':_TEXT,'example':_TEXT,'connection':_TEXT}))}),
 'living_culture':sourced({'introduction':_TEXT,'variations':_items(sourced({'id':_TEXT,'community_or_region':_TEXT,'difference':_TEXT,'explanation':_TEXT}))}),
 'key_terms':_items(sourced({'term':_TEXT,'meaning':_TEXT})),
 'knowledge_checks':_items(_object({'question':_TEXT,'answer':_TEXT,'explanation':_TEXT})),
 'takeaways':_strings(),'related_topics':_strings(),
 'photos':_items(_object({'id':_TEXT,'section_id':{'type':'STRING','enum':list(SECTIONS)},'entry_id':NULL_TEXT,
   'kind':{'type':'STRING','enum':['named_place','person','historical_object','attire','architecture','food','music','festival','map','everyday','process']},
   'subject':_TEXT,'queries':_strings()}))})
CULTURE_LESSON_SCHEMA['properties']['photos'].update(minItems=12,maxItems=30)
CULTURE_RESPONSE_SCHEMA=deepcopy(PHYSICS_RESPONSE_SCHEMA)
del CULTURE_RESPONSE_SCHEMA['properties']['physics_lesson']
CULTURE_RESPONSE_SCHEMA['required'].remove('physics_lesson')
CULTURE_RESPONSE_SCHEMA['properties'].update(article_type={'type':'STRING','enum':['culture_lesson']},culture_lesson=CULTURE_LESSON_SCHEMA)
CULTURE_RESPONSE_SCHEMA['required'].append('culture_lesson')
CULTURE_RESPONSE_SCHEMA['properties']['visual_suggestions']=_object({'cover':_TEXT,'overview':_TEXT,'how_it_works':_TEXT})

def culture_refs(l):
 return {'markers':l['markers'],'daily_life':l['daily_life']['comparisons'],'worldview':l['worldview']['concepts']+l['worldview']['etiquette'],
  'india':l['india_connections']['connections'],'explanation':l['why_custom']['drivers'],
  'spread':l['spread']['pathways']+l['spread']['influences'],'living':l['living_culture']['variations']}

def culture_photo_entries(f):return [dict(p,key=f'culture_photo_{i}') for i,p in enumerate(f.get('culture_lesson',{}).get('photos',[])[:30])]

def ensure_culture_photo_plan(f):
 """Complete section coverage and marker bindings while preserving existing model queries."""
 l=f.get('culture_lesson')
 if f.get('article_type')!='culture_lesson' or not isinstance(l,dict):return False
 try:
  name=l['identity']['name'];existing=l.get('photos') or []
  if not isinstance(existing,list) or any(not isinstance(p,dict) for p in existing) or len(existing)>30:return False
  defaults=[]
  def add(section,entry,kind,subject,alternate):
   if not isinstance(subject,str) or not subject.strip():return
   queries=list(dict.fromkeys(q.strip()[:160] for q in (subject,alternate) if isinstance(q,str) and q.strip()))
   if len(queries)<2:queries.append(subject[:140]+' culture')
   defaults.append(dict(id='fallback_'+str(len(defaults)),section_id=section,entry_id=entry,kind=kind,subject=subject[:160],queries=queries))
  for section,kind,subject,alt in [('overview','everyday',name,name+' everyday life'),('origins','named_place',l['identity']['heartland'],name+' history'),
    ('daily_life','everyday',name+' daily life',name+' community'),('worldview','everyday',name+' customs',name+' social life'),
    ('explanation','process',l['why_custom']['custom'],name+' '+l['why_custom']['custom']),('spread','everyday',name+' diaspora',name+' cultural heritage'),
    ('living','everyday',name+' contemporary culture',name+' traditions today')]:add(section,None,kind,subject,alt)
  for m in l['markers']:
   kind={'clothing':'attire','celebration':'festival'}.get(m['kind'],m['kind'])
   add('markers',m['id'],kind,m['name'],m['name']+' '+name)
  for c in l['india_connections']['connections']:add('india',c['id'],'historical_object',c['title'],name+' India cultural exchange')
  key=lambda p:(p.get('section_id'),p.get('entry_id'))
  merged=list(existing);covered={key(p) for p in merged};ids={p.get('id') for p in merged}
  for p in defaults:
   if key(p) in covered:continue
   while p['id'] in ids:p['id']+='x'
   merged.append(p);covered.add(key(p));ids.add(p['id'])
  if len(merged)>30:
   needed={key(p) for p in defaults};keep=[]
   for index,p in enumerate(merged):
    if key(p) in needed:keep.append(index);needed.remove(key(p))
   chosen=set(keep)
   for index in range(len(merged)):
    if len(chosen)>=30:break
    chosen.add(index)
   merged=[p for i,p in enumerate(merged) if i in chosen]
  if merged==existing:return False
  l['photos']=merged;f.setdefault('culture_media',{}).update(photo_plan_source='repaired' if existing else 'fallback',photo_plan_version=1)
  return True
 except (KeyError,TypeError,ValueError):return False

def validate_culture_content(f):
 try:
  if not _shape(f,CULTURE_RESPONSE_SCHEMA):return False
  l=f['culture_lesson'];sources=f['sources'];ids={s['id'] for s in sources}
  if l['content_version']!=1 or not sources or not _unique_ids(sources):return False
  def check(v):
   if isinstance(v,dict):return ('source_ids' not in v or bool(v['source_ids']) and set(v['source_ids'])<=ids) and all(check(x) for x in v.values())
   if isinstance(v,list):return all(check(x) for x in v)
   return not isinstance(v,str) or bool(v.strip())
  if not check(l):return False
  refs=culture_refs(l)
  groups=[(l['milestones'],0,6),(l['markers'],5,10),(l['daily_life']['comparisons'],3,5),(l['worldview']['concepts'],1,4),
   (l['worldview']['etiquette'],1,4),(l['india_connections']['connections'],0,4),(l['why_custom']['drivers'],2,5),
   (l['spread']['pathways'],1,5),(l['spread']['influences'],1,5),(l['living_culture']['variations'],1,4),(l['photos'],12,30)]
  if any(not low<=len(rows)<=high or not _unique_ids(rows) or any(not simple_id(p['id']) for p in rows) for rows,low,high in groups):return False
  if any(len({p['id'] for p in rows})!=len(rows) for rows in refs.values()):return False
  if not set(MARKERS)<={p['kind'] for p in l['markers']}:return False
  if not 1<=len(l['identity']['peoples'])<=6 or not 1<=len(l['identity']['languages'])<=8 or len(l['identity']['local_names'])>5:return False
  if len(l['key_terms'])>6 or not 1<=len(l['knowledge_checks'])<=3 or not 3<=len(l['takeaways'])<=6 or not 1<=len(l['related_topics'])<=6:return False
  sections=set(SECTIONS)-({'india'} if not l['india_connections']['connections'] else set())
  if not sections<={p['section_id'] for p in l['photos']}:return False
  if not {p['id'] for p in l['markers']}<={p['entry_id'] for p in l['photos'] if p['section_id']=='markers'}:return False
  for p in l['photos']:
   if not 2<=len(p['queries'])<=3 or len({q.casefold() for q in p['queries']})!=len(p['queries']) or any(len(q)>160 for q in p['queries']):return False
   if p['entry_id'] is not None and p['entry_id'] not in {r['id'] for r in refs.get(p['section_id'],[])}:return False
  return validate_culture_images(f)
 except (KeyError,ValueError,TypeError,OverflowError):return False

def validate_culture_images(f):
 try:
  v=f['visual_suggestions'];details=f['image_details']
  return set(v)=={'cover','overview','how_it_works'} and all(isinstance(p,str) and p.strip() for p in v.values()) and len(details)==2 and {d['slot'] for d in details}=={'overview','how_it_works'} and all(d['placement']==('overview' if d['slot']=='overview' else 'explanation') and all(isinstance(d.get(k),str) and d[k].strip() for k in ('alt','caption','learning_purpose')) for d in details)
 except (KeyError,ValueError,TypeError):return False

def prepare_culture_media(f):
 f['visual_suggestions']['how_it_works']=f['culture_lesson']['why_custom']['infographic_prompt']
 f['images']={};f['image_credits']={}
 f['culture_media']={'version':1,'generated_limit':3,'generated_slots':['cover','overview','how_it_works'],'photo_timeout_seconds':720,
  'photo_plan_version':1,'photo_plan_source':f.get('culture_media',{}).get('photo_plan_source','model')}
 f['culture_validation']={'structure_checked':True,'source_verification':'not_performed','historical_review':'not_performed'}

CULTURE_IMAGE_INSTRUCTIONS='''CULTURE IMAGE PLAN: exactly three AI illustrations: cover, overview, how_it_works.
Cover: coherent specific cultural setting, mobile-safe subject centre-right, quiet title area left.
Overview: a distinct conceptual summary, also used on discovery cards. Never present generated scenes as
historical documentary evidence. how_it_works copies why_custom.infographic_prompt: a clear explanatory
infographic for ONE sociological, ecological or historical mechanism. Short labels, causal relationships,
actual factors from the lesson, readable layout; no fake historic maps, statistics or invented symbols.
image_details has overview/placement overview and how_it_works/placement explanation with descriptive
alt, caption and learning_purpose, clearly identified as illustrations. No additional AI images.
Require 12-30 Wikimedia photo requests, 2-3 distinct concise queries each. Every visible section has
at least one request and EACH marker has an entry_id-bound request. Use exact local names, museum
object names, attire, instruments, verified places, heritage sites, festivals and maps. Prioritize
community museums and documented artifacts. Each query has a specific subject and a simpler alternative.
No generic stock portrait stands for a named person or community; no modern scene claims historical
provenance. Contemporary life photos must state their actual context. Historical maps need identifiable
place and period. Unsplash/Pixabay form a separate complementary end carousel, using metadata AI ranking.
'''

def build_culture_prompt(blocklist):
 return f'''Create ONE culture_lesson, category culture, schema_version 2.0, content_version 1.
Avoid recent topics: {blocklist}. Teach ONE named culture anywhere in the world in an accessible
8-12 minute reading journey. A culture can cross national borders. Do not write a country profile,
world-cultures list or national stereotype. Begin with a concrete cultural scene and one compelling
question, then explain it through connected complete paragraphs. Easy-to-medium topics and simple words.
identity identifies peoples, local_names, heartland, languages and scope. hook is a concise subtitle.
opening has heading/scene/question/source_ids; do not repeat its scene in an overview introduction.
origins connects heartland, climate_and_terrain, adaptation, historical_origins and time_context.
Explain ecological influences without claiming terrain determines beliefs or human ability. milestones
has 0-6 meaningful period/event/significance entries, never made-up exact dates or decorative chronology.
daily_life has introduction and 3-5 comparisons: domain, historical_context, then, now, why_changed,
who_and_where. Cover home/work, social organisation, family/community and customs. Historical periods
and communities must be named; do not imply an unchanged uniform past or a uniformly Westernised present.
worldview has introduction, 1-4 concepts with term/local_term/meaning/everyday_example/scope and 1-4
etiquette entries situation/practice/reason/context. Explain distinctive ideas without assigning them
to every person; never claim a popular marketing term is an ancient universal philosophy.
markers has 5-10 detailed examples covering clothing, architecture, food, music, celebration at least
once each. Each gives name/place_or_community/description/meaning/experience/today; include observable
features, material or preparation, context and contemporary changes. Never write a caption as the whole
explanation. Photos may be modest near markers, larger for architecture or festivals.
india_connections has introduction and 0-4 substantial connections with title/relationship/explanation/
indian_example/distinction. relationship is documented_contact, shared_roots or comparison. A resemblance
is not proof of historical contact or common ancestry. No invented linguistic roots. If no documented
contact exists, use a clearly labelled comparison where useful; an empty list is valid with a complete
introduction explaining what a reader can compare. No forced India connection or supremacy claims.
why_custom explains ONE named signature custom or structure, with title/custom/explanation, 2-5 drivers
factor/effect, what_it_explains, nullable limits and detailed infographic_prompt. Distinguish documented
history from interpretation. Avoid unsupported single-cause origin stories. Describe actual mechanisms,
not superficial 1-2-3 numbered dots. Omit generic disclaimers; include limits only if they alter meaning.
spread has introduction, 1-5 pathways destination/period/route/what_changed/what_continues and 1-5
influences name/example/connection. Explain migration, trade, religion, art or diaspora as supported,
including specific subcultures and adaptation, without claiming unrelated trends were borrowed.
living_culture has introduction and 1-4 variations community_or_region/difference/explanation. Cultures
remain living and internally diverse; include local perspectives with sources, not invented quotations.
0-6 key_terms, 1-3 knowledge_checks question/answer/explanation, 3-6 takeaways, 1-6 related_topics.
All repeated records have unique simple lowercase slug IDs, max48 characters. All factual blocks use
resolving source_ids. Use museums, community cultural institutions, primary historical records, scholarly
anthropology and heritage agencies. Sources only in bottom references. Do not claim source retrieval or
independent verification. Root compatibility fields agree with the lesson. No fabricated quotations,
URLs or exact figures. Photos have id/section_id/entry_id/kind/subject/queries; section_id is overview,
origins,daily_life,worldview,markers,india,explanation,spread,living. entry_id is null or references an
actual record in that section (milestones are not photo references). Use 2-3 distinct queries per photo.
'''
