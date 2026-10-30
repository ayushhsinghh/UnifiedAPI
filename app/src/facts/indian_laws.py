"""Situation-first learning about Indian Acts and codes, with explicit attribution limits."""
from copy import deepcopy
from datetime import date
from .schemas import _object, _items, _strings, _TEXT
from .physics import PHYSICS_RESPONSE_SCHEMA, _shape, _nonempty, _unique_ids
from .biology import sourced
from .constitution import official_source
from .image_policy import validate_image_plan
from .constants import CATEGORY_HINTS

LESSON_TYPES = ['concept', 'right_or_duty', 'procedure', 'comparison', 'case_explainer']
SOURCE_KINDS = ['statute', 'rule', 'notification', 'judgment', 'commentary']
NULL_DATE = {'type': 'STRING', 'nullable': True}
EXAMPLE = sourced({'title': _TEXT, 'situation': _TEXT, 'reasoning_steps': _strings(), 'implications': _TEXT, 'limits': _TEXT})
LAW_LESSON_SCHEMA = _object({
    'lesson_type': {'type': 'STRING', 'enum': LESSON_TYPES},
    'legal_area': _TEXT, 'question': _TEXT, 'learning_goal': _TEXT,
    'opening_scenario': _object({'title': _TEXT, 'situation': _TEXT, 'question': _TEXT}),
    'plain_rule': sourced({'explanation': _TEXT}),
    'legal_basis': _items(sourced({'id': _TEXT, 'instrument': _TEXT, 'year': {'type': 'INTEGER'},
        'reference': _TEXT, 'title': _TEXT, 'source_kind': {'type': 'STRING', 'enum': SOURCE_KINDS},
        'plain_meaning': _TEXT, 'legal_effect': _TEXT,
        'status': {'type': 'STRING', 'enum': ['current', 'historical', 'proposed', 'uncertain']},
        'commencement_date': NULL_DATE})),
    'applicability': sourced({'jurisdiction': _TEXT, 'who_it_concerns': _strings(), 'relevant_dates': _TEXT,
        'conditions': _strings(), 'exceptions': _strings(), 'limits': _strings()}),
    'key_terms': _items(_object({'term': _TEXT, 'definition': _TEXT})),
    'explanation_steps': _items(sourced({'id': _TEXT, 'title': _TEXT, 'explanation': _TEXT, 'basis_ids': _strings()})),
    'worked_example': EXAMPLE, 'contrast_example': {**deepcopy(EXAMPLE), 'nullable': True},
    'common_confusions': _items(sourced({'confusion': _TEXT, 'clarification': _TEXT})),
    'case_note': {**sourced({'name': _TEXT, 'court': _TEXT, 'citation': _TEXT, 'decision_date': NULL_DATE,
        'question': _TEXT, 'decision': _TEXT, 'significance': _TEXT, 'limits': _TEXT}), 'nullable': True},
    'law_changes': _items(sourced({'label': _TEXT, 'date': NULL_DATE,
        'status': {'type': 'STRING', 'enum': ['enacted', 'commenced', 'proposed', 'historical', 'uncertain']},
        'change': _TEXT, 'significance': _TEXT})),
    'commentary': _items(sourced({'title': _TEXT, 'explanation': _TEXT, 'limits': _TEXT})),
    'deeper_detail': _items(sourced({'title': _TEXT, 'explanation': _TEXT})),
    'knowledge_checks': _items(_object({'id': _TEXT, 'question': _TEXT, 'answer': _TEXT, 'explanation': _TEXT, 'related_step_ids': _strings()})),
    'takeaways': _strings(), 'related_concepts': _strings(),
})
INDIAN_LAWS_RESPONSE_SCHEMA = deepcopy(PHYSICS_RESPONSE_SCHEMA)
del INDIAN_LAWS_RESPONSE_SCHEMA['properties']['physics_lesson']
INDIAN_LAWS_RESPONSE_SCHEMA['required'].remove('physics_lesson')
INDIAN_LAWS_RESPONSE_SCHEMA['properties'].update({
    'article_type': {'type': 'STRING', 'enum': ['indian_law_lesson']}, 'indian_law_lesson': LAW_LESSON_SCHEMA})
INDIAN_LAWS_RESPONSE_SCHEMA['required'].append('indian_law_lesson')


def validate_indian_laws_content(fact):
    """Validate structure and source attribution, never legal accuracy or currency."""
    try:
        if not _shape(fact, INDIAN_LAWS_RESPONSE_SCHEMA) or not validate_image_plan(fact):
            return False
        lesson = fact['indian_law_lesson']
        if not all(_nonempty(fact[k]) for k in ('topic', 'headline_fact', 'summary')):
            return False
        if not all(_nonempty(lesson[k]) for k in ('legal_area', 'question', 'learning_goal')):
            return False
        if not all(_nonempty(v) for v in lesson['opening_scenario'].values()):
            return False
        sources = fact['sources']
        if not _unique_ids(sources):
            return False
        source_map = {s['id']: s for s in sources}
        def linked(item, primary=True):
            ids = item['source_ids']
            return bool(ids) and set(ids) <= source_map.keys() and (not primary or any(official_source(source_map[i]['url']) for i in ids))
        def filled(item, keys):
            return all(_nonempty(item[k]) for k in keys)
        bases, steps = lesson['legal_basis'], lesson['explanation_steps']
        if not 1 <= len(bases) <= 4 or not _unique_ids(bases) or not any(b['source_kind'] == 'statute' for b in bases):
            return False
        for basis in bases:
            if not filled(basis, ('instrument', 'reference', 'title', 'plain_meaning', 'legal_effect')) or not 1800 <= basis['year'] <= date.today().year + 1:
                return False
            if not linked(basis, basis['source_kind'] != 'commentary'):
                return False
        if not filled(lesson['plain_rule'], ('explanation',)) or not linked(lesson['plain_rule']):
            return False
        if len(lesson['key_terms']) > 8 or any(not filled(term, ('term', 'definition')) for term in lesson['key_terms']):
            return False
        scope = lesson['applicability']
        if not filled(scope, ('jurisdiction', 'relevant_dates')) or not linked(scope) or any(not scope[k] for k in ('who_it_concerns', 'conditions', 'limits')):
            return False
        if not 2 <= len(steps) <= 5 or not _unique_ids(steps):
            return False
        basis_ids = {b['id'] for b in bases if b['source_kind'] != 'commentary'}
        for step in steps:
            if not filled(step, ('title', 'explanation')) or not linked(step) or not step['basis_ids'] or not set(step['basis_ids']) <= basis_ids:
                return False
        for example in (lesson['worked_example'], lesson['contrast_example']):
            if example is not None and (not filled(example, ('title', 'situation', 'implications', 'limits')) or not example['reasoning_steps'] or not linked(example)):
                return False
        if not 1 <= len(lesson['common_confusions']) <= 3 or any(not filled(x, ('confusion', 'clarification')) or not linked(x) for x in lesson['common_confusions']):
            return False
        checks = lesson['knowledge_checks']
        if not 1 <= len(checks) <= 3 or not _unique_ids(checks):
            return False
        if any(not filled(c, ('question', 'answer', 'explanation')) or not c['related_step_ids'] or not set(c['related_step_ids']) <= {s['id'] for s in steps} for c in checks):
            return False
        case = lesson['case_note']
        if lesson['lesson_type'] == 'case_explainer' and not case:
            return False
        if lesson['lesson_type'] == 'comparison' and not lesson['contrast_example']:
            return False
        if case and (not filled(case, ('name', 'court', 'citation', 'question', 'decision', 'significance', 'limits')) or not linked(case)):
            return False
        for field, keys in [('law_changes', ('label', 'change', 'significance')), ('commentary', ('title', 'explanation', 'limits')), ('deeper_detail', ('title', 'explanation'))]:
            if len(lesson[field]) > 4 or any(not filled(x, keys) or not linked(x, field != 'commentary') for x in lesson[field]):
                return False
        def valid_tree(value):
            if isinstance(value, dict):
                if 'source_ids' in value and not linked(value, False):
                    return False
                for key, child in value.items():
                    if key in ('date', 'decision_date', 'commencement_date') and child is not None:
                        if not isinstance(child, str) or date.fromisoformat(child).isoformat() != child:
                            return False
                    if not valid_tree(child):
                        return False
            elif isinstance(value, list):
                return all(valid_tree(child) for child in value) and all(not isinstance(child, str) or bool(child.strip()) for child in value)
            return True
        return 2 <= len(lesson['takeaways']) <= 4 and valid_tree(lesson)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def build_indian_laws_prompt(blocklist):
    from .prompts import _EVIDENCE_INSTRUCTIONS
    return f"""Teach ONE useful Indian law concept to a non-expert using an everyday situation.
Category indian_laws; schema_version 2.0; article_type indian_law_lesson.
Choose easy-to-medium topics across: {CATEGORY_HINTS.get('indian_laws', '')}.
Avoid these previous topics: {', '.join(blocklist) or 'None'}.
Do not make this a constitutional lesson, exam syllabus, personalized legal advice or litigation strategy.
Use lesson_type concept, right_or_duty, procedure, comparison or case_explainer.
Flow: hypothetical situation, plain rule, applicability, 2-5 explanation steps, worked example,
optional contrast, common confusions, optional deeper context, 1-3 checks, 2-4 takeaways.
Explain terms at first use. Each article teaches one idea in 3-6 minutes.
Use Acts and codes as primary authority; commentary only adds context and cannot override law or judgments.
legal_basis contains 1-4 accurately named instruments with year and precise section/rule locators.
Separate statute, rule, notification, judgment and commentary. Include at least one statute.
Every legal claim and interpretation needs resolving source_ids, including an official primary reference.
Commentary requires real named sources and source_ids; leave it empty instead of inventing books or authors.
Use India Code, legislative.gov.in, official Gazette or sci.gov.in for primary references.
Explain jurisdiction, relevant dates, who is covered, conditions, exceptions and limits explicitly.
State-specific, personal-law and historical differences must not be presented as universal rules.
Distinguish passage, assent, commencement, amendments, judicial interpretation and proposals.
Never assume old IPC/CrPC/Evidence Act provisions apply to every date. Explain transitional context when relevant.
Dates are YYYY-MM-DD or null if unknown. status is an attributed description, not a currency check.
Never invent sections, cases, citations, dates, URLs or exact quotations. All explanations are paraphrases.
Do not supply verification timestamps, retrieval records or indian_laws_validation: the server owns them.
Use conditional implications and explicit limits in examples; never guarantee a court outcome.
comparison needs contrast_example; case_explainer needs a genuine case_note with court and citation.
Optional law_changes, case_note, commentary and deeper_detail stay empty/null when not useful.
Preserve the common summary, core_mechanics and learning_takeaways for older readers.
No numbered-circle diagrams, SVG, HTML or generated code. Use purposeful explanatory images instead.
Follow the shared 3-5-image plan: cover, overview/card summary, how_it_works and up to two useful extras.
Illustrations are hypothetical scenes, not authentic documents, judgments, evidence or official endorsements.
{_EVIDENCE_INSTRUCTIONS}
"""
