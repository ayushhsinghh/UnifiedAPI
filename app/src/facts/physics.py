"""Physics lesson contract and bounded, non-executable numerical checks."""
import math
import re
from copy import deepcopy
from .image_policy import validate_image_plan

from .schemas import FACT_RESPONSE_SCHEMA, _object, _items, _strings, _TEXT, _SOURCE_IDS_SCHEMA


def text_item(properties):
    return _object({**properties, 'source_ids': _SOURCE_IDS_SCHEMA})


NUMBER = {'type': 'NUMBER'}
QUANTITY = _object({'id': _TEXT, 'symbol': _TEXT, 'meaning': _TEXT, 'value': NUMBER, 'unit': _TEXT})
CALCULATION = _object({
    'id': _TEXT, 'explanation': _TEXT,
    'operation': {'type': 'STRING', 'enum': ['add', 'subtract', 'multiply', 'divide', 'sqrt', 'square']},
    'operand_ids': _strings(), 'result': NUMBER, 'unit': _TEXT,
})
DIAGRAM = text_item({
    'type': {'type': 'STRING', 'enum': ['comparison', 'force', 'ray', 'energy_flow', 'graph', 'none']},
    'title': _TEXT, 'caption': _TEXT, 'description': _TEXT, 'assumptions': _strings(),
    'items': _items(_object({'label': _TEXT, 'detail': _TEXT})),
    'vectors': _items(_object({'label': _TEXT, 'x': NUMBER, 'y': NUMBER})),
    'rays': _items(_object({'label': _TEXT, 'x1': NUMBER, 'y1': NUMBER, 'x2': NUMBER, 'y2': NUMBER})),
    'x_label': _TEXT, 'x_unit': _TEXT, 'y_label': _TEXT, 'y_unit': _TEXT,
    'points': _items(_object({'x': NUMBER, 'y': NUMBER})),
})
PHYSICS_LESSON_SCHEMA = _object({
    'question': _TEXT, 'learning_goal': _TEXT,
    'prerequisites': _items(_object({'term': _TEXT, 'explanation': _TEXT})),
    'key_terms': _items(_object({'term': _TEXT, 'definition': _TEXT, 'relevance': _TEXT})),
    'intuition': text_item({'explanation': _TEXT, 'analogy': _TEXT, 'analogy_limit': _TEXT}),
    'diagram': DIAGRAM,
    'explanation_steps': _items(text_item({'id': _TEXT, 'title': _TEXT, 'explanation': _TEXT})),
    'worked_example': text_item({
        'question': _TEXT, 'starting_conditions': _strings(), 'reasoning_steps': _strings(),
        'givens': _items(QUANTITY), 'calculations': _items(CALCULATION),
        'result': _TEXT, 'interpretation': _TEXT,
    }),
    'mathematics': _items(text_item({
        'title': _TEXT, 'formula_latex': _TEXT, 'spoken_formula': _TEXT, 'meaning': _TEXT,
        'symbols': _items(_object({'id': _TEXT, 'symbol': _TEXT, 'meaning': _TEXT, 'unit': _TEXT})),
        'symbol_ids': _strings(), 'assumptions': _strings(), 'derivation_steps': _strings(),
    })),
    'misconceptions': _items(text_item({'belief': _TEXT, 'correction': _TEXT, 'explanation': _TEXT})),
    'applications': _items(text_item({'title': _TEXT, 'explanation': _TEXT})),
    'model_limits': _strings(),
    'knowledge_checks': _items(_object({
        'id': _TEXT, 'question': _TEXT, 'answer': _TEXT, 'explanation': _TEXT,
        'misconception': _TEXT, 'related_step_ids': _strings(),
    })),
    'takeaways': _strings(), 'related_concepts': _strings(),
})
PHYSICS_LESSON_SCHEMA['properties']['supporting_image'] = {
    **_object({
        'slot': {'type': 'STRING', 'enum': ['overview', 'how_it_works']},
        'learning_purpose': _TEXT, 'caption': _TEXT, 'alt': _TEXT,
    }),
    'nullable': True,
}

PHYSICS_RESPONSE_SCHEMA = deepcopy(FACT_RESPONSE_SCHEMA)
# Old clients keep the summary, mechanics, takeaways, metadata and references.
# Do not force historical or cultural filler into a physics explanation.
for field in ('history', 'impact_on_india', 'cultural_significance', 'key_year', 'key_figure',
              'key_stat', 'quote', 'global_comparison', 'timeline'):
    PHYSICS_RESPONSE_SCHEMA['required'].remove(field)
PHYSICS_RESPONSE_SCHEMA['properties'].update({
    'schema_version': {'type': 'STRING', 'enum': ['2.0']},
    'article_type': {'type': 'STRING', 'enum': ['physics_lesson']},
    'physics_lesson': PHYSICS_LESSON_SCHEMA,
})
PHYSICS_RESPONSE_SCHEMA['required'] += ['schema_version', 'article_type', 'physics_lesson']

# Dimensions are (mass, length, time, current, temperature, amount, luminosity).
ZERO = (0,) * 7
UNITS = {
    '1': ZERO, 'rad': ZERO, 'kg': (1, 0, 0, 0, 0, 0, 0), 'm': (0, 1, 0, 0, 0, 0, 0),
    's': (0, 0, 1, 0, 0, 0, 0), 'A': (0, 0, 0, 1, 0, 0, 0), 'K': (0, 0, 0, 0, 1, 0, 0),
    'mol': (0, 0, 0, 0, 0, 1, 0), 'cd': (0, 0, 0, 0, 0, 0, 1),
    'N': (1, 1, -2, 0, 0, 0, 0), 'J': (1, 2, -2, 0, 0, 0, 0),
    'W': (1, 2, -3, 0, 0, 0, 0), 'Hz': (0, 0, -1, 0, 0, 0, 0),
    'Pa': (1, -1, -2, 0, 0, 0, 0), 'C': (0, 0, 1, 1, 0, 0, 0),
    'V': (1, 2, -3, -1, 0, 0, 0), 'ohm': (1, 2, -3, -2, 0, 0, 0),
}


def unit_dimensions(unit):
    """Parse SI products such as kg*m/s^2. No expressions or unit conversions."""
    if not isinstance(unit, str) or len(unit) > 80:
        raise ValueError('Invalid unit')
    parts = unit.split('/')
    if len(parts) > 2:
        raise ValueError('Use a single division and SI base/derived units')
    result = list(ZERO)
    for side, product in enumerate(parts):
        for token in product.split('*'):
            match = re.fullmatch(r'(1|[A-Za-z]+)(?:\^(-?[0-9]{1,2}))?', token)
            if not match or match[1] not in UNITS:
                raise ValueError('Unsupported SI unit')
            exponent = int(match[2] or 1) * (-1 if side else 1)
            result = [a + exponent * b for a, b in zip(result, UNITS[match[1]])]
    return tuple(result)


def _shape(value, schema):
    if value is None and schema.get('nullable'):
        return True
    kind = schema['type']
    if kind == 'OBJECT':
        return (isinstance(value, dict) and all(k in value for k in schema.get('required', []))
                and all(_shape(value[k], v) for k, v in schema['properties'].items() if k in value))
    if kind == 'ARRAY':
        return isinstance(value, list) and len(value) <= 100 and all(_shape(v, schema['items']) for v in value)
    if kind == 'NUMBER':
        return type(value) in (int, float) and math.isfinite(value)
    if kind == 'INTEGER':
        return type(value) is int
    return isinstance(value, str) and len(value) <= 12000 and value in schema.get('enum', [value])


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _unique_ids(items):
    ids = [item['id'] for item in items]
    return all(_nonempty(i) for i in ids) and len(ids) == len(set(ids))


def _check_calculations(example):
    values = {}
    for item in example['givens']:
        if not _nonempty(item['id']) or item['id'] in values or not all(_nonempty(item[k]) for k in ('symbol', 'meaning')):
            return False
        values[item['id']] = (item['value'], unit_dimensions(item['unit']))
    for calc in example['calculations']:
        if not _nonempty(calc['id']) or calc['id'] in values or not _nonempty(calc['explanation']):
            return False
        operands = [values[key] for key in calc['operand_ids']]
        operation = calc['operation']
        unary = operation in ('sqrt', 'square')
        if len(operands) != (1 if unary else 2):
            return False
        a, dims = operands[0]
        if unary:
            expected = math.sqrt(a) if operation == 'sqrt' else a * a
            dimensions = tuple(d / 2 if operation == 'sqrt' else d * 2 for d in dims)
        else:
            b, other = operands[1]
            if operation in ('add', 'subtract'):
                if dims != other:
                    return False
                expected = a + b if operation == 'add' else a - b
                dimensions = dims
            else:
                expected = a * b if operation == 'multiply' else a / b
                sign = 1 if operation == 'multiply' else -1
                dimensions = tuple(d + sign * e for d, e in zip(dims, other))
        if not math.isfinite(expected) or not math.isclose(expected, calc['result'], rel_tol=0.005, abs_tol=1e-10):
            return False
        if dimensions != unit_dimensions(calc['unit']):
            return False
        values[calc['id']] = (calc['result'], dimensions)
    return not example['calculations'] or bool(example['givens'])


def validate_physics_content(fact):
    """Validate structure and numerical consistency, not scientific truth or citations."""
    try:
        if fact.get('article_type') != 'physics_lesson' or fact.get('schema_version') != '2.0':
            return False
        lesson = fact.get('physics_lesson')
        if not _shape(fact, PHYSICS_RESPONSE_SCHEMA):
            return False
        if not all(_nonempty(fact.get(k)) for k in ('topic', 'headline_fact', 'summary')):
            return False
        if not all(_nonempty(lesson[k]) for k in ('question', 'learning_goal')):
            return False
        if not validate_image_plan(fact):
            return False
        if not _nonempty(lesson['intuition']['explanation']):
            return False
        if lesson['intuition']['analogy'] and not _nonempty(lesson['intuition']['analogy_limit']):
            return False
        steps, checks = lesson['explanation_steps'], lesson['knowledge_checks']
        if not 3 <= len(steps) <= 5 or not _unique_ids(steps) or not 2 <= len(checks) <= 3 or not _unique_ids(checks):
            return False
        if any(not all(_nonempty(s[k]) for k in ('title', 'explanation')) for s in steps):
            return False
        ids = {s['id'] for s in steps}
        if any(not all(_nonempty(c[k]) for k in ('question', 'answer', 'explanation'))
               or not c['related_step_ids'] or not set(c['related_step_ids']) <= ids for c in checks):
            return False
        if not lesson['takeaways'] or not lesson['model_limits'] or any(not _nonempty(t) for t in lesson['takeaways'] + lesson['model_limits']):
            return False
        example = lesson['worked_example']
        if not all(_nonempty(example[k]) for k in ('question', 'result', 'interpretation')) or not example['reasoning_steps']:
            return False
        if not _check_calculations(example):
            return False
        for equation in lesson['mathematics']:
            if not all(_nonempty(equation[k]) for k in ('title', 'formula_latex', 'spoken_formula', 'meaning')) or not equation['assumptions']:
                return False
            if not _unique_ids(equation['symbols']) or not equation['symbol_ids'] or set(equation['symbol_ids']) != {s['id'] for s in equation['symbols']}:
                return False
            for symbol in equation['symbols']:
                if not _nonempty(symbol['symbol']) or not _nonempty(symbol['meaning']):
                    return False
                unit_dimensions(symbol['unit'])
        diagram = lesson['diagram']
        if not _nonempty(diagram['description']):
            return False
        if diagram['type'] != 'none' and (not all(_nonempty(diagram[k]) for k in ('title', 'caption')) or not diagram['assumptions']):
            return False
        if diagram['type'] in ('comparison', 'energy_flow') and not 2 <= len(diagram['items']) <= 4:
            return False
        if any(not _nonempty(item['label']) or not _nonempty(item['detail']) for item in diagram['items']):
            return False
        if diagram['type'] == 'force' and (not 1 <= len(diagram['vectors']) <= 4 or any(not -1 <= v[k] <= 1 for v in diagram['vectors'] for k in ('x', 'y'))):
            return False
        if diagram['type'] == 'ray' and (not 1 <= len(diagram['rays']) <= 4 or any(not 0 <= v[k] <= 1 for v in diagram['rays'] for k in ('x1', 'y1', 'x2', 'y2'))):
            return False
        if any(not _nonempty(v['label']) or (v['x'] == 0 and v['y'] == 0) for v in diagram['vectors']):
            return False
        if any(not _nonempty(v['label']) or (v['x1'] == v['x2'] and v['y1'] == v['y2']) for v in diagram['rays']):
            return False
        if diagram['type'] == 'graph':
            if not 2 <= len(diagram['points']) <= 20 or not _nonempty(diagram['x_label']) or not _nonempty(diagram['y_label']):
                return False
            unit_dimensions(diagram['x_unit'])
            unit_dimensions(diagram['y_unit'])
            if any(a['x'] >= b['x'] for a, b in zip(diagram['points'], diagram['points'][1:])):
                return False
        return True
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        return False


def build_physics_prompt(blocklist):
    # Do not inherit the general prompt's mandatory India-first/history requirements.
    from .prompts import _EVIDENCE_INSTRUCTIONS
    from .constants import CATEGORY_HINTS
    return f"""Create ONE self-contained Physics lesson for a curious beginner, not an exam syllabus.
Choose a focused question from: {CATEGORY_HINTS.get('physics', 'everyday physics')}.
Do not repeat these previous topics: {blocklist!r}.
Return schema_version 2.0, article_type physics_lesson and the supplied structured schema.
The plain-language route must make sense without opening mathematics. Define unfamiliar terms.
Follow the shared 3-5-image article plan. Keep structured diagrams separate from generated art.
Use 3-5 connected cause-and-effect explanation_steps, ONE worked example, 2-3 knowledge_checks
and concise takeaways. Checks must be answerable from the lesson and related_step_ids must resolve.
Explain each application's mechanism, not just its name. Pair misconceptions with reasoned corrections.
Every analogy must state its limitations. State approximations and model_limits visibly.
Keep history, quotes, timelines and cultural connections optional. Use Indian examples only when useful.
Supply a static diagram when helpful: comparison (2-4 labeled items), force (1-4 vectors x/y in [-1,1]),
ray (1-4 straight directed rays with x1/y1/x2/y2 in [0,1]), energy_flow (2-4 items), or graph
(2-20 finite points and named/unit-labeled axes). Positive y points UP. These are explanatory schematics,
not executable code. No HTML, SVG, scripts, external URLs or animated instructions in diagram data.
For an unsupported diagram use type none, explain the reason in description, and leave other fields empty.
For all diagrams leave unused arrays empty and unused labels empty. Include caption, description and assumptions.
Math is optional: use an empty array when unnecessary. Each equation needs formula_latex, a spoken_formula,
plain meaning, ALL symbols with units, matching symbol_ids, assumptions and optional derivation_steps.
Use canonical SI units in calculations and symbols: 1, rad, kg, m, s, A, K, mol, cd, N, J, W, Hz, Pa,
C, V, ohm, or products/division such as m/s^2 or kg*m^2/s^2. No prefixes: convert givens to SI first.
For a numerical example provide givens with IDs and a sequence of calculations referencing only prior IDs.
Use only add/subtract/multiply/divide (two operands), sqrt/square (one operand). Each operation needs
an explanation, result, and compatible SI unit. Arithmetic is checked to 0.5% relative tolerance.
For a qualitative example use empty givens and calculations, but still provide reasoned steps and a result.
Never invent measurements or present illustrative numbers as observations. Check mathematical assumptions.
Preserve a useful headline_fact, summary, core_mechanics, why_it_matters, in_depth_breakdown and
learning_takeaways for older readers; avoid repeating whole paragraphs across fields.
State uncertainty. Do not present a conjecture, analogy or simplified model as established fact.
{_EVIDENCE_INSTRUCTIONS}
"""
