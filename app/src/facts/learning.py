"""Shared audience policy for every new fact or category lesson."""

LEARNER_INSTRUCTIONS = """
READER AND TOPIC RULES (override requests for exhaustive or advanced detail):
Teach ONE interesting fact or useful new idea to a reader with no subject expertise.
Choose an easy or medium topic. Prefer beginner; use intermediate only when needed.
Set difficulty_level to beginner or intermediate. Never return advanced or expert.
Do not choose a specialist or graduate-level topic. If it needs extensive background,
choose a simpler topic instead. A surprising fact does not need an obscure technical topic.
Start with a familiar situation, then explain what happens and why it matters.
Assume no prior subject knowledge. Explain necessary background in one or two short sentences.
Use common everyday words and short sentences, preferably under 20 words.
Use short paragraphs with one main idea. Explain an unfamiliar term immediately when it first appears.
Keep terminology consistent. Avoid jargon when a common word conveys the same meaning.
Use one concrete example and a few connected steps to explain the main idea.
Avoid specialist research debates, detailed biochemical pathways, calculus and formal proofs.
Optional depth clarifies the SAME idea; it must not become an advanced lesson.
Math, when genuinely needed, stays at basic arithmetic or a simple relation with all symbols explained.
Leave optional equations, derivations and technical sections empty when they add little learning value.
Keep evidence and important limits, but explain them simply. Do not weaken accuracy to simplify wording.
Do not repeat paragraphs or add filler to populate every field. Keep required fields concise and useful.
Aim for a focused 3-6 minute read, not an encyclopedia chapter or exam syllabus.
Before returning, check that a newcomer can explain the central fact in one sentence.
"""


def normalize_learning_level(fact):
    """Reject unsupported difficulty labels; this does not measure prose readability."""
    level = fact.get('difficulty_level')
    if not isinstance(level, str) or level.strip().lower() not in ('beginner', 'intermediate'):
        return False
    fact['difficulty_level'] = level.strip().lower()
    return True
