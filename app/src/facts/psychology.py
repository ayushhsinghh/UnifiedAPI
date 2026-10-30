"""Experience-first Psychology lessons with explicit evidence and scope limits."""
from copy import deepcopy
from .schemas import _object, _items, _strings, _TEXT
from .physics import PHYSICS_RESPONSE_SCHEMA, _shape, _nonempty, _unique_ids
from .biology import sourced

LESSON_TYPES = ['cognitive_process', 'learning_behavior', 'social_influence', 'research_finding']
DIAGRAM_TYPES = ['process_map', 'feedback_loop', 'situation_comparison', 'study_design']
NUMBER_OR_NULL = {'type': 'NUMBER', 'nullable': True}
diagram = _object({
    'type': {'type': 'STRING', 'enum': [*DIAGRAM_TYPES, 'none']},
    'title': _TEXT, 'caption': _TEXT, 'description': _TEXT, 'limitations': _strings(),
    'nodes': _items(_object({'id': _TEXT, 'label': _TEXT, 'detail': _TEXT})),
    'edges': _items(_object({'from_id': _TEXT, 'to_id': _TEXT, 'relationship': _TEXT,
                           'relationship_type': {'type': 'STRING', 'enum': ['procedure', 'association', 'causal', 'conceptual']}})),
})
PSYCHOLOGY_LESSON_SCHEMA = _object({
    'lesson_type': {'type': 'STRING', 'enum': LESSON_TYPES},
    'question': _TEXT, 'learning_goal': _TEXT,
    'opening_scenario': _object({'title': _TEXT, 'situation': _TEXT, 'question': _TEXT,
        'prediction': {**_object({'prompt': _TEXT, 'reveal': _TEXT, 'explanation': _TEXT}), 'nullable': True}}),
    'big_idea': sourced({'name': _TEXT, 'explanation': _TEXT}),
    'explanation_steps': _items(sourced({'id': _TEXT, 'title': _TEXT, 'explanation': _TEXT})),
    'diagram': sourced(diagram['properties']),
    'worked_example': sourced({'title': _TEXT, 'situation': _TEXT, 'reasoning_steps': _strings(), 'outcome': _TEXT, 'interpretation': _TEXT}),
    'alternative_explanations': _items(sourced({'title': _TEXT, 'explanation': _TEXT, 'how_to_distinguish': _TEXT})),
    'evidence': _items(sourced({
        'title': _TEXT, 'finding': _TEXT, 'interpretation': _TEXT,
        'research_design': {'type': 'STRING', 'enum': ['randomized_experiment', 'nonrandomized_experiment', 'observational', 'review', 'meta_analysis']},
        'inference': {'type': 'STRING', 'enum': ['association', 'causal', 'descriptive']},
        'causal_justification': _TEXT,
        'study_notes': _object({'authors': _TEXT, 'year': NUMBER_OR_NULL, 'sample_size': NUMBER_OR_NULL,
                                'participants': _TEXT, 'setting': _TEXT, 'method': _TEXT, 'limitations': _strings()}),
        'statistics': _items(sourced({'label': _TEXT, 'value': NUMBER_OR_NULL, 'unit': _TEXT, 'interpretation': _TEXT})),
    })),
    'replication': sourced({'status': {'type': 'STRING', 'enum': ['consistent', 'mixed', 'limited', 'not_assessed']}, 'summary': _TEXT}),
    'boundary_conditions': _object({'populations': _strings(), 'contexts': _strings(), 'limitations': _strings(), 'uncertainties': _strings()}),
    'practical_application': _items(sourced({'suggestion': _TEXT, 'reasoning': _TEXT, 'limitations': _TEXT})),
    'key_terms': _items(_object({'term': _TEXT, 'definition': _TEXT})),
    'deeper_detail': _items(sourced({'title': _TEXT, 'explanation': _TEXT})),
    'knowledge_checks': _items(_object({'id': _TEXT, 'question': _TEXT, 'answer': _TEXT, 'explanation': _TEXT, 'related_step_ids': _strings()})),
    'takeaways': _strings(), 'related_concepts': _strings(),
})
PSYCHOLOGY_LESSON_SCHEMA['properties']['supporting_image'] = deepcopy(PHYSICS_RESPONSE_SCHEMA['properties']['physics_lesson']['properties']['supporting_image'])
PSYCHOLOGY_RESPONSE_SCHEMA = deepcopy(PHYSICS_RESPONSE_SCHEMA)
del PSYCHOLOGY_RESPONSE_SCHEMA['properties']['physics_lesson']
PSYCHOLOGY_RESPONSE_SCHEMA['required'].remove('physics_lesson')
PSYCHOLOGY_RESPONSE_SCHEMA['properties'].update({'article_type': {'type': 'STRING', 'enum': ['psychology_lesson']}, 'psychology_lesson': PSYCHOLOGY_LESSON_SCHEMA})
PSYCHOLOGY_RESPONSE_SCHEMA['required'].append('psychology_lesson')


def validate_psychology_content(fact):
    """Validate structure and attribution, never claim independent evidence verification."""
    try:
        if not _shape(fact, PSYCHOLOGY_RESPONSE_SCHEMA):
            return False
        lesson = fact['psychology_lesson']
        if not all(_nonempty(fact[k]) for k in ('topic', 'headline_fact', 'summary')) or not all(_nonempty(lesson[k]) for k in ('question', 'learning_goal')):
            return False
        for obj, keys in [(lesson['opening_scenario'], ('title', 'situation', 'question')), (lesson['big_idea'], ('name', 'explanation')),
                          (lesson['worked_example'], ('title', 'situation', 'outcome', 'interpretation'))]:
            if not all(_nonempty(obj[k]) for k in keys):
                return False
        prediction = lesson['opening_scenario']['prediction']
        if prediction and not all(_nonempty(value) for value in prediction.values()):
            return False
        steps, checks = lesson['explanation_steps'], lesson['knowledge_checks']
        if not 3 <= len(steps) <= 5 or not _unique_ids(steps) or not 2 <= len(checks) <= 3 or not _unique_ids(checks):
            return False
        if any(not all(_nonempty(s[k]) for k in ('title', 'explanation')) for s in steps):
            return False
        ids = {s['id'] for s in steps}
        if any(not all(_nonempty(c[k]) for k in ('question', 'answer', 'explanation')) or not c['related_step_ids'] or not set(c['related_step_ids']) <= ids for c in checks):
            return False
        known_sources = {s['id'] for s in fact.get('sources', [])}
        evidence = lesson['evidence']
        if not 1 <= len(evidence) <= 4:
            return False
        for item in evidence:
            if not all(_nonempty(item[k]) for k in ('title', 'finding', 'interpretation')) or not item['source_ids'] or not set(item['source_ids']) <= known_sources:
                return False
            notes = item['study_notes']
            if not all(_nonempty(notes[k]) for k in ('participants', 'setting', 'method')) or not notes['limitations']:
                return False
            for key in ('year', 'sample_size'):
                value = notes[key]
                if value is not None and (value != int(value) or value <= 0 or (key == 'year' and not 1600 <= value <= 2100)):
                    return False
            if item['inference'] == 'causal' and (item['research_design'] == 'observational' or not _nonempty(item['causal_justification'])):
                return False
            if item['inference'] != 'causal' and item['causal_justification'].strip():
                return False
            for stat in item['statistics']:
                if not all(_nonempty(stat[k]) for k in ('label', 'interpretation')) or (stat['value'] is not None and (not stat['source_ids'] or not set(stat['source_ids']) <= known_sources)):
                    return False
        replication = lesson['replication']
        if not _nonempty(replication['summary']) or (replication['status'] != 'not_assessed' and (not replication['source_ids'] or not set(replication['source_ids']) <= known_sources)):
            return False
        boundary = lesson['boundary_conditions']
        if any(not boundary[key] for key in ('populations', 'contexts', 'limitations')):
            return False
        collections = [('alternative_explanations', ('title', 'explanation', 'how_to_distinguish')), ('practical_application', ('suggestion', 'reasoning', 'limitations')),
                       ('key_terms', ('term', 'definition')), ('deeper_detail', ('title', 'explanation'))]
        if not 1 <= len(lesson['alternative_explanations']) <= 3 or not 1 <= len(lesson['practical_application']) <= 3:
            return False
        for field, keys in collections:
            if any(not all(_nonempty(item[k]) for k in keys) for item in lesson[field]):
                return False
        d = lesson['diagram']
        if not _nonempty(d['description']):
            return False
        if d['type'] != 'none':
            if d['type'] != dict(zip(LESSON_TYPES, DIAGRAM_TYPES))[lesson['lesson_type']] or not 2 <= len(d['nodes']) <= 6 or not _unique_ids(d['nodes']):
                return False
            if not all(_nonempty(d[k]) for k in ('title', 'caption')) or not d['limitations'] or any(not all(_nonempty(n[k]) for k in ('label', 'detail')) for n in d['nodes']):
                return False
            nodes = {n['id'] for n in d['nodes']}
            if not 1 <= len(d['edges']) <= 10 or any(e['from_id'] not in nodes or e['to_id'] not in nodes or e['from_id'] == e['to_id'] or not _nonempty(e['relationship']) for e in d['edges']):
                return False
            if {i for e in d['edges'] for i in (e['from_id'], e['to_id'])} != nodes:
                return False
            if any(e['relationship_type'] == 'causal' for e in d['edges']) and not any(e['inference'] == 'causal' for e in evidence):
                return False
        visuals, supporting = fact['visual_suggestions'], lesson.get('supporting_image')
        slots = [k for k in ('overview', 'how_it_works') if _nonempty(visuals[k])]
        if not _nonempty(visuals['cover']):
            return False
        if supporting:
            if not all(_nonempty(supporting[k]) for k in ('learning_purpose', 'caption', 'alt')) or slots != [supporting['slot']]:
                return False
        elif slots:
            return False
        strings = [lesson['takeaways'], lesson['related_concepts'], lesson['worked_example']['reasoning_steps'], d['limitations'], *boundary.values(),
                   *[item['study_notes']['limitations'] for item in evidence]]
        return bool(lesson['takeaways'] and lesson['worked_example']['reasoning_steps']) and all(_nonempty(v) for values in strings for v in values)
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return False


def build_psychology_prompt(blocklist):
    from .prompts import _EVIDENCE_INSTRUCTIONS
    from .constants import CATEGORY_HINTS
    return f"""Create ONE experience-first, evidence-led Psychology lesson for a curious beginner.
Choose from {CATEGORY_HINTS.get('psychology', 'thinking and behavior')}. Avoid prior topics: {blocklist!r}.
Return schema_version 2.0, article_type psychology_lesson, and the structured schema.
Choose lesson_type cognitive_process, learning_behavior, social_influence, or research_finding.
Start with a short everyday opening_scenario, explicitly illustrative rather than a reported experiment.
An optional prediction is a thought exercise with a reveal and explanation, never a diagnostic test,
personality score, or proof that this reader has a bias. Use null when it adds little.
Then explain the named big_idea, 3-5 causal/interpretive steps, one worked example, evidence,
alternative explanations, boundary conditions, modest practical applications, 2-3 checks and takeaways.
Keep the complete main explanation accessible without deeper_detail; key_terms and deeper_detail may be empty.
Never assume a personal trait or say 'your brain tricks you'. Do not diagnose or give treatment advice.
Separate each finding from its interpretation. Distinguish association from causation.
Evidence entries identify research_design, inference, study_notes and source_ids. Use null for unknown
sample_size/year/statistic values; never invent statistics, participants, methods or study results.
Unknown participants/setting/method details should be stated as not reported, not fabricated.
For a causal inference give causal_justification tied to the design; observational evidence cannot prove causation.
Replication status is consistent/mixed/limited/not_assessed, with a source-linked summary. Default to
not_assessed unless the cited material actually addresses replication. Do not invent certainty badges,
confidence percentages or 'scientifically proven' claims. Represent conflicting findings and scope limits.
Include population, context, cultural and measurement limits when relevant. Do not treat one study as universal.
Diagram types match lesson types: process_map, feedback_loop, situation_comparison, study_design.
Use 2-6 nodes and 1-10 connections with valid IDs and relationship_type procedure/association/
causal/conceptual. Association uses an undirected dashed connection in the UI. Do not imply causation
through arrows unless causal evidence and a justification support it. Every node participates.
No SVG, HTML, coordinates, code, invented data or fabricated brain imagery. Use none and a useful text
description if the fixed conceptual diagram cannot explain the topic. Include caption and limitations.
Request one relevant editorial cover in visual_suggestions.cover, with a quiet left third for the title,
subject inside the central 60%, and no text or labels. Default overview/how_it_works to empty strings,
supporting_image to null. At most ONE extra illustration may explain a distinct concrete situation
or study setup; provide slot, learning_purpose, caption and alt. Never depict generated art as research evidence.
Keep common summary/core_mechanics/learning_takeaways useful to legacy readers; history and cultural filler optional.
{_EVIDENCE_INSTRUCTIONS}
"""
