import random
import time
from typing import List
from configs.config import get_config
from .constants import CATEGORY_HINTS, CLICHED_FACTS

cfg = get_config()

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

        "'visual_suggestions':\n"
        "This object must contain EXACTLY 3 highly detailed, rich, and cinematic image generation prompts. Each prompt should be a full descriptive paragraph detailing the subject, lighting, atmosphere, style, and composition:\n"
        "1. 'cover': A stunning, expansive background image that captures the essence of the topic. IT MUST CONTAIN ABSOLUTELY NO TEXT OR WORDS. It should be composed with negative space in mind, and have the main visual elements of the image around the right side of the image leaving room for the UI to overlay the headline on the left side. Specify dramatic lighting and high-quality rendering (e.g., 'Unreal Engine 5 render, cinematic lighting, 8k resolution, wide angle lens').\n"
        "2. 'overview': A highly detailed, photorealistic visual depiction that directly represents the fact. This image should vividly describe the visual essence of the central idea or primary subject. Provide extremely detailed suggestions on the lighting, mood, environment, colors, and specific elements that visually capture the core concept. Make it vibrant, cinematic, and captivating.\n"
        "3. 'how_it_works': A visually striking, diagram-like or conceptual image that clearly illustrates the core mechanics, process, or scientific principle behind the fact. Include details about how to visually represent abstract concepts (e.g., 'glowing energy lines showing the flow of data', 'cross-section view with neon accents', 'intricate macro photography').\n\n"

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
    return prompt

