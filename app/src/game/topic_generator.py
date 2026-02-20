"""
Topic generation for the Guess-the-Imposter game.

Uses Google Gemini as the primary source and falls back to curated
per-category lists when the API is unavailable.

Merges the old ``gemini.py`` and ``fallback.py`` into a single module.
"""

import json
import logging
import os
import random
import time
from typing import Dict, Optional

from google import genai

from configs.config import get_config

logger = logging.getLogger(__name__)

cfg = get_config()

# ── Fallback data ────────────────────────────────────────────────────────
# Kept inline so the module is self-contained.  Import the dict from a
# separate file if it grows large enough to warrant its own module.

FALLBACK_DATA: Dict[str, list] = {
    "animals": [
        "Bengal Tiger", "Indian Elephant", "Snow Leopard", "One-horned Rhino",
        "Asiatic Lion", "Peacock", "King Cobra", "Gharial", "Nilgai",
        "Blackbuck", "Hanuman Langur", "Sloth Bear", "Red Panda",
        "Clouded Leopard", "Indian Wolf", "Golden Jackal", "Striped Hyena",
        "Indian Fox", "Wild Boar", "Mongoose", "Kangaroo", "Pangolin",
        "Spotted Deer", "Sambar Deer", "Barking Deer", "Indian Bison",
        "Water Buffalo", "Camel", "Yak", "Himalayan Tahr",
        "Great Indian Bustard", "Indian Roller", "Parrot", "Myna", "Bulbul",
        "Eagle", "Vulture", "Owl", "Rat", "Cat", "Dog", "Cow", "Goat",
        "Sheep", "Donkey", "Horse", "Monkey", "Squirrel",
    ],
    "professions": [
        "Surgeon", "Dentist", "Physiotherapist", "Pharmacist", "Optician",
        "Veterinary Doctor", "Yoga Instructor", "Nurse", "Radiologist",
        "Psychiatrist", "Software Engineer", "Data Analyst",
        "Chartered Accountant (CA)", "Human Resources (HR)",
        "Digital Marketer", "Investment Banker", "UI/UX Designer",
        "Cybersecurity Expert", "Company Secretary", "Project Manager",
        "Police Inspector", "Traffic Constable", "Lawyer", "Judge",
        "IAS Officer", "Income Tax Officer", "Army Major", "Firefighter",
        "Intelligence Agent (RAW)", "Postmaster", "Bollywood Actor",
        "Film Director", "News Anchor", "Wedding Photographer",
        "Makeup Artist", "Fashion Designer", "Radio Jockey (RJ)",
        "Stunt Performer", "Lyricist", "Content Creator", "Railway TTE",
        "Bus Conductor", "Dabbawala", "Delivery Partner",
        "Zomato/Swiggy Rider", "Security Guard", "Electrician", "Plumber",
        "Carpenter", "Tailor (Darzi)", "Barber", "Pandit/Priest",
        "Raddiwallah", "Dobi (Washerman)", "Milkman (Doodhwala)",
        "Jeweller (Sunar)", "Potter (Kumhaar)", "Blacksmith (Lohaar)",
        "Gardener (Maali)", "Shopkeeper",
    ],
    "countries": [
        "India", "Pakistan", "Bangladesh", "Sri Lanka", "Nepal", "Bhutan",
        "Maldives", "China", "Japan", "South Korea", "Thailand", "Vietnam",
        "Indonesia", "Malaysia", "Singapore", "Afghanistan", "Iran", "Iraq",
        "Saudi Arabia", "UAE", "Qatar", "UK", "France", "Germany", "Italy",
        "Spain", "Russia", "USA", "Canada", "Mexico", "Brazil", "Argentina",
        "Australia", "New Zealand", "South Africa", "Egypt", "Kenya",
        "Nigeria", "Switzerland", "Sweden", "Norway", "Denmark",
        "Netherlands", "Belgium", "Greece", "Turkey", "Israel", "Ukraine",
        "Poland", "Portugal",
    ],
    "fruits": [
        "Mango", "Banana", "Apple", "Orange", "Guava", "Papaya",
        "Pomegranate", "Watermelon", "Muskmelon", "Grapes", "Pineapple",
        "Chickoo", "Custard Apple", "Lychee", "Jackfruit", "Pear", "Peach",
        "Plum", "Apricot", "Cherry", "Strawberry", "Blueberry", "Blackberry",
        "Coconut", "Amla", "Tamarind", "Jamun", "Ber", "Starfruit",
        "Dragon Fruit", "Kiwi", "Avocado", "Fig", "Date", "Prune", "Raisin",
        "Cashew Apple", "Mulberry", "Wood Apple", "Lemon", "Lime",
        "Sweet Lime", "Grapefruit", "Pomelo", "Passion Fruit", "Cranberry",
        "Raspberry", "Olive", "Walnut", "Almond",
    ],
    "sports": [
        "Cricket", "Kabaddi", "Hockey", "Football", "Badminton", "Tennis",
        "Table Tennis", "Wrestling", "Boxing", "Archery", "Shooting",
        "Weightlifting", "Athletics", "Swimming", "Cycling", "Chess",
        "Carrom", "Kho-Kho", "Gilli Danda", "Ludo", "Snakes and Ladders",
        "Basketball", "Volleyball", "Handball", "Rugby", "Golf", "Billards",
        "Snooker", "Squash", "Formula 1", "Motor Racing", "Horse Racing",
        "Polo", "Judo", "Karate", "Taekwondo", "Yoga", "Mallakhamba",
        "Kalaripayattu", "Fencing", "Gymnastics", "Rowing", "Sailing",
        "Surfing", "Skating", "Skiing", "Ice Hockey", "Mountaineering",
        "Trekking", "High Jump",
    ],
    "movies": [
        "Sholay", "Zanjeer", "DDLJ", "Kuch Kuch Hota Hai",
        "Kabhi Khushi Kabhie Gham", "Hum Saath Saath Hain", "Devdas",
        "Bajirao Mastani", "Lagaan", "Dangal", "Mother India",
        "Mughal-E-Azam", "Amar Akbar Anthony", "Naseeb", "Don",
        "Agneepath", "Mr. India", "Shaan", "Deewaar", "Trishul",
        "Dil Chahta Hai", "Zindagi Na Milegi Dobara", "3 Idiots",
        "Chhichhore", "Yeh Jawaani Hai Deewani", "Ae Dil Hai Mushkil",
        "Rock On!!", "Gully Boy", "Queen", "English Vinglish", "Piku",
        "Karwaan", "Wake Up Sid", "Tamasha", "Barfi!", "Jagga Jasoos",
        "Kai Po Che!", "MS Dhoni: The Untold Story", "Sanju", "Rocketry",
        "Hera Pheri", "Welcome", "Andaz Apna Apna", "Munna Bhai M.B.B.S.",
        "Lage Raho Munna Bhai", "Golmaal", "Dhamaal", "Chennai Express",
        "Bol Bachchan", "Stree", "Bhool Bhulaiyaa", "Dream Girl", "Bala",
        "Housefull", "Total Dhamaal", "Fukrey", "War", "Pathaan", "Dhoom",
        "Race", "Singham", "Simmba", "Drishyam", "Special 26", "Andhadhun",
        "Ittefaq", "Raazi", "Baby", "Gangs of Wasseypur", "Satya",
        "Kahaani", "Pink", "Badla", "Talaash", "Vikram Vedha", "Bholaa",
        "Veer-Zaara", "Kal Ho Naa Ho", "Jab We Met", "Hum Tum",
        "Aashiqui 2", "Kabir Singh", "Dil To Pagal Hai", "Taal",
        "Chak De! India", "Maidaan", "Bhaag Milkha Bhaag", "Sultan",
        "Mary Kom", "Saand Ki Aankh", "Padmaavat", "Jodhaa Akbar",
        "Brahmastra", "Ra.One", "Main Hoon Na", "Om Shanti Om", "RRR",
        "KGF: Chapter 1", "KGF: Chapter 2", "Pushpa: The Rise", "Kantara",
        "Baahubali 2", "Ponniyin Selvan", "Vikram", "Jailer", "Leo",
        "Salaar", "Hanu-Man", "Minnal Murali", "Eega (Makkhi)",
        "Sita Ramam", "Animal", "Jawan", "Gadar 2", "Tiger 3", "Dunki",
        "12th Fail", "Laapataa Ladies", "OMG 2", "The Kerala Story",
        "Fighter", "Bramayugam", "Munjya", "Chandu Champion", "Kill",
        "Merry Christmas", "Maine Pyar Kiya", "Hum Aapke Hain Koun..!",
        "Karan Arjun", "Baazigar", "Border", "Rangeela", "Sarfarosh",
        "Anand", "Pakeezah", "Guide", "Aradhana", "Kati Patang", "Bobby",
        "Julie", "Masaan", "Tumbbad", "Article 15", "Newton", "Badhaai Do",
        "Vicky Donor", "Bareilly Ki Barfi", "Luka Chuppi",
        "Manjhi: The Mountain Man", "Udaan",
    ],
    "superheroes": [
        "Shaktimaan", "Krrish", "G.One", "Flying Jatt", "Minnal Murali",
        "Bhisma", "Nagraj", "Super Commando Dhruva", "Parmanu", "Bheriya",
        "Inspector Steel", "Shakti", "Tiranga", "Anthony", "Super Indian",
        "Devi", "Sadhu", "Aghori", "Ravan", "Hanuman", "Bheem", "Arjun",
        "Karna", "Vikram Betal", "Hatim Tai", "Mowgli", "Baahubali",
        "Iron Man", "Spider-Man", "Batman", "Superman", "Wonder Woman",
        "Thor", "Hulk", "Captain America", "Black Panther", "Doctor Strange",
        "Flash", "Aquaman", "Cyborg", "Shazam", "Joker", "Thanos", "Loki",
        "Wolverine", "Deadpool", "Black Widow", "Scarlet Witch", "Vision",
        "Ant-Man", "Star-Lord", "Groot", "Hawkeye", "Ghost Rider",
    ],
    "foods": [
        "Samosa", "Jalebi", "Dhokla", "Vada Pav", "Pani Puri", "Bhel Puri",
        "Pav Bhaji", "Idli", "Dosa", "Vada", "Uttapam", "Biryani", "Pulao",
        "Butter Chicken", "Paneer Tikka", "Dal Makhani", "Chole Bhature",
        "Rajma Chawal", "Paratha", "Naan", "Roti", "Gulab Jamun",
        "Rasgulla", "Kulfi", "Lassi", "Masala Chai", "Filter Coffee",
        "Pakora", "Kachori", "Thali", "Upma", "Poha", "Khichdi",
        "Fish Curry", "Chicken Tikka", "Mutton Rogan Josh", "Korma",
        "Nihari", "Hyderabadi Haleem", "Mishti Doi", "Sandesh", "Barfi",
        "Laddu", "Petha", "Mysore Pak", "Gajak", "Chikki", "Aloo Paratha",
        "Baigan Bharta", "Palak Paneer", "Litti Chokha", "Sarson Ka Saag",
        "Makki Ki Roti", "Puran Poli", "Misal Pav", "Appam",
        "Malabar Paratha", "Akki Roti", "Methi Thepla", "Khandvi", "Momos",
        "Gobi Manchurian", "Hakka Noodles", "Chilli Chicken", "Spring Rolls",
        "Manchow Soup", "Aloo Tikki", "Dahi Bhalla", "Sev Puri", "Dahi Puri",
        "Medu Vada", "Sabudana Khichdi", "Sabudana Vada", "Onion Bhajji",
        "Bread Pakora", "Malai Kofta", "Dum Aloo", "Matar Paneer",
        "Kadai Paneer", "Seekh Kebab", "Tandoori Chicken", "Chicken 65",
        "Galouti Kebab", "Afghani Chaap", "Baingan Musallam", "Rasmalai",
        "Kheer", "Gajar Ka Halwa", "Soan Papdi", "Rabri", "Ghevar",
        "Shrikhand", "Modak", "Malpua", "Shahi Tukda", "Kalakand",
        "Cham Cham", "Thandai", "Jaljeera", "Nimbu Pani", "Sol Kadhi",
        "Badam Milk",
    ],
    "celebrities": [
        "Shah Rukh Khan", "Salman Khan", "Aamir Khan", "Amitabh Bachchan",
        "Rajinikanth", "Akshay Kumar", "Ajay Devgn", "Hrithik Roshan",
        "Ranbir Kapoor", "Ranveer Singh", "Deepika Padukone",
        "Priyanka Chopra", "Alia Bhatt", "Katrina Kaif", "Kareena Kapoor",
        "Aishwarya Rai", "Madhuri Dixit", "Sridevi", "Kajol",
        "Anushka Sharma", "Sachin Tendulkar", "Virat Kohli", "MS Dhoni",
        "Rohit Sharma", "Hardik Pandya", "Kapil Dev", "Sunil Gavaskar",
        "Sourav Ganguly", "Yuvraj Singh", "Rishabh Pant", "A.R. Rahman",
        "Arijit Singh", "Shreya Ghoshal", "Lata Mangeshkar", "Kishore Kumar",
        "Badshah", "Diljit Dosanjh", "Kapil Sharma", "Zakir Khan",
        "Abhishek Upmanyu", "Prabhas", "Allu Arjun", "Yash", "Ram Charan",
        "Jr. NTR", "Vijay Thalapathy", "Mahesh Babu",
        "Samantha Ruth Prabhu", "Nayanthara", "Rashmika Mandanna",
        "Vicky Kaushal", "Ayushmann Khurrana", "Kartik Aaryan",
        "Shahid Kapoor", "Sidharth Malhotra", "Varun Dhawan",
        "Tiger Shroff", "Pankaj Tripathi", "Manoj Bajpayee",
        "Rajkummar Rao", "Shraddha Kapoor", "Kriti Sanon", "Kiara Advani",
        "Sara Ali Khan", "Janhvi Kapoor", "Taapsee Pannu", "Vidya Balan",
        "Rani Mukerji", "Juhi Chawla", "Karisma Kapoor", "Neeraj Chopra",
        "PV Sindhu", "Sania Mirza", "Mary Kom", "Sunil Chhetri",
        "Mithali Raj", "Smriti Mandhana", "Shubman Gill", "KL Rahul",
        "Mohammed Shami", "Shaan", "Sonu Nigam", "Neha Kakkar",
        "Sunidhi Chauhan", "Yo Yo Honey Singh", "Divine", "Raftaar",
        "Ustad Zakir Hussain", "Jubin Nautiyal", "Mohit Chauhan",
        "Kamal Haasan", "Mammootty", "Mohanlal", "Fahadh Faasil",
        "Dulquer Salmaan", "Dhanush", "Trisha Krishnan", "Keerthy Suresh",
        "Sai Pallavi", "Anushka Shetty",
    ],
    "tv_shows": [
        "Mirzapur", "Sacred Games", "Panchayat", "The Family Man",
        "Scam 1992", "Kota Factory", "Delhi Crime", "Made in Heaven",
        "Gullak", "Farzi", "Special Ops", "Paatal Lok", "Aspirants",
        "Rocket Boys", "Criminal Justice", "Khichdi",
        "Taarak Mehta Ka Ooltah Chashmah", "CID", "Shaktimaan",
        "Office Office", "Hum Paanch", "Dekh Bhai Dekh", "F.I.R.",
        "Bhabiji Ghar Par Hain!",
        "Kyunki Saas Bhi Kabhi Bahu Thi", "Kasautii Zindagii Kay",
        "Ramayan", "Mahabharat", "Bigg Boss", "Kaun Banega Crorepati",
        "Shark Tank India", "Indian Idol", "MasterChef India", "Splitsvilla",
        "Roadies", "Koffee with Karan", "The Kapil Sharma Show",
        "Dance India Dance", "Game of Thrones", "Friends", "The Office",
        "Breaking Bad", "Stranger Things", "Money Heist", "Squid Game",
        "Narcos", "Sherlock", "The Big Bang Theory",
    ],
}

# Track last fallback pair to avoid immediate repeats
_last_fallback_pair: Optional[tuple] = None

# ── Category sanitisation ────────────────────────────────────────────────

_CATEGORY_MODIFICATIONS = {
    "movies": "bollywood movies",
    "celebrities": "Indian celebrities",
    "tv_shows": "Indian tv shows",
    "fruits": "Indian fruits",
    "foods": "Indian foods",
}


def sanitise_category(category: str) -> str:
    """Map generic categories to more specific Indian variants."""
    normalised = category.lower().strip()
    modified = _CATEGORY_MODIFICATIONS.get(normalised, normalised)
    if modified != normalised:
        logger.info("Category modified from '%s' to '%s'", category, modified)
    return modified


# ── Fallback generator ───────────────────────────────────────────────────


def get_fallback_topics(category: str) -> Dict[str, str]:
    """Pick two random items from fallback data for the given category."""
    global _last_fallback_pair

    choices_list = FALLBACK_DATA.get(
        category.lower(), ["Sun", "Moon", "Star", "Earth"]
    )

    if len(choices_list) < 2:
        return {"player_topic": "Error", "imposter_topic": "Error"}

    selection = tuple(random.sample(choices_list, 2))
    while selection == _last_fallback_pair:
        selection = tuple(random.sample(choices_list, 2))

    _last_fallback_pair = selection
    return {"player_topic": selection[0], "imposter_topic": selection[1]}


# ── Primary (Gemini) generator ───────────────────────────────────────────


def generate_game_topics(
    category: str,
    previous_player_topic: Optional[str] = None,
    previous_imposter_topic: Optional[str] = None,
) -> Dict[str, str]:
    """
    Generate a pair of topics using Google Gemini.

    Falls back to curated lists if the API call fails.
    """
    modified_category = sanitise_category(category)
    random_seed = random.randint(1, 10000)

    avoid_instruction = ""
    if previous_player_topic and previous_imposter_topic:
        avoid_instruction = (
            f"- DO NOT regenerate the exact same pair as before: "
            f"'{previous_player_topic}' and '{previous_imposter_topic}'. "
            "Pick something different."
        )

    prompt = (
        'Generate a unique pair of topics for a social deduction game '
        'called "Guess the Imposter".\n'
        f"Category: {modified_category}\n"
        f"Randomness Token: {random_seed}\n"
        f"Timestamp: {int(time.time())}\n\n"
        "RULES:\n"
        f"- Create TWO similar but distinct items from category "
        f"{modified_category}.\n"
        '- Return only the two items in JSON with keys '
        '"player_topic" and "imposter_topic".\n'
        '- The "player_topic" should be more common/well-known; '
        'the "imposter_topic" should be less obvious but plausible.\n'
        f"- {avoid_instruction}\n"
        "- Ensure they are common knowledge with subtle differences.\n"
        "- Be creative! Pick items not suggested in the last 100 rounds.\n"
        "- Cross-check: topics must belong to the category.\n"
        "- Interesting and fun to describe!\n"
    )

    try:
        client = genai.Client(api_key=cfg.GEMINI_API_KEY)
        logger.debug("Gemini prompt: %s", prompt)
        response = client.models.generate_content(
            model=cfg.GEMINI_MODEL_NAME,
            contents=prompt,
            config={
                "temperature": 1.0,
                "top_p": 0.95,
                "top_k": 40,
                "response_mime_type": "application/json",
                "response_schema": {
                    "type": "OBJECT",
                    "properties": {
                        "player_topic": {"type": "STRING"},
                        "imposter_topic": {"type": "STRING"},
                    },
                    "required": ["player_topic", "imposter_topic"],
                },
            },
        )
        return response.parsed

    except Exception as exc:
        logger.error("Gemini API error: %s", exc)
        if category.lower() in FALLBACK_DATA:
            logger.info(
                "Using fallback topics for category '%s'", category
            )
            return get_fallback_topics(category)

        # Absolute emergency fallback
        logger.info("Using emergency fallback topics")
        return {"player_topic": "Sun", "imposter_topic": "Moon"}
