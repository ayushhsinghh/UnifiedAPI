from typing import Dict

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
        "fundamental technologies that run the modern world, amusing and bizarre tech inventions, "
        "latest cutting-edge breakthroughs shaping the future (AI, quantum computing, robotics), "
        "historical tech milestones, the hidden engineering behind everyday devices, "
        "future tech concepts and theoretical engineering, the evolution of the internet"
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
        "a comprehensive deep-dive into a single specific country, "
        "its unique geopolitical history, defining cultural identity, "
        "economic foundation, and fascinating lesser-known trivia, "
        "providing a complete and immersive guide to what makes that nation distinct"
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
        "mind-bending psychological phenomena, cognitive biases and heuristics, "
        "placebo and nocebo effects, classical and operant conditioning quirks, "
        "neuroplasticity and brain rewiring, social psychology experiments, "
        "memory distortion and false memories, the psychology of perception, "
        "split-brain studies, proven theories of human behavior and decision making"
    ),
    "biology": (
        "fascinating cellular mechanisms, human body oddities, "
        "evolutionary biology quirks, weird animal adaptations, "
        "microbiology and viruses, DNA and genetics, "
        "neurobiology phenomena, unusual plant biology, "
        "deep-sea creatures, extremophiles"
    ),
    "physics": (
        "mind-bending quantum mechanics, astrophysics and black holes, "
        "relativity and time dilation, thermodynamics and entropy, "
        "fluid dynamics phenomena, strange states of matter, "
        "optics and light illusions, particle physics, "
        "electromagnetism quirks, the physics of everyday objects"
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
        "global military history and tactical innovations, advanced defense technologies, "
        "Indian indigenous defense programs (Agni, BrahMos, Tejas), "
        "nuclear triad and deterrence strategies, historical sieges and battles, "
        "mountain warfare expertise (Siachen Glacier), naval fleet strategies, "
        "cyber warfare and intelligence operations, geopolitical military alliances"
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
    "mythbusters": (
        "Pick a widely believed misconception from ANY of these domains: "
        "health & nutrition, science & physics, psychology & behavior, "
        "technology, food & cooking, nature & animals, medicine & body. "
        "Prefer myths that are actively harmful or that most educated adults still believe. "
    )
}

SUPPORTED_CATEGORIES = list(CATEGORY_HINTS.keys())

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
