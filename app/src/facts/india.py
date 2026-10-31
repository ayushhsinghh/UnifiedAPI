"""One India topic explored in depth, with two generated images and documentary photos."""
from copy import deepcopy
import re
from .schemas import _object, _items, _strings, _TEXT
from .physics import PHYSICS_RESPONSE_SCHEMA, _shape, _nonempty, _unique_ids
from .biology import sourced

CHAPTER = sourced({'id':_TEXT,'title':_TEXT,'explanation':_TEXT,'details':_strings(),
    'example':_TEXT,'why_it_matters':_TEXT})
INDIA_LESSON_SCHEMA = _object({
    'theme':{'type':'STRING','enum':['heritage','science_technology','nature_geography','people_society','history','arts_culture','everyday_systems']},
    'question':_TEXT,'learning_goal':_TEXT,'central_idea':_TEXT,'region':_TEXT,'period':_TEXT,
    'opening_story':sourced({'title':_TEXT,'story':_TEXT,'question':_TEXT}),
    'background':sourced({'explanation':_TEXT,'key_terms':_items(_object({'term':_TEXT,'meaning':_TEXT}))}),
    'chapters':_items(CHAPTER),
    'case_study':sourced({'title':_TEXT,'place':_TEXT,'story':_TEXT,'what_it_shows':_TEXT}),
    'timeline':_items(sourced({'period':_TEXT,'event':_TEXT,'significance':_TEXT})),
    'wider_connections':sourced({'explanation':_TEXT,'examples':_strings()}),
    'nuances':_items(sourced({'idea':_TEXT,'clarification':_TEXT})),
    'photos':_items(_object({'id':_TEXT,'section_id':_TEXT,'subject':_TEXT,
        'kind':{'type':'STRING','enum':['person','place','object','scene']},'query':_TEXT})),
    'knowledge_checks':_items(_object({'question':_TEXT,'answer':_TEXT,'explanation':_TEXT})),
    'takeaways':_strings(),'related_topics':_strings(),
})
INDIA_RESPONSE_SCHEMA=deepcopy(PHYSICS_RESPONSE_SCHEMA)
del INDIA_RESPONSE_SCHEMA['properties']['physics_lesson']
INDIA_RESPONSE_SCHEMA['required'].remove('physics_lesson')
INDIA_RESPONSE_SCHEMA['properties'].update({'article_type':{'type':'STRING','enum':['india_lesson']},'india_lesson':INDIA_LESSON_SCHEMA})
INDIA_RESPONSE_SCHEMA['required'].append('india_lesson')
INDIA_RESPONSE_SCHEMA['properties']['visual_suggestions']=_object({'cover':_TEXT,'overview':_TEXT})
# Optional for stored first-version lessons; requested for new generations.
INDIA_LESSON_SCHEMA['properties']['carousel_queries']=_strings()

INDIA_IMAGE_INSTRUCTIONS='''
INDIA IMAGE PLAN overrides the ordinary 3-5-image plan:
Generate EXACTLY TWO images: cover and overview. Every other visual_suggestions value is empty.
The cover is a full-screen editorial illustration of this exact topic: a clear subject toward the
center-right, quiet left third for the title, generous mobile crop margins, no text or fake writing.
The overview is a different, self-contained visual summary, also used on discovery cards.
Return exactly one image_details record: slot overview, placement overview, alt, caption and learning_purpose.
Describe generated reconstructions as illustrations, never authentic historical evidence.
Documentary photos come from the separate photos list and never trigger AI generation.
'''

def validate_india_images(fact):
    visuals=fact.get('visual_suggestions');details=fact.get('image_details')
    return (isinstance(visuals,dict) and all(isinstance(v,str) for v in visuals.values())
        and {k for k,v in visuals.items() if v.strip()}=={'cover','overview'}
        and isinstance(details,list) and len(details)==1 and details[0].get('slot')=='overview'
        and details[0].get('placement')=='overview'
        and all(_nonempty(details[0].get(k)) for k in ('alt','caption','learning_purpose')))

def validate_india_content(fact):
    """Check structure and source attribution, not historical or scientific truth."""
    try:
        if not _shape(fact,INDIA_RESPONSE_SCHEMA) or not validate_india_images(fact):return False
        l=fact['india_lesson'];sources=fact['sources']
        def meaningful(value):
            if isinstance(value,str):return bool(value.strip())
            if isinstance(value,dict):return all(meaningful(v) for v in value.values())
            if isinstance(value,list):return all(meaningful(v) for v in value)
            return True
        if not meaningful(l):return False
        if not _unique_ids(sources) or not sources:return False
        ids={s['id'] for s in sources}
        def linked(item):return bool(item['source_ids']) and set(item['source_ids'])<=ids
        if not all(_nonempty(l[k]) for k in ('question','learning_goal','central_idea','region','period')):return False
        if not 3<=len(l['chapters'])<=6 or not _unique_ids(l['chapters']):return False
        if any(not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}',c['id']) for c in l['chapters']):return False
        if any(c['id'] in {'opening','background','case-study','connections'} for c in l['chapters']):return False
        for c in l['chapters']:
            if not all(_nonempty(c[k]) for k in ('title','explanation','example','why_it_matters')) or not 2<=len(c['details'])<=4 or not all(map(_nonempty,c['details'])):return False
        if not 1<=len(l['nuances'])<=3 or not 1<=len(l['knowledge_checks'])<=3:return False
        if not 2<=len(l['takeaways'])<=5 or len(l['timeline'])>6:return False
        if not all(linked(x) for x in [l['opening_story'],l['background'],*l['chapters'],l['case_study'],l['wider_connections'],*l['timeline'],*l['nuances']]):return False
        photos=l['photos'];sections={'opening','background','case-study','connections',*(c['id'] for c in l['chapters'])}
        if 'carousel_queries' in l and (not 1<=len(l['carousel_queries'])<=6 or any(not _nonempty(q) or len(q)>160 or q.strip().casefold() in ('india','indian') for q in l['carousel_queries'])):return False
        if not 2<=len(photos)<=6 or not _unique_ids(photos):return False
        if len({p['section_id'] for p in photos})!=len(photos):return False
        if any(p['section_id'] not in sections or not all(_nonempty(p[k]) for k in ('subject','query')) or len(p['query'])>160 for p in photos):return False
        return True
    except (KeyError,TypeError,ValueError):return False

def india_photo_entries(fact):
    return [dict(p,key=f'india_photo_{n}') for n,p in enumerate(fact.get('india_lesson',{}).get('photos',[])[:6])]

def india_carousel_queries(fact):
    """Different concrete subjects and concise searches from the lesson, never generic India stock."""
    queries=list(dict.fromkeys(q.strip()[:160] for q in fact.get('india_lesson',{}).get('carousel_queries',[]) if q.strip() and q.strip().casefold() not in ('india','indian')))
    for photo in india_photo_entries(fact):
        if photo['kind']=='person':continue
        for query in (photo['query'],photo['subject']):
            query=query.strip()[:160]
            if query.casefold() in ('india','indian') or query.casefold() in [q.casefold() for q in queries]:continue
            queries.append(query)
    return queries[:6]

def india_carousel_keys(fact):
    if fact.get('india_media',{}).get('carousel_version') not in (1,2):return []
    return [f'india_scene_{n}' for n in range(india_carousel_per_query(fact)*len(india_carousel_queries(fact)))]

def india_carousel_per_query(fact):
    return 3 if fact.get('india_media',{}).get('carousel_version')==2 else 2

PHOTO_STOPWORDS={'india','indian','photo','photograph','the','and','for','with','from','near','view','landscape','village','hill','hills'}
def _photo_words(value):
    words=re.findall(r'[^\W_]+',str(value).casefold())
    return {w[:-1] if len(w)>4 and w.endswith('s') and not w.endswith('ss') else w for w in words if len(w)>=3}

def india_carousel_matches(photo,query,fact):
    """Require subject evidence. Geography alone must never qualify a photo."""
    lesson=fact.get('india_lesson',{})
    geography=_photo_words(','.join(lesson.get('region','').split(',')[:2])+' '+lesson.get('case_study',{}).get('place',''))
    wanted=_photo_words(query)-geography-PHOTO_STOPWORDS
    evidence=_photo_words(' '.join([photo.get('title',''),photo.get('description',''),photo.get('alt_description',''),
        photo.get('location_country',''),photo.get('location_name',''),' '.join(t for t in (photo.get('tags') or []) if isinstance(t,str))]))
    core=_photo_words(fact.get('topic',''))-geography-PHOTO_STOPWORDS
    regional=_photo_words(query)&geography-PHOTO_STOPWORDS
    minimum=min(2,len(wanted))
    if not wanted and regional:wanted=core;minimum=1
    return bool(wanted and len(wanted&evidence)>=minimum and (not core or core&evidence) and (not regional or regional&evidence))

def india_carousel_tag_matches(photo,query,fact):
    lesson=fact.get('india_lesson',{})
    geography=_photo_words(','.join(lesson.get('region','').split(',')[:2])+' '+lesson.get('case_study',{}).get('place',''))
    wanted=(_photo_words(query)-geography-PHOTO_STOPWORDS) or (_photo_words(fact.get('topic',''))-geography-PHOTO_STOPWORDS)
    tags=_photo_words(' '.join(t for t in (photo.get('tags') or []) if isinstance(t,str)))
    return bool(tags&wanted) and india_carousel_matches(photo,query,fact)

def india_carousel_accepted(photo,query,fact):
    popular=(photo.get('provider')=='unsplash' and photo.get('detail_fetched') is True
        and photo.get('selection_mode')=='popular_fallback' and bool(query.strip()))
    return popular or india_carousel_matches(photo,query,fact)

def india_carousel_searches(query,fact):
    lesson=fact.get('india_lesson',{})
    geography=_photo_words(','.join(lesson.get('region','').split(',')[:2])+' '+lesson.get('case_study',{}).get('place',''))
    words=re.findall(r'[^\W_]+',query)
    subject=[word for word in words if _photo_words(word) and not (_photo_words(word)&(geography|PHOTO_STOPWORDS))]
    short=' '.join(subject)
    location=next((word for word in words if _photo_words(word)&(geography-PHOTO_STOPWORDS)),None)
    if not location:location=lesson.get('region','').split(',')[0].strip()
    noun=subject[-1] if subject else ''
    variations=[query,short,f'{location} {noun}' if location and noun else '', ' '.join(subject[-2:]),location]
    return list(dict.fromkeys(v for v in variations if v and v.strip()))[:5]

def prepare_india_media(fact):
    fact['visual_suggestions']={k:v for k,v in fact['visual_suggestions'].items() if k in ('cover','overview')}
    fact['images']={};fact['image_credits']={}
    fact['india_media']={'version':1,'generated_limit':2,'photo_limit':6,'generated_slots':['cover','overview'],
        'carousel_version':2,'carousel_limit':18}
    fact['india_validation']={'structure_checked':True,'source_verification':'not_performed'}

def build_india_prompt(blocklist):
    return f'''Create an india_lesson about ONE rich, specific topic connected to India.
Avoid these recent topics: {blocklist}.
Choose an accessible easy-to-medium topic with enough depth for a curious non-expert: a stepwell's
water system, a craft and its makers, a railway practice, a regional ecosystem, a scientific achievement,
a historical exchange, a language tradition or an everyday institution. Vary regions, periods and themes.
Do NOT write an overview of India, a list of unrelated facts, or another country's portrait.
Aim for a focused 7-10 minute read. Explain unfamiliar words on first use. Prefer short clear sentences.
Flow: a concrete opening story and question; short central answer; enough background; 3-6 connected
chapters; one real named case study; an optional timeline; wider connections; nuance; recall and takeaways.
Each chapter develops ONE part of the same topic in 100-180 words, with 2-4 useful details, a concrete
example and why it matters. Explain how and why, not just names and dates. Never pad to hit a word count.
Make the case study a complete 100-180-word explanation, with place and what it demonstrates.
Define region and period precisely. Local customs are not universal Indian practices. Distinguish historical
practice, present use, regional variation and uncertainty. Avoid unsupported greatest/first/oldest claims.
Use real, credible primary or scholarly sources. All factual blocks carry resolving source_ids.
No invented quotes, dates, sources, measurements or heroic claims. Clearly label hypothetical examples.
Keep timeline empty if chronology adds nothing; never invent events to fill it. Sources appear only at bottom.
Supply 2-6 focused documentary photo requests, each bound to a DIFFERENT existing section_id:
opening, background, a chapter id, case-study, or connections. Include exact subject and concise query.
Use kind person only for a named person, place for an identifiable named place, object for a named artifact
or dish, scene for general activities or landscape. Keep query India-specific and short. Generic portraits
must never stand in for named people. Do not request decorative or repeated photos. Photo availability is not guaranteed.
Also provide carousel_queries: 3-6 distinct concise Unsplash searches connected to THIS topic, using
concrete keywords rather than long prose. Include the main subject, relevant activities/materials,
and useful related regional examples (for a stepwell lesson: Rani ki Vav, Gujarat stepwell,
Adalaj stepwell). Do not include named-person portraits or generic India/travel searches.
These documentary carousel photos are separate from the two AI illustrations and inline exact-subject photos.
Return plain paragraphs, no embedded source lists, HTML, code or diagrams made of numbered circles.
Preserve common summary, core_mechanics and learning_takeaways for legacy readers.
'''
