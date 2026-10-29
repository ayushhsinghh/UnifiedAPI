"""Beginner Biology lessons with bounded diagram and evidence contracts."""
from copy import deepcopy
from .schemas import _object, _items, _strings, _TEXT, _SOURCE_IDS_SCHEMA
from .physics import PHYSICS_RESPONSE_SCHEMA, _shape, _nonempty, _unique_ids

LESSON_TYPES = ['process', 'structure_function', 'inheritance', 'adaptation_evolution', 'ecosystem']
DIAGRAM_TYPES = ['sequence', 'structure_map', 'inheritance', 'population_sequence', 'relationship_map', 'none']


def sourced(properties):
    return _object({**properties, 'source_ids': _SOURCE_IDS_SCHEMA})


BIOLOGY_LESSON_SCHEMA = _object({
    'lesson_type': {'type': 'STRING', 'enum': LESSON_TYPES},
    'question': _TEXT, 'learning_goal': _TEXT,
    'context': _object({'organism': _TEXT, 'biological_scale': _TEXT, 'location': _TEXT, 'conditions': _strings()}),
    'big_idea': sourced({'explanation': _TEXT, 'analogy': _TEXT, 'analogy_limit': _TEXT}),
    'key_players': _items(sourced({'id': _TEXT, 'name': _TEXT, 'role': _TEXT})),
    'diagram': sourced({
        'type': {'type': 'STRING', 'enum': DIAGRAM_TYPES},
        'title': _TEXT, 'caption': _TEXT, 'description': _TEXT, 'limitations': _strings(),
        'nodes': _items(_object({'id': _TEXT, 'label': _TEXT, 'detail': _TEXT})),
        'edges': _items(_object({'from_id': _TEXT, 'to_id': _TEXT, 'relationship': _TEXT})),
    }),
    'explanation_steps': _items(sourced({'id': _TEXT, 'title': _TEXT, 'explanation': _TEXT, 'player_ids': _strings()})),
    'worked_example': sourced({'title': _TEXT, 'situation': _TEXT, 'reasoning_steps': _strings(), 'outcome': _TEXT, 'interpretation': _TEXT}),
    'change_scenario': sourced({'question': _TEXT, 'changed_condition': _TEXT, 'expected_effect': _TEXT, 'explanation': _TEXT, 'limitations': _TEXT}),
    'misconceptions': _items(sourced({'belief': _TEXT, 'correction': _TEXT, 'explanation': _TEXT})),
    'evidence_and_limits': _object({
        'evidence': _items(sourced({'observation': _TEXT, 'explanation': _TEXT, 'evidence_type': {'type': 'STRING', 'enum': ['experimental', 'observational', 'comparative', 'model']}})),
        'scope_limits': _strings(), 'uncertainties': _strings(),
    }),
    'key_terms': _items(_object({'term': _TEXT, 'definition': _TEXT})),
    'deeper_detail': _items(sourced({'title': _TEXT, 'explanation': _TEXT})),
    'knowledge_checks': _items(_object({'id': _TEXT, 'question': _TEXT, 'answer': _TEXT, 'explanation': _TEXT, 'related_step_ids': _strings()})),
    'takeaways': _strings(), 'related_concepts': _strings(),
})
# Additive and nullable so the payload can omit an unnecessary extra illustration.
BIOLOGY_LESSON_SCHEMA['properties']['supporting_image'] = deepcopy(PHYSICS_RESPONSE_SCHEMA['properties']['physics_lesson']['properties']['supporting_image'])
BIOLOGY_RESPONSE_SCHEMA = deepcopy(PHYSICS_RESPONSE_SCHEMA)
del BIOLOGY_RESPONSE_SCHEMA['properties']['physics_lesson']
BIOLOGY_RESPONSE_SCHEMA['required'].remove('physics_lesson')
BIOLOGY_RESPONSE_SCHEMA['properties'].update({
    'article_type': {'type': 'STRING', 'enum': ['biology_lesson']},
    'biology_lesson': BIOLOGY_LESSON_SCHEMA,
})
BIOLOGY_RESPONSE_SCHEMA['required'].append('biology_lesson')


def validate_biology_content(fact):
    """Check structure and references; this is not independent scientific review."""
    try:
        if not _shape(fact, BIOLOGY_RESPONSE_SCHEMA):
            return False
        lesson = fact['biology_lesson']
        if not all(_nonempty(fact[k]) for k in ('topic', 'headline_fact', 'summary')) or not all(_nonempty(lesson[k]) for k in ('question', 'learning_goal')):
            return False
        if not all(_nonempty(lesson['context'][k]) for k in ('organism', 'biological_scale', 'location')) or not lesson['context']['conditions']:
            return False
        idea = lesson['big_idea']
        if not _nonempty(idea['explanation']) or (idea['analogy'] and not _nonempty(idea['analogy_limit'])):
            return False
        players, steps, checks = lesson['key_players'], lesson['explanation_steps'], lesson['knowledge_checks']
        if not 2 <= len(players) <= 6 or not _unique_ids(players) or any(not all(_nonempty(p[k]) for k in ('name', 'role')) for p in players):
            return False
        if not 3 <= len(steps) <= 5 or not _unique_ids(steps) or not 2 <= len(checks) <= 3 or not _unique_ids(checks):
            return False
        player_ids, step_ids = {p['id'] for p in players}, {s['id'] for s in steps}
        if any(not all(_nonempty(s[k]) for k in ('title', 'explanation')) or not s['player_ids'] or not set(s['player_ids']) <= player_ids for s in steps):
            return False
        if any(not all(_nonempty(c[k]) for k in ('question', 'answer', 'explanation')) or not c['related_step_ids'] or not set(c['related_step_ids']) <= step_ids for c in checks):
            return False
        example = lesson['worked_example']
        if not all(_nonempty(example[k]) for k in ('title', 'situation', 'outcome', 'interpretation')) or not example['reasoning_steps']:
            return False
        if not all(_nonempty(v) for v in lesson['change_scenario'].values() if isinstance(v, str)):
            return False
        evidence = lesson['evidence_and_limits']
        if not evidence['evidence'] or not evidence['scope_limits'] or not lesson['takeaways']:
            return False
        if any(not all(_nonempty(item[k]) for k in ('observation', 'explanation')) for item in evidence['evidence']):
            return False
        for field, keys in [('misconceptions', ('belief', 'correction', 'explanation')), ('deeper_detail', ('title', 'explanation')), ('key_terms', ('term', 'definition'))]:
            if any(not all(_nonempty(item[k]) for k in keys) for item in lesson[field]):
                return False
        if not lesson['misconceptions']:
            return False
        diagram = lesson['diagram']
        if not _nonempty(diagram['description']):
            return False
        if diagram['type'] != 'none':
            expected = dict(zip(LESSON_TYPES, DIAGRAM_TYPES))[lesson['lesson_type']]
            if diagram['type'] != expected or not 2 <= len(diagram['nodes']) <= 6 or not _unique_ids(diagram['nodes']):
                return False
            if not all(_nonempty(diagram[k]) for k in ('title', 'caption')) or not diagram['limitations']:
                return False
            if any(not all(_nonempty(node[k]) for k in ('label', 'detail')) for node in diagram['nodes']):
                return False
            node_ids = {node['id'] for node in diagram['nodes']}
            edges = diagram['edges']
            if not 1 <= len(edges) <= 10 or any(e['from_id'] not in node_ids or e['to_id'] not in node_ids or e['from_id'] == e['to_id'] or not _nonempty(e['relationship']) for e in edges):
                return False
            if {i for e in edges for i in (e['from_id'], e['to_id'])} != node_ids:
                return False
            if diagram['type'] in ('inheritance', 'population_sequence'):
                levels = dict.fromkeys(node_ids, 0)
                for attempt in range(len(node_ids)):
                    changed = False
                    for edge in edges:
                        if levels[edge['to_id']] <= levels[edge['from_id']]:
                            levels[edge['to_id']] = levels[edge['from_id']] + 1
                            changed = True
                    if not changed:
                        break
                else:
                    return False  # Ancestry and successive generations cannot loop backwards.
        visuals, supporting = fact['visual_suggestions'], lesson.get('supporting_image')
        slots = [k for k in ('overview', 'how_it_works') if _nonempty(visuals[k])]
        if not _nonempty(visuals['cover']):
            return False
        if supporting:
            if not all(_nonempty(supporting[k]) for k in ('learning_purpose', 'caption', 'alt')) or slots != [supporting['slot']]:
                return False
        elif slots:
            return False
        # Empty optional collections are fine; empty items are not.
        string_lists = [lesson['context']['conditions'], example['reasoning_steps'], evidence['scope_limits'], evidence['uncertainties'], lesson['takeaways'], lesson['related_concepts'], diagram['limitations']]
        return all(_nonempty(item) for values in string_lists for item in values)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def build_biology_prompt(blocklist):
    from .prompts import _EVIDENCE_INSTRUCTIONS
    from .constants import CATEGORY_HINTS
    return f"""Create ONE Biology lesson for a curious beginner. Focus on one question, not a syllabus.
Choose from {CATEGORY_HINTS.get('biology', 'living systems')}. Avoid these previous topics: {blocklist!r}.
Return schema_version 2.0 and article_type biology_lesson with the supplied schema.
Choose ONE lesson_type: process, structure_function, inheritance, adaptation_evolution, ecosystem.
Use the question, context, big idea, 2-6 key players, 3-5 connected causal steps, one worked example,
one changed-condition scenario, misconceptions, evidence and limits, 2-3 checks, and takeaways.
Define terms before using them; keep deeper_detail and key_terms optional arrays. Explain the entire
main idea without requiring readers to open deeper detail. State the organism, biological scale,
location and conditions. Do not generalize a finding across species or conditions without support.
Each explanation step names valid player_ids; each check names valid related_step_ids.
Separate evidence observations from explanations. Label evidence experimental/observational/comparative/model.
State uncertainty and scope limits. Never invent experiments, measurements, evidence or citations.
For evolution, distinguish individual responses from population changes across generations.
Do not imply organisms evolve because they want or need a trait. Avoid deterministic claims about genes.
An analogy needs analogy_limit. A changed condition needs its expected effect, causal explanation and limits.
Diagram types match lesson_type respectively: sequence, structure_map, inheritance, population_sequence,
relationship_map. Supply 2-6 nodes with stable IDs, labels and details, plus 1-10 directed edges with
from_id/to_id and a named relationship. Every node must participate. Use none with a useful description
if these schematic maps cannot explain the topic accurately. Never return SVG, HTML, script, coordinates
or executable diagrams. These are conceptual maps, not anatomical drawings, timelines to scale or measured data.
Always request one relevant cover in visual_suggestions.cover. Keep the left third quiet for the title and
the subject inside the central 60% for phone crops. No words, labels, numbers or equations in generated images.
Default overview/how_it_works to empty strings and supporting_image to null. Request at most ONE extra
illustration only when a specific organism, structure or apparatus view adds clear learning value beyond
the cover and structured map. Provide its slot, learning_purpose, caption and alt, and only its matching
visual prompt. Identify generated illustrations as illustrations; never present them as experimental evidence.
Keep common summary/core_mechanics/learning_takeaways and metadata useful to older readers.
History, quotes and India connections are optional. Do not add cultural filler or personal medical advice.
{_EVIDENCE_INSTRUCTIONS}
"""
