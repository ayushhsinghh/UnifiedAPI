import logging
from google import genai
import json
import time
import random
import os

logger = logging.getLogger(__name__)

client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

FALLBACK_DATA = {
    "animals": [
        ("Cheetah", "Leopard"), ("Raven", "Crow"), ("Dolphin", "Porpoise"), 
        ("Alligator", "Crocodile"), ("Bee", "Wasp"),
        ("Zebra", "Donkey"), ("Hamster", "Guinea Pig"), ("Owl", "Falcon"), 
        ("Octopus", "Squid"), ("Llama", "Alpaca")
    ],
    "professions": [
        ("Plumber", "Electrician"), ("Pilot", "Astronaut"), ("Judge", "Lawyer"), 
        ("Librarian", "Teacher"), ("Surgeon", "Dentist"),
        ("Architect", "Civil Engineer"), ("Firefighter", "Police Officer"), 
        ("Journalist", "Author"), ("Psychologist", "Sociologist"), ("Waiter", "Bartender")
    ],
    "countries": [
        ("Spain", "Portugal"), ("Japan", "South Korea"), ("Brazil", "Argentina"), 
        ("Canada", "USA"), ("Egypt", "Morocco"),
        ("Norway", "Sweden"), ("Australia", "New Zealand"), ("Thailand", "Vietnam"), 
        ("Greece", "Turkey"), ("Mexico", "Colombia")
    ],
    "fruits": [
        ("Peach", "Nectarine"), ("Lime", "Lemon"), ("Blueberry", "Blackberry"), 
        ("Mango", "Papaya"), ("Cherry", "Plum"),
        ("Raspberry", "Strawberry"), ("Grapefruit", "Pomelo"), ("Cantaloupe", "Honeydew"), 
        ("Apricot", "Peach"), ("Mandarin", "Clementine")
    ],
    "sports": [
        ("Baseball", "Cricket"), ("Tennis", "Badminton"), ("Rugby", "Football"), 
        ("Surfing", "Skateboarding"), ("Boxing", "MMA"),
        ("Ice Hockey", "Field Hockey"), ("Biking", "Motorcycling"), ("Skiing", "Snowboarding"), 
        ("Table Tennis", "Pool/Billiards"), ("Swimming", "Water Polo")
    ],
    "movies": [
        ("Star Wars", "Star Trek"), ("Toy Story", "Shrek"), ("Inception", "Interstellar"), 
        ("Jaws", "Jurassic Park"), ("Batman", "Spider-Man"),
        ("The Matrix", "Blade Runner"), ("Harry Potter", "Lord of the Rings"), 
        ("Titanic", "The Notebook"), ("The Godfather", "Scarface"), ("Alien", "Predator")
    ],
    "superheroes": [
        ("Superman", "Thor"), ("Flash", "Quicksilver"), ("Iron Man", "Batman"), 
        ("Wonder Woman", "Captain Marvel"), ("Hulk", "Thanos"),
        ("Black Widow", "Catwoman"), ("Green Lantern", "Doctor Strange"), 
        ("Wolverine", "Black Panther"), ("Ant-Man", "The Atom"), ("Robin", "Nightwing")
    ],
    "foods": [
        ("Pizza", "Calzone"), ("Sushi", "Sashimi"), ("Hamburger", "Hotdog"), 
        ("Taco", "Burrito"), ("Pasta", "Noodles"),
        ("Pancakes", "Waffles"), ("Ice Cream", "Gelato"), ("Steak", "Pork Chop"), 
        ("Donut", "Bagel"), ("Fried Chicken", "Chicken Nuggets")
    ],
}

# To avoid immediate repeats in fallbacks
last_fallback = None

def get_fallback(category):
    global last_fallback
    choices = FALLBACK_DATA.get(category, [("Sun", "Moon")])
    
    # Try to pick a different one than last time
    selection = random.choice(choices)
    while selection == last_fallback and len(choices) > 1:
        selection = random.choice(choices)
        
    last_fallback = selection
    return {"player_topic": selection[0], "imposter_topic": selection[1]}

def generate_game_topics(category: str) -> dict:
    # 1. Add a tiny bit of random noise to the prompt to break the cache/pattern
    random_seed = random.randint(1, 10000)
    
    prompt = f"""Generate a unique pair of topics for a social deduction game called "Guess the Imposter".
    Category: {category}
    Randomness Token: {random_seed}
    Timestamp: {int(time.time())}

    RULES:
    - Create TWO similar but distinct items from given category that is {category}.
    - Return Only the two items not phases in a JSON format with keys "player_topic" and "imposter_topic".
    - The "player_topic" should be the more common or well-known item, while the "imposter_topic" should be a less obvious but still plausible item.
    - Ensure they are common knowledge but have subtle differences.
    - Be creative! Pick items that haven't been suggested in the last 100 rounds.
    - Interesting and fun to describe! The more you can say about them, the better.
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash-lite', 
            contents=prompt,
            config={
                # 2. Crank up the randomness
                'temperature': 1.0, 
                'top_p': 0.95,
                'top_k': 40,
                # 3. Native JSON enforcement (No more manual parsing!)
                'response_mime_type': 'application/json',
                'response_schema': {
                    'type': 'OBJECT',
                    'properties': {
                        'player_topic': {'type': 'STRING'},
                        'imposter_topic': {'type': 'STRING'}
                    },
                    'required': ['player_topic', 'imposter_topic']
                }
            }
        )
        
        # With response_mime_type, we can parse directly
        return response.parsed
    
    except Exception as e:
        logger.error(f"Gemini API Error: {e}")
        if category in FALLBACK_DATA:
            logger.info(f"Going for FallBack Option, Gemini is tired now.")
            print(f"Gemini API Fallback triggered for category: {category}")
            return get_fallback(category)
        
        # Absolute Emergency Fallback
        logger.info(f"Going for Emergency FallBack Option, Gemini is tired now.")
        return {"player_topic": "Sun", "imposter_topic": "Moon"}
