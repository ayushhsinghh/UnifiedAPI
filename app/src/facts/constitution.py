"""A single constitutional idea for a non-expert: situation, provision, example and limits."""
import re
from copy import deepcopy
from .image_policy import validate_image_plan
from datetime import date
from urllib.parse import urlparse
from .schemas import _object, _items, _strings, _TEXT
from .physics import PHYSICS_RESPONSE_SCHEMA, _shape, _nonempty, _unique_ids
from .biology import sourced

LESSON_TYPES = ['right_or_principle', 'institution', 'procedure', 'amendment', 'case_explainer']
DIAGRAM_TYPES = ['scope_map', 'roles_map', 'process_sequence', 'before_after', 'case_path']
SOURCE_KINDS = ['constitutional_text', 'judgment', 'amendment', 'ordinary_law']
NULL_DATE = {'type': 'STRING', 'nullable': True}
CONSTITUTION_LESSON_SCHEMA = _object({
    'lesson_type': {'type': 'STRING', 'enum': LESSON_TYPES}, 'question': _TEXT, 'learning_goal': _TEXT,
    'opening_scenario': _object({'title': _TEXT, 'situation': _TEXT, 'question': _TEXT}),
    'big_idea': sourced({'explanation': _TEXT}),
    'constitutional_basis': _items(sourced({
        'id': _TEXT, 'reference': _TEXT, 'title': _TEXT, 'part_or_schedule': _TEXT,
        'source_kind': {'type': 'STRING', 'enum': SOURCE_KINDS},
        'provision_type': {'type': 'STRING', 'enum': ['fundamental_right', 'directive_principle', 'fundamental_duty', 'institutional_rule', 'procedure', 'other']},
        'plain_meaning': _TEXT, 'legal_effect': _TEXT, 'quote_candidate': _TEXT,
    })),
    'explanation_steps': _items(sourced({'id': _TEXT, 'title': _TEXT, 'explanation': _TEXT, 'basis_ids': _strings()})),
    'worked_example': sourced({'title': _TEXT, 'situation': _TEXT, 'reasoning_steps': _strings(), 'outcome': _TEXT, 'limits': _TEXT}),
    'scope_and_limits': sourced({'who_it_concerns': _strings(), 'conditions': _strings(), 'exceptions': _strings(), 'limits': _strings()}),
    'common_confusions': _items(sourced({'confusion': _TEXT, 'clarification': _TEXT})),
    'diagram': sourced({
        'type': {'type': 'STRING', 'enum': [*DIAGRAM_TYPES, 'none']}, 'title': _TEXT, 'caption': _TEXT, 'description': _TEXT, 'limitations': _strings(),
        'nodes': _items(_object({'id': _TEXT, 'label': _TEXT, 'detail': _TEXT})),
        'edges': _items(_object({'from_id': _TEXT, 'to_id': _TEXT, 'relationship': _TEXT})),
    }),
    'amendment_timeline': _items(sourced({'label': _TEXT, 'date': NULL_DATE, 'change': _TEXT, 'significance': _TEXT})),
    'case_note': {**sourced({'name': _TEXT, 'court': _TEXT, 'citation': _TEXT, 'decision_date': NULL_DATE,
                            'question': _TEXT, 'decision': _TEXT, 'significance': _TEXT, 'limits': _TEXT}), 'nullable': True},
    'key_terms': _items(_object({'term': _TEXT, 'definition': _TEXT})),
    'deeper_detail': _items(sourced({'title': _TEXT, 'explanation': _TEXT})),
    'knowledge_checks': _items(_object({'id': _TEXT, 'question': _TEXT, 'answer': _TEXT, 'explanation': _TEXT, 'related_step_ids': _strings()})),
    'takeaways': _strings(), 'related_concepts': _strings(),
})
CONSTITUTION_LESSON_SCHEMA['properties']['supporting_image'] = deepcopy(PHYSICS_RESPONSE_SCHEMA['properties']['physics_lesson']['properties']['supporting_image'])
CONSTITUTION_RESPONSE_SCHEMA = deepcopy(PHYSICS_RESPONSE_SCHEMA)
del CONSTITUTION_RESPONSE_SCHEMA['properties']['physics_lesson']
CONSTITUTION_RESPONSE_SCHEMA['required'].remove('physics_lesson')
CONSTITUTION_RESPONSE_SCHEMA['properties'].update({'article_type': {'type': 'STRING', 'enum': ['constitution_lesson']}, 'constitution_lesson': CONSTITUTION_LESSON_SCHEMA})
CONSTITUTION_RESPONSE_SCHEMA['required'].append('constitution_lesson')


def official_source(url):
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or '').lower()
        return parsed.scheme == 'https' and not parsed.username and not parsed.password and parsed.port in (None, 443) and any(host == root or host.endswith('.' + root) for root in ('legislative.gov.in', 'sansad.in', 'sci.gov.in', 'indiacode.nic.in', 'egazette.gov.in', 'egazette.nic.in'))
    except (TypeError, ValueError):
        return False


def validate_constitution_content(fact):
    """Check attribution and lesson shape, not legal correctness or currency."""
    try:
        if not _shape(fact, CONSTITUTION_RESPONSE_SCHEMA):
            return False
        l = fact['constitution_lesson']
        if not all(_nonempty(fact[k]) for k in ('topic', 'headline_fact', 'summary')) or not all(_nonempty(l[k]) for k in ('question', 'learning_goal')):
            return False
        if not all(_nonempty(v) for v in l['opening_scenario'].values()) or not _nonempty(l['big_idea']['explanation']):
            return False
        sources = {item['id']: item for item in fact['sources']}
        def attributed(item):
            return bool(item['source_ids']) and set(item['source_ids']) <= sources.keys() and any(official_source(sources[key]['url']) for key in item['source_ids'])
        bases, steps, checks = l['constitutional_basis'], l['explanation_steps'], l['knowledge_checks']
        if not 1 <= len(bases) <= 3 or not _unique_ids(bases):
            return False
        for b in bases:
            if not all(_nonempty(b[k]) for k in ('reference', 'title', 'plain_meaning', 'legal_effect')) or not attributed(b):
                return False
            if b['quote_candidate'] and (b['source_kind'] != 'constitutional_text' or not re.fullmatch(r'Article [1-9][0-9]{0,2}[A-Z]{0,2}', b['reference']) or not 40 <= len(b['quote_candidate']) <= 1200):
                return False
        if not 3 <= len(steps) <= 5 or not _unique_ids(steps) or not 2 <= len(checks) <= 3 or not _unique_ids(checks):
            return False
        basis_ids, step_ids = {b['id'] for b in bases}, {s['id'] for s in steps}
        if any(not all(_nonempty(s[k]) for k in ('title', 'explanation')) or not s['basis_ids'] or not set(s['basis_ids']) <= basis_ids or not attributed(s) for s in steps):
            return False
        if any(not all(_nonempty(c[k]) for k in ('question', 'answer', 'explanation')) or not c['related_step_ids'] or not set(c['related_step_ids']) <= step_ids for c in checks):
            return False
        example = l['worked_example']
        if not all(_nonempty(example[k]) for k in ('title', 'situation', 'outcome', 'limits')) or not example['reasoning_steps'] or not attributed(example):
            return False
        scope = l['scope_and_limits']
        if not attributed(scope) or any(not scope[k] for k in ('who_it_concerns', 'conditions', 'limits')):
            return False
        if not 1 <= len(l['common_confusions']) <= 3 or any(not all(_nonempty(item[k]) for k in ('confusion', 'clarification')) or not attributed(item) for item in l['common_confusions']):
            return False
        for field in ('amendment_timeline', 'deeper_detail'):
            if len(l[field]) > 4 or any(not attributed(item) for item in l[field]):
                return False
        for item in l['amendment_timeline']:
            if not all(_nonempty(item[k]) for k in ('label', 'change', 'significance')):
                return False
            if item['date'] is not None:
                date.fromisoformat(item['date'])
        case = l['case_note']
        if l['lesson_type'] == 'case_explainer' and not case:
            return False
        if l['lesson_type'] == 'amendment' and not l['amendment_timeline']:
            return False
        if case:
            if not all(_nonempty(case[k]) for k in ('name', 'court', 'citation', 'question', 'decision', 'significance', 'limits')) or not attributed(case):
                return False
            if case['decision_date'] is not None:
                date.fromisoformat(case['decision_date'])
        if any(not all(_nonempty(item[k]) for k in ('term', 'definition')) for item in l['key_terms']) or any(not all(_nonempty(item[k]) for k in ('title', 'explanation')) for item in l['deeper_detail']):
            return False
        d = l['diagram']
        if not _nonempty(d['description']):
            return False
        if d['type'] != 'none':
            if d['type'] != dict(zip(LESSON_TYPES, DIAGRAM_TYPES))[l['lesson_type']] or not 2 <= len(d['nodes']) <= 6 or not _unique_ids(d['nodes']) or not attributed(d):
                return False
            if not all(_nonempty(d[k]) for k in ('title', 'caption')) or not d['limitations'] or any(not all(_nonempty(n[k]) for k in ('label', 'detail')) for n in d['nodes']):
                return False
            node_ids = {n['id'] for n in d['nodes']}
            if not 1 <= len(d['edges']) <= 10 or any(e['from_id'] not in node_ids or e['to_id'] not in node_ids or e['from_id'] == e['to_id'] or not _nonempty(e['relationship']) for e in d['edges']):
                return False
            if {i for e in d['edges'] for i in (e['from_id'], e['to_id'])} != node_ids:
                return False
        if not validate_image_plan(fact):
            return False
        lists = [l['takeaways'], l['related_concepts'], example['reasoning_steps'], d['limitations'], *[scope[k] for k in ('who_it_concerns', 'conditions', 'exceptions', 'limits')]]
        return bool(l['takeaways']) and all(_nonempty(v) for values in lists for v in values)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def build_constitution_prompt(blocklist):
    from .prompts import _EVIDENCE_INSTRUCTIONS
    return f"""Teach ONE easy-to-medium Indian Constitution idea to a non-expert in plain language.
Avoid prior topics: {blocklist!r}. Return schema_version 2.0 and article_type constitution_lesson.
Choose ONE lesson_type right_or_principle/institution/procedure/amendment/case_explainer.
Start with a clearly hypothetical everyday situation. Then give the plain meaning, 1-3 relevant
constitutional_basis entries, 3-5 explanation steps, one worked hypothetical example, scope and limits,
common confusions, 2-3 checks linked to step IDs, takeaways and related concepts. Define terms immediately.
Keep optional key_terms, deeper_detail, amendment_timeline and case_note short or empty/null unless useful.
An amendment lesson needs its relevant timeline; a case_explainer needs one relevant case_note.
Separate constitutional_text, judgment, amendment and ordinary_law. State provision_type and legal_effect
in plain language. Do not imply that every right, directive principle and duty has the same legal effect.
Preserve important qualifications. Explain who a provision concerns without assuming all refer only to citizens.
Do not promise a legal outcome or give personal litigation advice. Explain the limits of hypothetical examples.
Every legal claim in the basis, steps, example, scope, confusions, history or case must have source_ids
linking to an official source. Prefer legislative.gov.in, sansad.in, sci.gov.in, indiacode.nic.in and official Gazette.
Never invent an Article number, clause, amendment, case name, citation, date, quote or source URL.
For constitutional text use reference 'Article N' when an Article applies; put relevant clause details
in plain_meaning. Use part_or_schedule for other locators. quote_candidate is optional: use empty string
unless confident in a short exact excerpt. The server matches candidates against a fixed official edition;
never provide original_text, text_verification, source_context or verification dates yourself.
Never put purported exact legal quotations in explanation fields. They are clearly labelled paraphrases.
Dates in timeline/case metadata use YYYY-MM-DD or null if unknown. Do not confuse passage, assent,
commencement and judgment dates. An amendment timeline item must explain what changed and why it matters.
Clearly distinguish a proposed amendment from one that has been enacted or brought into force.
Do not call anything 'current' or 'verified today' without an actual legal currency check. Contested
interpretations and historical positions need explicit context. A generated timestamp is not verification.
Diagram types match lesson types: scope_map/roles_map/process_sequence/before_after/case_path.
Use 2-6 nodes with IDs, labels and details; 1-10 named edges with resolving IDs; every node participates.
These are schematic teaching maps, not legal decision engines. Use none with a description when unsuitable.
Supply a short caption and limitations. No SVG, HTML, coordinates, scripts or executable code.
Follow the shared 3-5-image article plan. Keep structured diagrams separate from generated art.
Preserve useful common summary/core_mechanics/learning_takeaways for older readers. Avoid filler.
{_EVIDENCE_INSTRUCTIONS}
"""
