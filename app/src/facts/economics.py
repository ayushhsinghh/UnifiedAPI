"""Beginner economics lessons: explicit assumptions, linked actors and bounded numerical evidence."""
from copy import deepcopy
from datetime import date
import math
import re
from .schemas import _object, _items, _strings, _TEXT, _SOURCE_IDS_SCHEMA
from .physics import PHYSICS_RESPONSE_SCHEMA, _shape, _unique_ids
from .india import validate_india_images

def sourced(fields):
    return _object({**fields, 'source_ids': _SOURCE_IDS_SCHEMA})

NUMBER = {'type': 'NUMBER'}
PROVENANCE = _object({'kind': {'type': 'STRING', 'enum': ['illustrative', 'observed']},
    'period': {**_TEXT, 'nullable': True}, 'geography': {**_TEXT, 'nullable': True},
    'as_of': {**_TEXT, 'nullable': True}, 'description': _TEXT})
DIAGRAM = sourced({'type': {'type': 'STRING', 'enum': ['bar', 'line', 'comparison']},
    'title': _TEXT, 'caption': _TEXT, 'description': _TEXT, 'assumptions': _strings(),
    'provenance': PROVENANCE, 'x_label': {**_TEXT, 'nullable': True},
    'unit': {**_TEXT, 'nullable': True}, 'labels': _strings(),
    'series': _items(_object({'name': _TEXT, 'values': _items(NUMBER)})),
    'comparison_basis': {**_TEXT, 'nullable': True},
    'comparisons': _items(_object({'name': _TEXT, 'approach': _TEXT, 'benefit': _TEXT, 'cost': _TEXT, 'conditions': _TEXT}))})
ECONOMICS_LESSON_SCHEMA = _object({
    'identity': sourced({'name': _TEXT, 'branch': _TEXT, 'scope': _TEXT, 'geography': _TEXT}),
    'hook': _TEXT, 'question': _TEXT, 'learning_goal': _TEXT,
    'opening_scenario': sourced({'title': _TEXT, 'experience': _TEXT, 'question': _TEXT}),
    'central_idea': _TEXT,
    'key_terms': _items(sourced({'term': _TEXT, 'meaning': _TEXT})),
    'mechanism': _object({
        'actors': _items(sourced({'id': _TEXT, 'name': _TEXT, 'role': _TEXT})),
        'steps': _items(sourced({'id': _TEXT, 'title': _TEXT, 'actor_ids': _strings(),
            'action': _TEXT, 'what_changes': _TEXT, 'why_next': _TEXT, 'conditions': _strings()}))}),
    'worked_example': sourced({'title': _TEXT, 'provenance': PROVENANCE, 'assumptions': _strings(),
        'values': _items(_object({'id': _TEXT, 'label': _TEXT, 'value': NUMBER, 'unit': _TEXT})),
        'calculations': _items(_object({'id': _TEXT, 'label': _TEXT,
            'operation': {'type': 'STRING', 'enum': ['add', 'subtract', 'multiply', 'divide']},
            'operand_ids': _strings(), 'result': NUMBER, 'unit': _TEXT, 'explanation': _TEXT})),
        'reasoning': _strings(), 'outcome': _TEXT, 'explanation': _TEXT, 'limits': _strings()}),
    'diagram': {**DIAGRAM, 'nullable': True},
    'distributional_effects': _items(sourced({'actor_id': _TEXT, 'benefit': _TEXT, 'cost': _TEXT,
        'time_horizon': _TEXT, 'conditions': _TEXT})),
    'real_world_case': {**sourced({'title': _TEXT, 'place': _TEXT, 'period': _TEXT,
        'explanation': _TEXT, 'connection': _TEXT, 'limits': _TEXT}), 'nullable': True},
    'conditions_and_limits': _items(sourced({'title': _TEXT, 'explanation': _TEXT})),
    'misconceptions': _items(sourced({'belief': _TEXT, 'correction': _TEXT, 'explanation': _TEXT})),
    'optional_depth': _items(sourced({'title': _TEXT, 'explanation': _TEXT})),
    'knowledge_checks': _items(_object({'question': _TEXT, 'answer': _TEXT, 'explanation': _TEXT})),
    'takeaways': _strings(), 'related_topics': _strings(),
    'photos': _items(_object({'id': _TEXT,
        'section_id': {'type': 'STRING', 'enum': ['overview', 'mechanism', 'example', 'effects', 'case', 'limits']},
        'kind': {'type': 'STRING', 'enum': ['setting', 'process', 'named_place', 'historical_object', 'person']},
        'subject': _TEXT, 'queries': _strings()}))})
ECONOMICS_RESPONSE_SCHEMA = deepcopy(PHYSICS_RESPONSE_SCHEMA)
del ECONOMICS_RESPONSE_SCHEMA['properties']['physics_lesson']
ECONOMICS_RESPONSE_SCHEMA['required'].remove('physics_lesson')
ECONOMICS_RESPONSE_SCHEMA['properties'].update({'article_type': {'type': 'STRING', 'enum': ['economics_lesson']},
    'economics_lesson': ECONOMICS_LESSON_SCHEMA})
ECONOMICS_RESPONSE_SCHEMA['required'].append('economics_lesson')
ECONOMICS_RESPONSE_SCHEMA['properties']['visual_suggestions'] = _object({'cover': _TEXT, 'overview': _TEXT})

def simple_id(value):
    return isinstance(value, str) and bool(re.fullmatch('[a-z][a-z0-9_-]{0,47}', value))

def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and abs(value) <= 1e15

def valid_provenance(value):
    if not _shape(value, PROVENANCE): return False
    if value['kind'] == 'observed' and any(not value[k] for k in ('period', 'geography', 'as_of')): return False
    if value['as_of'] is not None:
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value['as_of']) or date.fromisoformat(value['as_of']) > date.today(): return False
        except ValueError: return False
    return True

def valid_example(example):
    if not valid_provenance(example['provenance']): return False
    values, calculations = example['values'], example['calculations']
    if len(values) > 8 or len(calculations) > 6 or not _unique_ids(values + calculations): return False
    known = {}
    for item in values:
        if not simple_id(item['id']) or not finite(item['value']): return False
        known[item['id']] = item['value']
    for item in calculations:
        if not simple_id(item['id']) or len(item['operand_ids']) != 2 or not finite(item['result']): return False
        if any(i not in known for i in item['operand_ids']): return False
        a, b = (known[i] for i in item['operand_ids'])
        if item['operation'] == 'divide' and b == 0: return False
        expected = {'add': lambda: a+b, 'subtract': lambda: a-b, 'multiply': lambda: a*b,
                    'divide': lambda: a/b}[item['operation']]()
        if not finite(expected) or not math.isclose(expected, item['result'], rel_tol=1e-6, abs_tol=1e-6): return False
        known[item['id']] = item['result']
    return (1 <= len(example['assumptions']) <= 5 and 1 <= len(example['reasoning']) <= 6
            and 1 <= len(example['limits']) <= 4 and (not values or bool(calculations)))

def valid_economics_diagram(diagram):
    if diagram is None: return True
    if not _shape(diagram, DIAGRAM) or not valid_provenance(diagram['provenance']): return False
    if diagram['type'] == 'comparison':
        return (not diagram['labels'] and not diagram['series'] and diagram['unit'] is None
                and diagram['x_label'] is None and bool(diagram['comparison_basis']) and 2 <= len(diagram['comparisons']) <= 3)
    labels, series = diagram['labels'], diagram['series']
    return (2 <= len(labels) <= 10 and len(set(labels)) == len(labels) and 1 <= len(series) <= 3
            and len({s['name'] for s in series}) == len(series) and bool(diagram['unit']) and bool(diagram['x_label'])
            and not diagram['comparisons'] and diagram['comparison_basis'] is None
            and all(len(s['values']) == len(labels) and all(finite(v) for v in s['values']) for s in series))

def economics_photo_entries(fact):
    return [dict(p, key=f'economics_photo_{i}') for i, p in enumerate(fact.get('economics_lesson', {}).get('photos', [])[:6])]

def validate_economics_content(fact):
    try:
        if not _shape(fact, ECONOMICS_RESPONSE_SCHEMA) or not validate_india_images(fact): return False
        lesson, sources = fact['economics_lesson'], fact['sources']
        if not sources or not _unique_ids(sources): return False
        source_ids = {s['id'] for s in sources}
        def check(value):
            if isinstance(value, dict):
                if 'source_ids' in value and (not value['source_ids'] or not set(value['source_ids']) <= source_ids): return False
                return all(check(v) for v in value.values())
            if isinstance(value, list): return all(check(v) for v in value)
            return not isinstance(value, str) or bool(value.strip())
        if not check(lesson): return False
        actors, steps = lesson['mechanism']['actors'], lesson['mechanism']['steps']
        if not 1 <= len(actors) <= 5 or not 3 <= len(steps) <= 6: return False
        if not _unique_ids(actors) or not _unique_ids(steps) or any(not simple_id(p['id']) for p in actors + steps): return False
        actor_ids = {p['id'] for p in actors}
        if any(not s['actor_ids'] or len(set(s['actor_ids'])) != len(s['actor_ids']) or not set(s['actor_ids']) <= actor_ids or not 1 <= len(s['conditions']) <= 3 for s in steps): return False
        if not actor_ids <= {i for s in steps for i in s['actor_ids']}: return False
        if not valid_example(lesson['worked_example']) or not valid_economics_diagram(lesson['diagram']): return False
        if len(lesson['key_terms']) > 6 or len(lesson['distributional_effects']) > 5: return False
        if any(e['actor_id'] not in actor_ids for e in lesson['distributional_effects']): return False
        if len({e['actor_id'] for e in lesson['distributional_effects']}) != len(lesson['distributional_effects']): return False
        if not 1 <= len(lesson['conditions_and_limits']) <= 4 or not 1 <= len(lesson['misconceptions']) <= 4: return False
        if len(lesson['optional_depth']) > 3 or not 1 <= len(lesson['knowledge_checks']) <= 3: return False
        if not 2 <= len(lesson['takeaways']) <= 5 or not 1 <= len(lesson['related_topics']) <= 6: return False
        photos = lesson['photos']
        if len(photos) > 6 or not _unique_ids(photos) or len({p['section_id'] for p in photos}) != len(photos): return False
        for p in photos:
            if not simple_id(p['id']) or not 1 <= len(p['queries']) <= 2 or any(len(q) > 160 for q in p['queries']): return False
            if p['section_id'] == 'case' and lesson['real_world_case'] is None: return False
            if p['section_id'] == 'effects' and not lesson['distributional_effects']: return False
        return True
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError): return False

def prepare_economics_media(fact):
    fact['visual_suggestions'] = {k: v for k, v in fact['visual_suggestions'].items() if k in ('cover', 'overview')}
    fact['images'] = {}; fact['image_credits'] = {}
    fact['economics_media'] = {'version': 1, 'generated_limit': 2, 'generated_slots': ['cover', 'overview'], 'photo_timeout_seconds': 720}
    fact['economics_validation'] = {'structure_checked': True, 'arithmetic_checked': True,
        'source_verification': 'not_performed', 'data_verification': 'not_performed'}

ECONOMICS_IMAGE_INSTRUCTIONS = '''ECONOMICS IMAGE PLAN overrides the ordinary generated-image plan.
Generate exactly TWO conceptual illustrations: cover and overview/card. Return one image_details record
for overview with placement overview, alt, caption and learning_purpose. Cover has one coherent everyday
scene, subject center-right, quiet left for title and mobile-safe crop. No lettering, fake currency,
charts, statistics, documents or misleading documentary evidence. Overview explains the same idea visually.
The UI draws charts from structured data, never generated images. Request zero to six section-bound
documentary photos only when they teach a real setting or process. Do not force stock money photos.
Named places, historical objects and people use Commons only. No additional AI images.
'''

def build_economics_prompt(blocklist):
    return f'''Create ONE economics_lesson, category economics, schema_version 2.0.
Avoid recent topics: {blocklist}. Teach one easy-to-medium global economics concept to a curious beginner.
No India-first requirement. Use simple language, familiar choices and stable mechanisms, not market news,
investment recommendations, price forecasts, product rankings, advanced models or ideological advocacy.
Choose household choices, incentives, scarcity, trade, markets, firms, labour, public goods, money or
basic macroeconomics. Define necessary words at first use. Identity has name/branch/scope/geography.
Begin with hook/question/learning_goal/opening_scenario, then central_idea and zero to six key_terms.
mechanism contains 1-5 actors (id/name/role/source_ids), then 3-6 connected steps with id/title/actor_ids,
action/what_changes/why_next/conditions/source_ids. Use unique lowercase slug IDs. All actor references
resolve, and every actor participates. Each step has 1-3 explicit conditions. Explain decisions and why
the next change CAN occur; do not treat conditional economic effects as certain or confuse correlation
with causation. Final why_next explains the result rather than inventing another step.
worked_example contains title/provenance/assumptions/values/calculations/reasoning/outcome/explanation/limits/source_ids.
provenance kind is illustrative or observed; description states its status. period/geography/as_of may
be null for illustrative examples. Observed examples and charts require all three, valid nonfuture
YYYY-MM-DD as_of and resolving primary source_ids. Never invent observed data or claim live verification.
Prefer small illustrative numbers. Use 1-5 assumptions, 1-6 reasoning steps and 1-4 limits.
values: up to eight id/label/value/unit records. calculations: up to six id/label/operation/operand_ids/
result/unit/explanation records. Each operation add/subtract/multiply/divide uses exactly TWO references
to values or EARLIER results. Match the arithmetic within 0.000001 relative tolerance; no zero division,
NaN, infinity or values above 1e15. Give compatible units. If numbers add nothing, values/calculations
are both empty and reasoning explains a concrete qualitative example. Never execute model-authored code.
diagram may be null. Otherwise give type bar/line/comparison, title/caption/description/assumptions,
provenance/source_ids. Charts have x_label/unit, 2-10 unique category/time labels, 1-3 uniquely named series
with one finite numeric value per label. Bar charts include zero; line charts use ordered equally spaced
time intervals and explain the interval in x_label. No invented demand curves or fake measured trends.
comparisons is empty and comparison_basis null for charts. Comparison diagrams use 2-3 records with
name/approach/benefit/cost/conditions, a shared comparison_basis, empty labels/series and null unit/x_label.
distributional_effects has zero to five distinct actor_id/benefit/cost/time_horizon/conditions/source_ids
entries, without forcing winners or losers where irrelevant. Explain unequal effects and short/long term
differences where justified. real_world_case is nullable; include title/place/period/explanation/connection/
limits/source_ids only for a supported case. Otherwise omit it rather than fabricate a real event.
Include 1-4 conditions_and_limits, 1-4 misconceptions (belief/correction/explanation), up to three
optional_depth entries, 1-3 knowledge_checks with answer/explanation, 2-5 takeaways and 1-6 related_topics.
All explanatory facts reference root sources through source_ids; do not add inline source lists.
Use primary public statistical agencies, central banks, public institutions and accessible research.
Distinguish economic mechanism, empirical finding and policy opinion. State period, region, units,
nominal versus inflation-adjusted values and per-person versus total values when relevant. State what
the evidence does not establish. Do not invent sources, quotes or dates. Root compatibility fields agree
with the lesson. Photos have id/section_id/kind/subject/queries; section_id overview/mechanism/example/
effects/case/limits, one request per section, 1-2 concise exact queries. Omit case/effects photos if the
matching section is absent. Optional sections stay empty/null rather than adding filler.
'''
