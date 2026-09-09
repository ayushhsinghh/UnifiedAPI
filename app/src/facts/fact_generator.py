"""
Daily Learning Fact Generator.

Uses Google Gemini with structured JSON output to generate rich,
educational, India-biased facts. Includes retry logic with exponential
backoff and emergency fallback to cached facts from MongoDB.
"""

import asyncio
import json
import logging
import random
import time
from typing import Dict, List, Optional

import openai
from google import genai

from configs.config import get_config

logger = logging.getLogger(__name__)

cfg = get_config()

# ── Category sub-topic hints ────────────────────────────────────────────
# Fed into the system prompt so Gemini generates diverse, India-biased facts.

CATEGORY_HINTS: Dict[str, str] = {
    "food": (
        "Indian spices & masalas, regional thali traditions, "
        "street food culture (chaat, vada pav), Mughlai cuisine origins, "
        "South Indian fermented foods (dosa, idli), Indian pickle (achar) varieties, "
        "chai culture & history, Indian sweets (mithai) craftsmanship, "
        "Ayurvedic diet principles, India's spice export dominance"
    ),
    "space": (
        "ISRO founding & evolution, Chandrayaan missions (1, 2, 3), "
        "Mangalyaan Mars orbiter, Gaganyaan human spaceflight, "
        "PSLV launch vehicle records, Vikram Sarabhai's legacy, "
        "Indian satellite communication (INSAT), Astrosat X-ray observatory, "
        "ISRO's cost-efficiency records, SpaDeX docking mission"
    ),
    "history": (
        "Indus Valley Civilization, Maurya & Gupta empires, "
        "Mughal era architecture & governance, Maratha empire expansion, "
        "Indian independence movement, Partition of 1947, "
        "ancient Indian trade routes (Silk Road), Chola dynasty naval power, "
        "Indian kingdoms' contributions to art, post-independence modernization"
    ),
    "technology": (
        "Indian IT revolution (Infosys, TCS, Wipro), UPI digital payments system, "
        "Aadhaar biometric ID, Digital India initiative, "
        "Indian startup ecosystem (unicorns), IIT system & tech talent pipeline, "
        "PARAM supercomputers, Indian semiconductor mission, "
        "CoWIN vaccination platform, open-source contributions from India"
    ),
    "science": (
        "CV Raman & Raman Effect, Homi Bhabha & nuclear program, "
        "APJ Abdul Kalam's missile program, Jagadish Chandra Bose (radio waves), "
        "Satyendra Nath Bose (Boson), Indian pharmaceutical generics industry, "
        "Venkatraman Ramakrishnan (Nobel), CSIR research labs, "
        "Indian contributions to metallurgy (Wootz steel), Srinivasa Ramanujan's theorems"
    ),
    "india": (
        "India's linguistic diversity (22 official languages), Indian Railways network, "
        "demographic dividend & population, Indian diaspora worldwide, "
        "unity in diversity, Indian postal system, census & demographic records, "
        "India's time zones, national symbols & emblems, India's UNESCO World Heritage Sites"
    ),
    "country": (
        "India vs China economic comparison, India's role in BRICS & G20, "
        "India-Pakistan relations, India's UN peacekeeping contributions, "
        "India's soft power (Bollywood, yoga, cuisine), India vs global democracy index, "
        "India's nuclear doctrine, Indian Ocean geopolitics, "
        "India's climate commitments, India's role in Non-Aligned Movement"
    ),
    "indian_politics": (
        "Indian parliamentary system, Lok Sabha & Rajya Sabha, "
        "role of the President & PM, Election Commission of India, "
        "EVM voting technology, coalition politics history, "
        "Panchayati Raj system, Indian political parties evolution, "
        "Governor's role in states, anti-defection law"
    ),
    "indian_constitution": (
        "Preamble & its amendments, fundamental rights (Part III), "
        "directive principles (Part IV), constitutional amendments (42nd, 44th, 73rd, 74th), "
        "Dr. B.R. Ambedkar's drafting, federal structure, emergency provisions, "
        "Right to Education, abolition of Article 370, Schedule system (8th schedule languages)"
    ),
    "indian_laws": (
        "RTI Act 2005, Consumer Protection Act, IPC to BNS transition, "
        "landmark Supreme Court judgments (Kesavananda Bharati, Vishakha), "
        "GST implementation, POCSO Act, IT Act 2000 & cyber laws, "
        "environmental protection laws, land acquisition laws, anti-corruption laws (Lokpal)"
    ),
    "nature": (
        "Indian tiger conservation (Project Tiger), Western Ghats biodiversity hotspot, "
        "Sundarbans mangrove ecosystem, Indian national parks (Jim Corbett, Kaziranga), "
        "Himalayan ecology, Indian monsoon system, Thar Desert ecosystem, "
        "Andaman & Nicobar marine life, Indian elephants & corridors, "
        "endemic species of the Eastern Ghats"
    ),
    "medicine": (
        "Ayurveda origins & principles, Sushruta (father of surgery), "
        "Indian generic pharma (pharmacy of the world), AIIMS & medical education, "
        "yoga therapy & WHO recognition, Unani & Siddha medicine systems, "
        "India's polio eradication campaign, Pulse Polio & immunization drives, "
        "Indian contributions to cataract surgery, "
        "traditional herbal medicine (Tulsi, Ashwagandha, Turmeric)"
    ),
    "economics": (
        "Indian GDP growth trajectory, Green Revolution & food security, "
        "liberalization of 1991 (LPG reforms), UPI & fintech revolution, "
        "Make in India initiative, Indian stock exchanges (BSE, NSE), "
        "cooperative movement (Amul model), Indian textile & handloom economy, "
        "remittance economy (NRI contributions), Five-Year Plans history"
    ),
    "geography": (
        "Indian river systems (Ganga, Brahmaputra, Godavari), "
        "Himalayan geology & tectonic activity, Deccan Plateau formation, "
        "Indian coastline (7,500+ km), Western & Eastern Ghats, "
        "Thar Desert geography, Northeast India's biodiversity, "
        "Indian islands (Lakshadweep, Andaman), Indo-Gangetic plain fertility, "
        "Indian climate zones"
    ),
    "culture": (
        "Indian classical dance forms (Bharatanatyam, Kathak, Odissi), "
        "Indian classical music (Hindustani & Carnatic), "
        "festival traditions (Diwali, Holi, Pongal, Onam), "
        "Indian textile arts (Banarasi, Kanjeevaram, Pashmina), Indian cinema history, "
        "ancient Indian literature (Vedas, Upanishads), Indian martial arts (Kalaripayattu), "
        "Indian wedding traditions, rangoli & kolam art, Indian puppet traditions"
    ),
    "mathematics": (
        "Aryabhata (zero & place value), Brahmagupta (negative numbers), "
        "Ramanujan's infinite series, Kerala school of mathematics (calculus precursors), "
        "Baudhayana's geometry (Pythagorean theorem precursor), "
        "Indian numeral system's global adoption, Bhaskara II's Lilavati, "
        "combinatorics in Jain mathematics, Vedic mathematics techniques, "
        "D.R. Kaprekar's number theory"
    ),
    "psychology": (
        "Indian perspectives on consciousness (Yoga Sutras), "
        "mental health stigma & awareness campaigns, NIMHANS & psychiatric research, "
        "Indian family system & collectivist psychology, "
        "mindfulness roots in Buddhist & Hindu traditions, "
        "Indian student stress & competitive exam culture, "
        "workplace psychology in Indian IT sector, "
        "traditional healing & modern therapy integration, "
        "positive psychology & Indian philosophy, "
        "digital mental health platforms in India"
    ),
    "fashion": (
        "Indian traditional clothing (Sari, Kurta, Sherwani, Lehenga), "
        "history of Indian textiles (Khadi, Chanderi, Ikat, Chikankari), "
        "Bollywood fashion influence, indigenous natural dyes (indigo, madder), "
        "Indian sustainable & ethical fashion movements, "
        "regional embroidery styles (Phulkari, Zardosi, Kantha), "
        "handloom weaving traditions, evolution of the Indian wedding attire, "
        "modern Indian designers on the global stage, "
        "historical jewelry making (Kundan, Polki)"
    ),
    "art": (
        "Indian miniature painting traditions (Mughal, Rajput, Pahari), "
        "Ajanta & Ellora cave murals, Madhubani & Warli folk art, "
        "Tanjore painting technique, Indian sculpture (Chola bronzes, Gandhara art), "
        "Pattachitra scroll painting of Odisha, Indian pottery & terracotta traditions, "
        "contemporary Indian art scene (Husain, Raza, Souza), "
        "Rangoli & Kolam as living art forms, "
        "Indian mural art & temple architecture aesthetics"
    ),
    "architecture": (
        "Indian stepwell (baoli) engineering, Mughal geometric design (Taj Mahal, Red Fort), "
        "South Indian gopuram tower construction, Dravidian vs Nagara temple styles, "
        "colonial-era Indo-Saracenic buildings, IIM Ahmedabad & modernist architecture, "
        "Chandigarh city planning (Le Corbusier), cave temple architecture (Badami, Elephanta), "
        "Indian fort engineering (Mehrangarh, Golconda), sustainable mud & bamboo architecture"
    ),
    "music": (
        "Raga system & emotional science of Indian classical music, "
        "Carnatic vs Hindustani traditions, tabla rhythmic mathematics (taal system), "
        "Indian classical instruments (sitar, veena, sarangi, mridangam), "
        "Bollywood playback singing history, Tansen & Akbar's court music, "
        "Baul folk music of Bengal, Qawwali & Sufi musical tradition, "
        "Indian film music composers (R.D. Burman, A.R. Rahman), "
        "Vedic chanting & its UNESCO recognition"
    ),
    "sports": (
        "Cricket as India's cultural religion, chess origins in India (Chaturanga), "
        "kabaddi's ancient roots & Pro Kabaddi League, Indian hockey golden era (1928-1956), "
        "India's Olympic journey & medal history, wrestling (kushti) traditions, "
        "Indian Premier League's economic impact, badminton rise (Saina, Sindhu, Srikanth), "
        "polo origins in Manipur, indigenous sports (gilli-danda, kho-kho, mallakhamb)"
    ),
    "defense": (
        "INS Vikrant indigenous aircraft carrier, Agni & BrahMos missile programs, "
        "Indian Navy submarine fleet & nuclear triad, Tejas indigenous fighter jet, "
        "Indian Army mountain warfare expertise, DRDO research & development, "
        "Siachen Glacier military operations, Indian border infrastructure (roads, tunnels), "
        "Indian peacekeeping forces worldwide, Arjun main battle tank development"
    ),
    "languages": (
        "Sanskrit's computational & grammatical structure (Panini's Ashtadhyayi), "
        "Devanagari script design principles, India's 22 scheduled languages, "
        "how multilingualism works in daily Indian life, endangered tribal languages, "
        "Tamil as one of the oldest living languages, Indian sign language development, "
        "Urdu-Hindi linguistic continuum, Brahmi script evolution, "
        "Indian languages' influence on Southeast Asian scripts"
    ),
    "mythology": (
        "Mahabharata's game theory & political philosophy, Ramayana's geographical mapping, "
        "Vedic cosmology parallels with modern physics, regional folk myths & oral traditions, "
        "temple iconography & symbolism, Puranic timekeeping (yugas & kalpas), "
        "Panchatantra fables & their global spread, Shakti tradition & goddess worship, "
        "Naga & serpent mythology across Indian cultures, "
        "astronomical references in ancient Indian texts"
    ),
    "agriculture": (
        "Green Revolution & Norman Borlaug in India, MSP politics & farmer movements, "
        "Indian spice farming & global trade dominance, organic farming movements, "
        "traditional irrigation systems (stepwells, tanks, johads), "
        "India's crop diversity & seed banks, sugarcane & tea plantation history, "
        "cooperative dairy farming (Amul & Operation Flood), "
        "millets revival & nutritional security, GM crops debate (Bt cotton)"
    ),
    "transport": (
        "Indian Railways engineering marvels & station architecture, "
        "Delhi Metro & urban metro expansion, Konkan Railway tunnel engineering, "
        "National Highway network development, inland waterways revival, "
        "Indian aviation growth & Air India history, Vande Bharat train technology, "
        "Mumbai local train culture, mountain railways (Darjeeling, Shimla, Nilgiri), "
        "Indian shipping & port modernization (Sagarmala project)"
    ),
    "cinema": (
        "Bollywood's global cultural reach, Dadasaheb Phalke & Raja Harishchandra, "
        "Satyajit Ray's Apu Trilogy & international acclaim, regional cinema movements "
        "(Malayalam New Wave, Tamil commercial cinema, Bengali parallel cinema), "
        "Indian animation history, Bombay Talkies & studio era, "
        "playback singing revolution, Indian documentary filmmaking, "
        "Cannes & Oscar recognition for Indian films, "
        "censorship & the CBFC's role in Indian cinema"
    ),
    "philosophy": (
        "Vedanta & Advaita (non-duality) tradition, Buddhism's Indian origins & spread, "
        "Jain logic systems (Anekantavada & Syadvada), Charvaka materialist philosophy, "
        "Guru-Shishya knowledge transmission tradition, Yoga Sutras of Patanjali, "
        "Indian influence on Western philosophers (Schopenhauer, Emerson), "
        "Nyaya school of logic & epistemology, Bhakti movement's philosophical revolution, "
        "Thiruvalluvar's Thirukkural & Tamil ethical philosophy"
    ),
}

SUPPORTED_CATEGORIES = frozenset(CATEGORY_HINTS.keys())

# ── Clichéd facts blocklist ─────────────────────────────────────────────
# Common overused facts the LLM must avoid.

CLICHED_FACTS = [
    "honey never spoils",
    "octopus has three hearts",
    "bananas are berries",
    "Cleopatra lived closer to the Moon landing",
    "Great Wall visible from space",
    "humans use only 10% of their brain",
    "goldfish memory is 3 seconds",
    "lightning never strikes twice",
    "dogs see in black and white",
]

# ── Gemini response schema ──────────────────────────────────────────────
# Enforces structured JSON output from Gemini.

_TIMELINE_ITEM_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "year": {"type": "STRING"},
        "event": {"type": "STRING"},
    },
    "required": ["year", "event"],
}

_BREAKDOWN_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "key_mechanisms_or_types": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "real_world_application": {"type": "STRING"},
        "fascinating_trivia": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "step_by_step_process": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
    },
    "required": [
        "key_mechanisms_or_types",
        "real_world_application",
        "fascinating_trivia",
        "step_by_step_process",
    ],
}

FACT_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        # Core Fact
        "category": {"type": "STRING"},
        "topic": {"type": "STRING"},
        "headline_fact": {"type": "STRING"},
        "summary": {"type": "STRING"},
        "did_you_know": {"type": "STRING"},

        # Deep Dive — the main educational content
        "history": {"type": "STRING"},
        "core_mechanics": {"type": "STRING"},
        "why_it_matters": {"type": "STRING"},
        "in_depth_breakdown": _BREAKDOWN_SCHEMA,

        # India-specific deep context
        "impact_on_india": {"type": "STRING"},
        "cultural_significance": {"type": "STRING"},
        "common_misconceptions": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },

        # Key Highlights
        "key_year": {"type": "STRING"},
        "key_figure": {"type": "STRING"},
        "key_stat": {"type": "STRING"},
        "quote": {"type": "STRING"},
        "global_comparison": {"type": "STRING"},

        # Timeline
        "timeline": {
            "type": "ARRAY",
            "items": _TIMELINE_ITEM_SCHEMA,
        },

        # Learning
        "learning_takeaways": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },

        # Metadata & UI Helpers
        "emoji_icon": {"type": "STRING"},
        "difficulty_level": {"type": "STRING"},
        "region": {"type": "STRING"},
        "fun_rating": {"type": "NUMBER"},
        "read_time_seconds": {"type": "NUMBER"},
        "tags": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "related_categories": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "visual_suggestion": {"type": "STRING"},
        "share_text": {"type": "STRING"},

        # Sources
        "sources_or_references": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
    },
    "required": [
        "category", "topic", "headline_fact", "summary", "did_you_know",
        "history", "core_mechanics", "why_it_matters",
        "in_depth_breakdown",
        "impact_on_india", "cultural_significance", "common_misconceptions",
        "key_year", "key_figure", "key_stat", "quote", "global_comparison",
        "timeline",
        "learning_takeaways",
        "emoji_icon", "difficulty_level", "region", "fun_rating",
        "read_time_seconds", "tags", "related_categories",
        "visual_suggestion", "share_text",
        "sources_or_references",
    ],
}


# ── Prompt builder ───────────────────────────────────────────────────────


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

        "'in_depth_breakdown.key_mechanisms_or_types':\n"
        "List detailed points, each explaining a specific mechanism, type, variant, or aspect. "
        "Every point should include context and explanation, not just a label.\n\n"

        "'in_depth_breakdown.fascinating_trivia':\n"
        "List truly surprising details that even knowledgeable people would not know. "
        "Each point should include enough context to understand why it is surprising.\n\n"

        "'in_depth_breakdown.step_by_step_process':\n"
        "Explain the process, method, or technique in sequential order. "
        "Each step should be self-contained and clear.\n\n"

        "'in_depth_breakdown.real_world_application':\n"
        "Describe practical applications today — who uses this, where, and how?\n\n"

        "'common_misconceptions':\n"
        "List myths or wrong beliefs people commonly have, each with a clear "
        "correction and the evidence behind it.\n\n"

        "'learning_takeaways':\n"
        "List key lessons or insights the reader should remember. "
        "These are the 'so what' bullet points — crisp and memorable.\n\n"

        "'timeline':\n"
        "Include chronological milestones with SPECIFIC dates/years and detailed event "
        "descriptions. Cover the full span from origin to the present.\n\n"

        "'sources_or_references':\n"
        "List specific, verifiable sources — books, research papers, government reports, "
        "historical records with authors and years.\n\n"

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
        "- The 'visual_suggestion' should describe a vivid image the UI could use.\n"
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


# ── Retry constants ──────────────────────────────────────────────────────

_MAX_RETRIES = 3
_BACKOFF_SECONDS = [1, 2, 4]
_REQUEST_TIMEOUT_SECONDS = 30


# ── Main generation function ────────────────────────────────────────────


async def generate_daily_fact(
    category: str,
    blocklist: Optional[List[str]] = None,
) -> dict:
    """
    Generate a rich, structured educational fact using Google Gemini.

    Args:
        category: The fact category (must be from SUPPORTED_CATEGORIES
                  or a custom sanitized category).
        blocklist: List of short topic keys to avoid (dedup).

    Returns:
        A dict matching the FACT_RESPONSE_SCHEMA structure.

    Raises:
        No exceptions — falls back to cached or emergency data on failure.
    """
    if blocklist is None:
        blocklist = []

    prompt = _build_prompt(category, blocklist)
    last_error: Optional[Exception] = None
    
    fallback_models = [cfg.GEMINI_MODEL_NAME, "gemini-3.7-flash", "gemini-3.6-flash", cfg.OPENAI_MODEL_NAME]

    for attempt in range(_MAX_RETRIES + 1):
        model_name = fallback_models[attempt] if attempt < len(fallback_models) else fallback_models[-1]
        try:
            if model_name.startswith("gemini"):
                client = genai.Client(api_key=cfg.GEMINI_API_KEY)
                logger.debug(
                    "Gemini fact generation attempt %d using model '%s' for category '%s'",
                    attempt + 1, model_name, category,
                )

                response = await client.aio.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={
                        "temperature": 0.9,
                        "top_p": 0.95,
                        "top_k": 40,
                        "response_mime_type": "application/json",
                        "response_schema": FACT_RESPONSE_SCHEMA,
                    },
                )
                fact = response.parsed
            else:
                openai_client = openai.AsyncOpenAI(api_key=cfg.OPENAI_API_KEY)
                logger.debug(
                    "OpenAI fallback generation attempt %d using model '%s' for category '%s'",
                    attempt + 1, model_name, category,
                )
                
                openai_prompt = prompt + "\n\nRETURN YOUR RESPONSE AS A VALID JSON OBJECT MATCHING THIS SCHEMA EXACTLY:\n" + json.dumps(FACT_RESPONSE_SCHEMA)
                
                response = await openai_client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": openai_prompt}],
                    response_format={"type": "json_object"},
                    top_p=0.95,
                )
                fact_str = response.choices[0].message.content
                fact = json.loads(fact_str) if fact_str else None

            if isinstance(fact, dict) and fact.get("headline_fact"):
                logger.info(
                    "Generated fact for '%s': %s",
                    category, fact.get("topic", "unknown"),
                )
                return fact

            logger.warning(
                "Model returned empty or malformed response on attempt %d",
                attempt + 1,
            )

        except Exception as exc:
            last_error = exc
            logger.error(
                "API error on attempt %d: %s", attempt + 1, exc,
            )

        # Exponential backoff before retry (skip on last attempt)
        if attempt < _MAX_RETRIES:
            backoff = _BACKOFF_SECONDS[attempt]
            logger.info("Retrying in %ds...", backoff)
            await asyncio.sleep(backoff)

    # All retries exhausted — fall back to cached fact
    logger.warning(
        "All %d Gemini attempts failed for category '%s'. Last error: %s",
        _MAX_RETRIES + 1, category, last_error,
    )
    return None
 