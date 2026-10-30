"""A country portrait with at most four generated illustrations plus licensed photo galleries."""
import json
import re
from copy import deepcopy
from datetime import date
from pathlib import Path
from .schemas import _object, _items, _strings, _TEXT
from .physics import PHYSICS_RESPONSE_SCHEMA, _shape, _nonempty, _unique_ids
from .biology import sourced

REGISTRY = json.loads(Path(__file__).with_name('country_registry.json').read_text())
PHOTO_KEYS = ('cover', 'overview', 'how_it_works', 'explanation_2', 'explanation_3', 'explanation_4', 'explanation_5', 'explanation_6')
GENERATED_KEYS = PHOTO_KEYS[:4]
COMMONS_KEYS = PHOTO_KEYS[4:]
PLACEMENTS = ('overview', 'geography', 'everyday', 'contributions', 'places', 'people', 'curiosity')
SHORT_STORY = sourced({'title': _TEXT, 'explanation': _TEXT, 'why_it_matters': _TEXT})
STORY = sourced({'title': _TEXT, 'explanation': _TEXT, 'why_it_matters': _TEXT,
    'details': _strings(), 'example': _TEXT, 'photo_subject': _TEXT, 'photo_queries': _strings()})
CULTURE_STORY = deepcopy(STORY)
# New generations name a concrete visual subject and alternative search terms.
CULTURE_STORY['properties']['photo_subject'] = _TEXT
STAT = sourced({'value': {'type': 'NUMBER', 'nullable': True}, 'year': {'type': 'INTEGER', 'nullable': True}, 'unit': _TEXT, 'scope': _TEXT})
PROFILE_SCHEMA = _object({
    'identity': _object({'iso2': _TEXT, 'name': _TEXT}),
    'introduction': sourced({'central_idea': _TEXT, 'surprising_fact': _TEXT, 'learning_goals': _strings()}),
    'geography': sourced({'location_explanation': _TEXT, 'seas': _strings(), 'landscapes': _strings(),
        'major_cities': _items(_object({'name': _TEXT, 'significance': _TEXT}))}),
    'essentials': _object({'population': STAT, 'time_zones': sourced({'explanation': _TEXT}),
        'spoken_languages': _items(sourced({'name': _TEXT, 'role': {'type': 'STRING', 'enum': ['official', 'national', 'widely_spoken', 'regional', 'minority', 'other']}, 'explanation': _TEXT}))}),
    'flag': sourced({'description': _TEXT, 'symbolism': _TEXT}),
    'everyday_life': _items(CULTURE_STORY),
    'history_milestones': _items(sourced({'date_label': _TEXT, 'event': _TEXT, 'significance': _TEXT})),
    'global_contributions': _items(STORY), 'products_and_industries': _items(STORY),
    'notable_places': _items(sourced({'name': _TEXT, 'kind': {'type': 'STRING', 'enum': ['natural', 'cultural', 'city', 'everyday', 'other']}, 'location': _TEXT, 'explanation': _TEXT, 'why_it_matters': _TEXT,
        'details': _strings(), 'example': _TEXT, 'photo_subject': _TEXT, 'photo_queries': _strings()})),
    'notable_people': _items(sourced({'name': _TEXT, 'field': _TEXT, 'connection': _TEXT, 'contribution': _TEXT, 'context': _TEXT,
        'details': _strings(), 'example': _TEXT, 'photo_subject': _TEXT, 'photo_queries': _strings()})),
    'surprising_facts': _items(SHORT_STORY),
    'common_misunderstandings': _items(sourced({'misunderstanding': _TEXT, 'explanation': _TEXT})),
    'knowledge_checks': _items(_object({'question': _TEXT, 'answer': _TEXT, 'explanation': _TEXT})),
    'takeaways': _strings(), 'curiosity_questions': _strings(), 'related_topics': _strings(),
})
COUNTRY_RESPONSE_SCHEMA = deepcopy(PHYSICS_RESPONSE_SCHEMA)
del COUNTRY_RESPONSE_SCHEMA['properties']['physics_lesson']
COUNTRY_RESPONSE_SCHEMA['required'].remove('physics_lesson')
COUNTRY_RESPONSE_SCHEMA['properties'].update({'article_type': {'type': 'STRING', 'enum': ['country_profile']}, 'country_profile': PROFILE_SCHEMA,
    'visual_suggestions': _object({key: _TEXT for key in PHOTO_KEYS}),
    'image_details': _items(_object({'slot': {'type': 'STRING', 'enum': list(PHOTO_KEYS[1:])},
        'placement': {'type': 'STRING', 'enum': list(PLACEMENTS)}, 'alt': _TEXT, 'caption': _TEXT, 'learning_purpose': _TEXT}))})
COUNTRY_RESPONSE_SCHEMA['required'].append('country_profile')


def validate_country_images(fact):
    visuals, details = fact.get('visual_suggestions'), fact.get('image_details')
    if not isinstance(visuals, dict) or not isinstance(details, list) or any(not isinstance(v, str) for v in visuals.values()):
        return False
    active = {k for k, v in visuals.items() if v.strip()}
    if not {'cover', 'overview'} <= active or not active <= set(PHOTO_KEYS) or not active.intersection(COMMONS_KEYS):
        return False
    if len(details) != len(active) - 1 or any(not isinstance(d, dict) for d in details):
        return False
    slots = [d.get('slot') for d in details]
    if any(not isinstance(k, str) for k in slots) or len(set(slots)) != len(slots) or set(slots) != active - {'cover'}:
        return False
    if sum(d.get('placement') == 'people' for d in details) > 1:
        return False
    if any(len(visuals[k]) > (5000 if k in GENERATED_KEYS else 300) for k in active):
        return False
    return all(d.get('placement') in PLACEMENTS and (d['slot'] != 'overview' or d['placement'] == 'overview')
        and (d['slot'] == 'overview' or d['placement'] != 'overview')
        and all(_nonempty(d.get(k)) and len(d[k]) <= 1200 for k in ('alt', 'caption', 'learning_purpose')) for d in details)


def validate_country_content(fact):
    try:
        if not _shape(fact, COUNTRY_RESPONSE_SCHEMA) or not validate_country_images(fact):
            return False
        p = fact['country_profile']; identity = p['identity']; entry = REGISTRY.get(identity['iso2'])
        if not entry or identity['name'].casefold() not in [s.casefold() for s in (entry['name'], entry['official_name'], *entry['local_names'])]:
            return False
        if not all(_nonempty(fact[k]) for k in ('topic', 'headline_fact', 'summary')) or not _unique_ids(fact['sources']):
            return False
        ids = {s['id'] for s in fact['sources']}
        def valid(value):
            if isinstance(value, dict):
                if 'source_ids' in value and (not value['source_ids'] or not set(value['source_ids']) <= ids): return False
                return all(valid(child) for key, child in value.items() if key != 'source_ids')
            if isinstance(value, list): return all(valid(v) for v in value)
            if isinstance(value, str): return bool(value.strip())
            return True
        # Unknown population is allowed; year is never silently inferred from publication time.
        stat = p['essentials']['population']
        if stat['value'] is not None and (stat['value'] <= 0 or stat['unit'] != 'people' or stat['year'] is None): return False
        if stat['year'] is not None and not 1800 <= stat['year'] <= date.today().year: return False
        if stat['value'] is None and stat['year'] is not None: return False
        ranges = {'everyday_life':(2,5),'history_milestones':(3,6),'global_contributions':(2,5),
            'products_and_industries':(2,5),'notable_places':(3,5),'notable_people':(3,5),
            'surprising_facts':(2,4),'common_misunderstandings':(1,3),'knowledge_checks':(1,3),
            'takeaways':(3,5),'curiosity_questions':(2,4),'related_topics':(1,6)}
        if any(not low <= len(p[key]) <= high for key, (low, high) in ranges.items()): return False
        if not 1 <= len(p['geography']['major_cities']) <= 6 or not 1 <= len(p['introduction']['learning_goals']) <= 4: return False
        if len(p['essentials']['spoken_languages']) > 8: return False
        if len({x['name'].casefold() for x in p['notable_people']}) != len(p['notable_people']): return False
        for field in ('everyday_life','global_contributions','products_and_industries','notable_places','notable_people'):
            for item in p[field]:
                if not 2 <= len(item['details']) <= 4 or not 1 <= len(item['photo_queries']) <= 3: return False
        if not any(x['kind'] in ('natural', 'everyday') for x in p['notable_places']): return False
        return valid(p)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def enrich_country_identity(fact):
    p = fact['country_profile']; code = p['identity']['iso2']; entry = REGISTRY[code]
    p['identity'] = {'iso2': code, **deepcopy(entry)}
    p['identity']['flag_url'] = f'https://flagcdn.com/w320/{code.lower()}.png'
    p['identity']['neighbour_names'] = [v['name'] for v in REGISTRY.values() if v['iso3'] in entry['neighbours']]
    p['data_context'] = {'snapshot_date': '2026-10-30', 'source': 'mledoze/countries',
        'source_url': 'https://github.com/mledoze/countries', 'license': 'ODbL 1.0',
        'currency_check': 'not_performed', 'population_verification': 'not_performed'}
    # Replace any model-authored assets/credits. Photos are resolved independently by the worker.
    fact['visual_suggestions'] = {key:value.strip() for key,value in fact['visual_suggestions'].items() if key in PHOTO_KEYS and value.strip()}
    fact['images'] = {}; fact['image_credits'] = {}; fact['country_photo_galleries'] = {}
    fact.pop('country_photo_enrichment',None)
    fact['country_media'] = {'version': 2, 'photo_layout': 'contextual_v2', 'generated_limit': 4,
        'generated_slots': [k for k in GENERATED_KEYS if fact['visual_suggestions'].get(k)],
        'commons_slots': [k for k in COMMONS_KEYS if fact['visual_suggestions'].get(k)]}
    fact['country_validation'] = {'structure_checked': True, 'identity_source': 'country_registry_snapshot',
        'source_verification': 'not_performed', 'checked_at': None, 'generated_image_limit': 4}
    return fact


COUNTRY_IMAGE_INSTRUCTIONS = """
COUNTRY VISUAL PLAN (replaces the ordinary 3-5 generated-image policy):
Generate at most FOUR images. There is no total visual limit for licensed Wikimedia photographs.
The server supplies the flag and map from country codes; never generate them or invent asset URLs.
visual_suggestions.cover and overview are REQUIRED image-generation prompts (about 100-180 words).
The cover is a beautiful editorial country landscape illustration with quiet space for title overlays.
The overview is a different visual summary composition, also used on discovery cards.
how_it_works and explanation_2 are OPTIONAL generation prompts; leave empty unless they teach something useful.
These four keys are the ONLY slots that use image generation. Never fabricate portraits, flags or banknotes.
Generated scenes are clearly labelled illustrations, not documentary photographs or authentic evidence.
explanation_3 through explanation_6 are SHORT Wikimedia Commons photograph search queries, NOT generation prompts.
Provide at least one, preferably 3-4 distinct photo searches for landscapes, everyday life, places or products.
Use a short specific subject and country name; omit stacks of adjectives. The worker has simpler search fallbacks.
Unused slots are empty strings. The worker can collect multiple licensed photos for a browsable carousel.
image_details describes every non-cover active slot exactly once, with alt, caption, learning_purpose
and placement overview/geography/everyday/contributions/places/people/curiosity.
Only overview uses overview placement. Photos need actual author, source and licence metadata from the worker.
Do not generate extra images when a Commons search fails. Cover/overview generation and local UI fallbacks
are separate from Commons lookup. Retain real licence metadata for all photographs.
The server independently searches four distinct Unsplash scene themes for the country carousel.
People and notable places receive exact-subject Commons searches beside their own entries.
For each everyday_life entry, include photo_subject: a short identifiable local dish, festival,
craft or cultural practice actually explained by that entry. Use its proper name, not a generic
stock-photo description or a long headline. Never invent a subject merely to obtain an image.
"""

def build_country_prompt(blocklist):
    from .prompts import _EVIDENCE_INSTRUCTIONS
    choices = ', '.join(f'{code}:{row["name"]}' for code, row in REGISTRY.items())
    return f"""Create an engaging country portrait for a curious non-expert. category country,
schema_version 2.0, article_type country_profile. Choose ONE country from {choices}.
Avoid previous topics: {', '.join(blocklist) or 'None'}. Match identity.iso2 and identity.name exactly.
This category is an exception to the single-fact length rule: teach a whole country through connected,
easy-to-medium explanations. A larger 8-15 minute read is allowed. Never become an advanced textbook.
Flow: introduction, geography, essentials, everyday life, short history, contributions and products,
3-5 places, 3-5 notable people from varied fields, surprising facts, misunderstandings, checks and curiosity.
Explain why each entry matters. Include natural/everyday places, food and regional differences.
Do not reduce a culture to stereotypes, tourist rankings or claims that everyone behaves alike.
Separate products, exports, industries and brands; origin, headquarters and manufacture are different.
Explain each person's connection to the country without assuming birthplace equals nationality.
Shape the learning sequence for a curious beginner: one short introduction, essentials and location,
then everyday life, history, contributions, places and people, followed by a clear recap.
headline_fact is one interesting hook. summary gives a different, broad introduction to the country
in 2-3 plain sentences; do not repeat the hook. central_idea is one short sentence to remember at
the end, not a second copy of the summary. learning_goals use simple, concrete language.
Use plain text in structured profile prose, with actual paragraph breaks where useful.
City significance explains what the city is known for and its role in 2-3 complete sentences.
History significance explains the background, what changed and the consequence in 2-3 short sentences.
Time-zone explanations define the UTC offset in simple language. Describe flag colours and layout
before discussing meanings, and distinguish documented meanings from popular interpretations.
Keep city detail secondary; usually select 2-3 useful cities. Explain any necessary specialist term
where it first appears. Avoid advanced economic, political or geographic vocabulary without a plain explanation.
Geography describes neighbours, seas, landscapes and 1-6 major cities. The server supplies country map data.
The server supplies snapshot names, capitals, currencies, listed languages, area and coordinates.
Explain language roles (official/national/widely_spoken/regional/minority) with supporting sources.
The snapshot language list alone does not prove legal official status. Never infer that status from common use.
Population needs value, measurement year, unit people, scope and source_ids; unknown value/year are null.
Never invent current statistics, exchange rates, political leaders, rankings or verification dates.
Dates and boundaries can be disputed; explain relevant context neutrally without implying endorsement.
history_milestones use meaningful dates, event and significance. Avoid text-only numbered-circle diagrams.
Every explanatory entry carries resolving source_ids; prefer national statistics, central banks, official
institutions and reliable museums/history references. Do not invent sources or exact quotations.
Keep common summary/core_mechanics/learning_takeaways for older readers. No source lists inside prose.
Flag description and symbolism need sources; say evidence is limited instead of inventing meanings.
COMPLETE TOPIC EXPLANATIONS: everyday_life, global_contributions, products_and_industries,
notable_places and notable_people each need 2-4 useful details and a concrete example, not filler.
For each topic, explain what it is, how it works or developed, and why it matters. Use 40-90 plain
words for its main explanation, split into short paragraphs when useful, plus concise details and
a 20-40 word example. People need a clear contribution and context; places need what the reader
would actually see and why it matters. History significance must connect cause and consequence.
Do not substitute long lists, repeated praise or generic claims for an explanation. Keep all text
simple enough for a curious beginner. Explain necessary terms immediately. Source the details and
examples with the entry's source_ids; omit unsupported details instead of inventing them.
For each core entry, photo_subject names a concrete depicted subject and photo_queries contains
1-3 concise Commons searches using proper/local names and useful aliases. Gallo Pinto is a useful
subject; 'Gallo Pinto and Daily Cuisine' is a headline, not a search. For an abstract concept choose
a concrete object, institution or setting actually discussed, and clearly describe its connection.
Never use generic portraits for named people or claim a context photo documents a historical event.
{_EVIDENCE_INSTRUCTIONS}
"""
