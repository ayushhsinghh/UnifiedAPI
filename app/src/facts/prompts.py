import random
import time
from typing import List
from configs.config import get_config
from .constants import CATEGORY_HINTS, CLICHED_FACTS
from .visual_prompts import build_visual_instructions

cfg = get_config()

_EVIDENCE_INSTRUCTIONS = """
SOURCE LINKING:
Keep sources_or_references as a list of readable reference strings for older clients.
Also return sources as structured records with unique IDs (s1, s2, ...), title, and URL.
Include author and published_date only when known. Use an empty URL when unknown.
Never invent a URL, author, publication date, study, or source to fill a field.
Return claim_citations for the central claim, key statistics, and other specific claims.
Each item contains the exact claim, its response field name in section, and source_ids.
Use only IDs present in sources. Attach source_ids to quotes, debunk_evidence, and
common_misconceptions when a source supports that item. Use empty lists when unknown.
References are model-supplied, not independently checked by this application.
A source link alone does not establish that a quotation or claim is verified.
"""


def _build_prompt(category: str, blocklist: List[str]) -> str:
    """
    Build the generation prompt with India-first bias, dedup blocklist,
    and randomness injection.
    """
    hints = CATEGORY_HINTS.get(category, category)
    random_seed = random.randint(1, 100000)

    blocklist_instruction = ""
    if blocklist:
        joined = ", ".join(f'"{t}"' for t in blocklist[:cfg.FACTS_DEDUP_LIMIT])
        blocklist_instruction = (
            f"\n\nDO NOT generate facts about any of these previously covered topics: "
            f"[{joined}]. Pick something completely different."
        )

    cliches = ", ".join(f'"{c}"' for c in CLICHED_FACTS)

    prompt = (
        "You are a world-class professor and educational content creator "
        "specializing in Indian knowledge, history, science, and culture. "
        "Your goal is to TEACH the reader something genuinely profound. "
        "Generate ONE deeply researched, encyclopedic-quality educational fact. "
        "The reader should finish feeling like they just read a fascinating "
        "Wikipedia deep-dive or a chapter from a brilliant non-fiction book.\n\n"

        "CRITICAL — CONTENT DEPTH REQUIREMENTS (do NOT summarize, provide exhaustive detail):\n\n"

        "'topic':\n"
        "Must be a concise 6-7 word noun phrase that clearly identifies the subject (e.g., 'Indian Black Pepper Trade History'). "
        "NEVER write a full sentence or include punctuation. This is used for database deduplication.\n\n"

        "'history':\n"
        "Cover the complete origin story from the very beginning. Trace the evolution through "
        "every major era — who were the key people, what were the turning points, what was "
        "the socio-political context at each stage? How did it transform over centuries? "
        "What forces drove those changes? How did it arrive at its modern form in India? "
        "Instead of summarizing, narrate the full arc as if writing a chapter of a history book. "
        "Include specific names, dates, places, and cause-and-effect chains.\n\n"

        "'core_mechanics':\n"
        "This is the single comprehensive field that explains HOW and WHY this works. "
        "Combine the technical explanation, scientific underpinning, and process mechanics "
        "into one cohesive deep-dive. Start from first principles — explain the underlying "
        "systems, mechanisms, engineering, chemistry, or economics as appropriate. "
        "Use analogies that a curious 15-year-old could follow, then build to the full "
        "technical depth. Describe the step-by-step process or technique if applicable. "
        "Explain what makes this different from alternatives. Cover every layer of "
        "complexity — a reader should walk away understanding the full 'machinery' "
        "behind this fact. Do not hold back on detail.\n\n"

        "'why_it_matters':\n"
        "Explain the significance exhaustively. How does this affect everyday life, "
        "government policy, the economy, cultural identity, or global standing? "
        "Draw connections to the bigger picture. Explain the second-order consequences — "
        "what would be different if this hadn't happened? Who benefits and how? "
        "Make the reader feel why this matters to them personally.\n\n"

        "'impact_on_india':\n"
        "Describe specifically how this shaped India — its economy, society, politics, "
        "global standing, or daily life of ordinary Indians. Include concrete examples, "
        "statistics where relevant, and trace both the historical and modern-day impact. "
        "Connect it to current Indian life and future implications.\n\n"

        "'cultural_significance':\n"
        "Explore the cultural, spiritual, artistic, or social meaning in Indian life. "
        "How is this woven into festivals, traditions, art, literature, or daily rituals? "
        "What symbolic or emotional weight does it carry?\n\n"

        "'in_depth_breakdown.detailed_processes':\n"
        "Provide clear, structured explanations of mechanisms, types, or step-by-step processes. "
        "Each process must have a title, a brief description, and a 'steps' array detailing the sequence of actions or components.\n\n"

        "'in_depth_breakdown.fascinating_trivia':\n"
        "List truly surprising details that even knowledgeable people would not know. "
        "Each point should include enough context to understand why it is surprising.\n\n"

        "'in_depth_breakdown.real_world_application':\n"
        "Describe practical applications today — who uses this, where, and how?\n\n"

        "'common_misconceptions':\n"
        "List myths or wrong beliefs people commonly have, structuring each with the 'myth', "
        "the actual 'reality', and the 'evidence' supporting the reality.\n\n"
        "'quote':\n"
        "Provide a highly relevant quote. Set 'confidence' to 'verified' if you are absolutely certain of its authenticity, otherwise 'unverified'.\n\n"
        "'global_comparison':\n"
        "Provide a high-level 'summary' string explaining how India compares globally, followed by a 'comparisons' array detailing specific points of comparison with other countries.\n\n"
        "'content_freshness':\n"
        "Determine if this fact is 'evergreen' (timeless) or 'time-sensitive' (likely to change or become outdated soon).\n\n"

        "'learning_takeaways':\n"
        "List key lessons or insights the reader should remember. "
        "These are the 'so what' bullet points — crisp and memorable.\n\n"

        "'timeline':\n"
        "Include chronological milestones with SPECIFIC dates/years and detailed event "
        "descriptions. Cover the full span from origin to the present.\n\n"

        "'sources_or_references':\n"
        "List specific, verifiable sources — books, research papers, government reports, "
        "historical records with authors and years.\n\n"

        f"{build_visual_instructions()}"

        "INDIA-FIRST RULE (CRITICAL):\n"
        "- Always prioritize facts related to India.\n"
        "- For any category, prefer Indian context first (e.g., Indian food, "
        "Indian space program, Indian history, Indian scientists).\n"
        "- Use other countries ONLY as comparative references or supporting context.\n"
        "- The fact MUST have a strong Indian connection.\n\n"

        f"CATEGORY: {category}\n"
        f"SUB-TOPIC HINTS: {hints}\n"
        f"RANDOMNESS SEED: {random_seed}\n"
        f"TIMESTAMP: {int(time.time())}\n\n"

        "QUALITY RULES:\n"
        "- WRITING STYLE — ASD-STE100 SIMPLIFIED TECHNICAL ENGLISH (CRITICAL, ENFORCE STRICTLY):\n"
        "  You MUST apply the following plain-language rules to EVERY sentence you write:\n"
        "  1. SENTENCE LENGTH: Keep sentences to a MAXIMUM of 25 words. If a sentence exceeds "
        "25 words, split it into two or more shorter sentences.\n"
        "  2. ACTIVE VOICE: Write in active voice at least 70% of the time. "
        "Say 'Scientists discovered X' NOT 'X was discovered by scientists'.\n"
        "  3. ONE IDEA PER SENTENCE: Each sentence conveys exactly one main idea. "
        "Do not chain multiple ideas with commas or semicolons.\n"
        "  4. SIMPLE WORDS: Prefer common, everyday words. Say 'use' not 'utilize', "
        "'start' not 'commence', 'help' not 'facilitate', 'show' not 'demonstrate', "
        "'enough' not 'sufficient', 'about' not 'approximately'.\n"
        "  5. NO NOUN CLUSTERS: Break up chains of 3+ nouns. "
        "Say 'system that controls the engine' NOT 'engine control system module'.\n"
        "  6. CONSISTENT TERMINOLOGY: Use ONE word for ONE meaning throughout. "
        "Do not alternate between synonyms (e.g., pick 'method' OR 'technique', not both).\n"
        "  7. NATURAL 30%: To avoid sounding like a dry manual, you MAY relax these rules "
        "for storytelling hooks, quotes, cultural expressions, and emotional emphasis. "
        "The text should read like a clear, engaging human explanation.\n"
        "- TERMINOLOGY RULE (CRITICAL): Whenever you use a local, regional, or "
        "non-English term (Hindi, Sanskrit, Tamil, etc.), IMMEDIATELY define it "
        "in plain English. Example: 'Jugaad (a frugal, innovative workaround)' "
        "or 'Thali (a round platter with multiple small bowls for serving a full meal)'. "
        "Never assume the reader knows these words.\n"
        "- MARKDOWN FORMATTING (CRITICAL): For all long text fields (history, "
        "core_mechanics, why_it_matters, impact_on_india, cultural_significance), "
        "use Markdown formatting inside the JSON string value. Separate paragraphs "
        "with blank lines (use the literal two-character sequence backslash-n backslash-n "
        "i.e. the JSON escape for a newline). Use **bold** for key terms, "
        "use bullet points (- ) for lists within paragraphs. The goal is that when "
        "the JSON string is parsed and rendered as Markdown, the result is beautifully "
        "structured with clear paragraphs, emphasis, and scannable sections.\n"
        "- The fact must be NON-TRIVIAL, accurate, and genuinely educational.\n"
        "- Avoid common clichés and overused facts. NEVER use any of these: "
        f"[{cliches}].\n"
        "- Provide VERIFIED information with real historical records or data sources.\n"
        "- The 'quote' must be a real, attributed quote from a named person.\n"
        "- The 'share_text' must be under 280 characters for social media.\n"
        "- The 'fun_rating' should be an integer from 1-10.\n"
        "- The 'read_time_seconds' should estimate TOTAL read time (expect 5-10 mins).\n"
        "- The 'difficulty_level' must be one of: beginner, intermediate, advanced.\n"
        "- Be creative! Pick obscure, lesser-known, and fascinating aspects.\n"
        "- Write as if teaching a curious student who WANTS to learn deeply.\n"
        "- Instead of summarizing, provide exhaustive detail in every field. "
        "NO placeholders, NO short answers, NO summaries.\n"
        f"{blocklist_instruction}\n"
    )
    return prompt + _EVIDENCE_INSTRUCTIONS


def _build_mythbuster_prompt(blocklist: List[str], category: str = "mythbusters") -> str:
    """
    Build a generation prompt specifically for myth-busting content.

    Unlike the generic fact prompt, this asks the model to start from a
    misconception and structure the response as a debunking investigation.
    """
    hints = CATEGORY_HINTS.get(category, "common misconceptions")
    random_seed = random.randint(1, 100000)

    blocklist_instruction = ""
    if blocklist:
        joined = ", ".join(f'"{t}"' for t in blocklist[:cfg.FACTS_DEDUP_LIMIT])
        blocklist_instruction = (
            f"\n\nDO NOT debunk any of these previously covered myths: "
            f"[{joined}]. Pick something completely different."
        )

    cliches = ", ".join(f'"{c}"' for c in CLICHED_FACTS)

    prompt = (
        "You are a world-class science communicator and investigative journalist "
        "specializing in debunking widely held misconceptions. "
        "Your goal is to dismantle ONE specific myth with rigorous evidence, "
        "psychological insight, and genuine empathy for why people believe it. "
        "The reader should finish feeling enlightened, not belittled.\n\n"

        "CRITICAL — YOU ARE A MYTH BUSTER, NOT A FACT GENERATOR:\n"
        "Start from a SPECIFIC, WIDELY BELIEVED MISCONCEPTION. "
        "Structure everything as an investigation that builds toward a verdict.\n\n"

        "CONTENT DEPTH REQUIREMENTS:\n\n"

        "'topic':\n"
        "Must be a concise 4-8 word noun phrase identifying the myth subject "
        "(e.g., 'Cracking Knuckles Causes Arthritis Myth'). "
        "NEVER write a full sentence. Used for deduplication.\n\n"

        "'headline_fact':\n"
        "A one-sentence hook that grabs attention by stating the myth and hinting at the truth "
        "(e.g., 'Despite what your parents told you, cracking your knuckles does NOT cause arthritis — "
        "and a doctor spent 60 years proving it on his own hands.').\n\n"

        "'myth_statement':\n"
        "The exact popular claim in quotation marks, stated exactly as believers would say it "
        "(e.g., '\"You need to drink at least 8 glasses of water a day to stay healthy.\"'). "
        "This is the central claim being investigated.\n\n"

        "'verdict':\n"
        "Your definitive ruling. Must be one of: BUSTED (completely false), "
        "PARTIALLY_TRUE (has a kernel of truth but is misleading), "
        "PLAUSIBLE (not enough evidence to fully confirm or deny), "
        "TRUE (actually correct despite sounding like a myth). "
        "Be rigorous — most entries should be BUSTED or PARTIALLY_TRUE.\n\n"

        "'verdict_confidence':\n"
        "How strong is the evidence behind your verdict? "
        "'strong' = meta-analyses, RCTs, overwhelming scientific consensus. "
        "'moderate' = solid observational studies, expert consensus but limited RCTs. "
        "'emerging' = preliminary research, limited data, active scientific debate.\n\n"

        "'myth_origin':\n"
        "Trace the FULL origin story of this myth. When did it first appear? "
        "Who popularized it? Was it a misunderstood study, a marketing campaign, "
        "a cultural tradition, or a logical-sounding assumption? "
        "Include specific names, dates, publications, and the chain of events "
        "that turned an idea into a widely held belief. Write as a narrative "
        "with rich historical detail. Use Markdown formatting.\n\n"

        "'spread_psychology':\n"
        "Analyze the cognitive biases and psychological mechanisms that make this myth sticky. "
        "Name SPECIFIC biases (confirmation bias, availability heuristic, anchoring effect, "
        "authority bias, illusory correlation, etc.) and explain exactly how each one "
        "applies to THIS myth. Why does your brain WANT to believe it? "
        "What emotional or evolutionary purpose does the belief serve? Use Markdown.\n\n"

        "'grain_of_truth':\n"
        "Almost every myth contains a distorted real observation. What is it? "
        "Explain the genuine phenomenon that the myth misinterprets or exaggerates. "
        "This is crucial for empathy — it shows WHY the myth seems plausible. Use Markdown.\n\n"

        "'the_reality':\n"
        "The comprehensive, evidence-based truth. Explain what actually happens, "
        "why the myth is wrong (or partially wrong), and what the science says. "
        "Use analogies a curious 15-year-old could follow, then build to full technical depth. "
        "This should be the most detailed section. Use Markdown.\n\n"

        "'counter_arguments':\n"
        "Steelman the myth. What do believers cite as evidence? What anecdotes or studies "
        "do they reference? Then systematically explain why each counter-argument is "
        "insufficient, outdated, or misinterpreted. Use Markdown.\n\n"

        "'how_to_explain':\n"
        "Provide a practical, empathetic script for how to gently correct someone "
        "who believes this myth. Include conversation starters, the key evidence "
        "to mention, and how to avoid making the person feel stupid. "
        "This should read like advice from a communication expert. Use Markdown.\n\n"

        "'myth_sub_category':\n"
        "Classify this myth into one of: health, science, history, nutrition, "
        "psychology, society, technology, nature, finance, environment.\n\n"

        "'prevalence':\n"
        "How widespread is this myth? Describe its geographic and demographic reach "
        "(e.g., 'Global — believed across all cultures', 'Mostly Western — rooted in "
        "American marketing', 'Indian-specific — tied to Ayurvedic misinterpretations').\n\n"

        "'debunk_evidence':\n"
        "An array of 3-5 specific studies or evidence items. Each must have: "
        "'study' (name of study or experiment), 'year' (publication year), "
        "'finding' (key result in one sentence), 'source' (journal or publication name). "
        "These must be REAL, verifiable studies.\n\n"

        "'common_misconceptions':\n"
        "List 2-3 RELATED myths that stem from the same family of misunderstanding. "
        "Each with 'myth', 'reality', and 'evidence'.\n\n"

        "'timeline':\n"
        "Chronological milestones of how this myth evolved — from its origin through "
        "peak belief to modern debunking efforts. Include specific dates/years.\n\n"

        "'learning_takeaways':\n"
        "3-5 key lessons the reader should remember. "
        "Frame as critical thinking skills, not just 'this myth is false'.\n\n"

        f"{build_visual_instructions(mythbuster=True)}"

        "'sources_or_references':\n"
        "List specific, verifiable sources — research papers, meta-analyses, "
        "textbooks, government health reports with authors and years.\n\n"

        "'quote':\n"
        "A relevant quote from a scientist, researcher, or expert related to this myth. "
        "Set 'confidence' to 'verified' if absolutely certain, otherwise 'unverified'.\n\n"

        f"CATEGORY: {category}\n"
        "Stay within this category. Evaluate the claim fairly; do not assume it is false.\n"
        f"MYTH DOMAIN HINTS: {hints}\n"
        f"RANDOMNESS SEED: {random_seed}\n"
        f"TIMESTAMP: {int(time.time())}\n\n"

        "QUALITY RULES:\n"
        "- WRITING STYLE — ASD-STE100 SIMPLIFIED TECHNICAL ENGLISH (CRITICAL, ENFORCE STRICTLY):\n"
        "  You MUST apply the following plain-language rules to EVERY sentence you write:\n"
        "  1. SENTENCE LENGTH: Keep sentences to a MAXIMUM of 25 words. If a sentence exceeds "
        "25 words, split it into two or more shorter sentences.\n"
        "  2. ACTIVE VOICE: Write in active voice at least 70% of the time. "
        "Say 'Scientists discovered X' NOT 'X was discovered by scientists'.\n"
        "  3. ONE IDEA PER SENTENCE: Each sentence conveys exactly one main idea. "
        "Do not chain multiple ideas with commas or semicolons.\n"
        "  4. SIMPLE WORDS: Prefer common, everyday words. Say 'use' not 'utilize', "
        "'start' not 'commence', 'help' not 'facilitate', 'show' not 'demonstrate', "
        "'enough' not 'sufficient', 'about' not 'approximately'.\n"
        "  5. NO NOUN CLUSTERS: Break up chains of 3+ nouns. "
        "Say 'system that controls the engine' NOT 'engine control system module'.\n"
        "  6. CONSISTENT TERMINOLOGY: Use ONE word for ONE meaning throughout. "
        "Do not alternate between synonyms (e.g., pick 'method' OR 'technique', not both).\n"
        "  7. NATURAL 30%: To avoid sounding like a dry manual, you MAY relax these rules "
        "for storytelling hooks, quotes, cultural expressions, and emotional emphasis. "
        "The text should read like a clear, engaging human explanation.\n"
        "- Pick myths that MOST EDUCATED ADULTS still believe — not obvious ones.\n"
        "- Avoid common clichés and overused myths. NEVER use any of these: "
        f"[{cliches}].\n"
        "- TONE: Empathetic investigator, not smug know-it-all. You are helping, not mocking.\n"
        "- EVIDENCE: All claims must be backed by real, verifiable research.\n"
        "- MARKDOWN FORMATTING: For all long text fields, use Markdown formatting "
        "inside the JSON string value. Separate paragraphs with blank lines "
        "(use literal \\n\\n). Use **bold** for key terms, bullet points for lists.\n"
        "- The 'share_text' must be under 280 characters, formatted as: "
        "'MYTH: [claim] — VERDICT: [ruling]. [one-line truth]'\n"
        "- The 'fun_rating' should be 1-10. Myth-busting is inherently fun, so aim 7+.\n"
        "- The 'read_time_seconds' should estimate TOTAL read time (expect 5-10 mins).\n"
        "- The 'difficulty_level' must be one of: beginner, intermediate, advanced.\n"
        f"{blocklist_instruction}\n"
    )
    return prompt + _EVIDENCE_INSTRUCTIONS


_HEALTH_EVIDENCE_INSTRUCTIONS = """
HEALTH CONTENT RULES (override generic depth or storytelling instructions):
Use simple language, short paragraphs, and practical steps for a general adult audience.
Give general education, not a personalized treatment, calorie target, or supplement prescription.
Separate cultural practices from established evidence. Do not assume traditional means effective,
that millets are universally superior, or that a food is a superfood. Discuss tradeoffs.
Use ICMR-NIN Indian Food Composition Tables / Dietary Guidelines and relevant systematic reviews
or recognized sports medicine guidance where known. Never invent citations or claim a live lookup.
State uncertainty, population differences and relevant contraindications. Do not assume all food
claims are false. Kidney disease and other medical conditions can change protein or exercise advice.
Do not guarantee weight loss, muscle gain, disease prevention or spot fat reduction.
References do not establish medical endorsement.
"""


def _build_wellness_prompt(category: str, blocklist: List[str]) -> str:
    if category == "nutrition_myths":
        return (_build_mythbuster_prompt(blocklist, category) + _HEALTH_EVIDENCE_INSTRUCTIONS
                + "\nCATEGORY: nutrition_myths. Evaluate ONE Indian nutrition or fitness claim from: "
                + CATEGORY_HINTS[category]
                + "\nUse the_reality for the nuanced answer and how_to_explain for a practical Indian-food example.")
    # Reuse the topic avoidance and evidence rules, with the category schema supplied separately.
    common = _build_prompt(category, blocklist)
    if category == "indian_diet":
        contract = """
Return nutrition_guide with goal, food_items, meal_plan, swaps, practical_tips and limitations.
Make this a focused guide to the chosen Indian food or meal topic, not a daily diet prescription.
For each food_items entry include an explicit cooked/raw state, portion in grams/ml plus household
measure, preparation and ingredients/oil assumptions. Nutrient values are approximate per THAT
portion, never a mixture of per-100g and per-serving values. Use null for unknown values, not zero.
Include energy_kcal, protein_g, carbs_g, fat_g, fiber_g, key_micronutrients and source_ids.
Use 3-5 relevant foods, 2-4 illustrative meal combinations, and 2-3 realistic Indian food swaps.
Explain variation from recipe, oil, brand and serving size in limitations. Avoid precise-looking
unsupported estimates. Label example meals as illustrations, not a nutritionally complete day.
"""
    else:
        contract = """
Return training_guide with goal, level, duration_minutes, equipment, frequency, warm_up,
exercises, cool_down, recovery and safety_notes. Provide a modest, coherent beginner example
with 3-5 movements only when relevant to the chosen topic. A cultural/historical topic can use
an empty exercises list. Never force an unsafe advanced practice into a beginner routine.
Each exercise contains name, sets, reps (or duration with units), rest_seconds, ordered steps,
easier_option, progression, and source_ids. Provide self-contained written instructions;
do not request an external exercise search, catalog ID, or demonstration video URL.
Include warm-up and recovery. Explain safe breathing; do not prescribe breath holding or
hyperventilation. State when supervision is needed and to stop for pain, dizziness or chest symptoms.
"""
    return common + _HEALTH_EVIDENCE_INSTRUCTIONS + contract + """
The response schema takes priority: omit history, impact_on_india, cultural_significance,
key_year, key_figure, key_stat, quote, global_comparison and timeline unless requested by the schema.
Keep core_mechanics, why_it_matters and in_depth_breakdown focused on this practical topic.
"""
