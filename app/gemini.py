import logging
from google import genai
import json
import time
import random
import os
from fallback import FALLBACK_DATA

logger = logging.getLogger(__name__)


# To avoid immediate repeats in fallbacks
last_fallback_pair = None

def get_fallback(category):
    global last_fallback_pair
    
    choices_list = FALLBACK_DATA.get(category.lower(), ["Sun", "Moon", "Star", "Earth"])
    
    if len(choices_list) < 2:
        return {"player_topic": "Error", "imposter_topic": "Error"}

    selection = tuple(random.sample(choices_list, 2))
    
    while selection == last_fallback_pair:
        selection = tuple(random.sample(choices_list, 2))
        
    last_fallback_pair = selection
    return {
        "player_topic": selection[0], 
        "imposter_topic": selection[1],
    }
    
def generate_game_topics(category: str) -> dict:
    if category in FALLBACK_DATA:
        logger.info(f"Going for FallBack Option, Gemini is tired now.")
        print(f"Gemini API Fallback triggered for category: {category}")
        return get_fallback(category)
        
    # Absolute Emergency Fallback
    logger.info(f"Going for Emergency FallBack Option, Gemini is tired now.")
    return {"player_topic": "Sun", "imposter_topic": "Moon"}

# def generate_game_topics(category: str) -> dict:
#     # 1. Add a tiny bit of random noise to the prompt to break the cache/pattern
#     random_seed = random.randint(1, 10000)
    
#     prompt = f"""Generate a unique pair of topics for a social deduction game called "Guess the Imposter".
#     Category: {category}
#     Randomness Token: {random_seed}
#     Timestamp: {int(time.time())}

#     RULES:
#     - Create TWO similar but distinct items from given category that is {category}.
#     - Return Only the two items not phases in a JSON format with keys "player_topic" and "imposter_topic".
#     - The "player_topic" should be the more common or well-known item, while the "imposter_topic" should be a less obvious but still plausible item.
#     - Ensure they are common knowledge but have subtle differences.
#     - Be creative! Pick items that haven't been suggested in the last 100 rounds.
#     - Interesting and fun to describe! The more you can say about them, the better.
#     """

#     try:
#         client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
#         response = client.models.generate_content(
#             model='gemini-2.0-flash-lite', 
#             contents=prompt,
#             config={
#                 # 2. Crank up the randomness
#                 'temperature': 1.0, 
#                 'top_p': 0.95,
#                 'top_k': 40,
#                 # 3. Native JSON enforcement (No more manual parsing!)
#                 'response_mime_type': 'application/json',
#                 'response_schema': {
#                     'type': 'OBJECT',
#                     'properties': {
#                         'player_topic': {'type': 'STRING'},
#                         'imposter_topic': {'type': 'STRING'}
#                     },
#                     'required': ['player_topic', 'imposter_topic']
#                 }
#             }
#         )
        
#         # With response_mime_type, we can parse directly
#         return response.parsed
    
#     except Exception as e:
#         logger.error(f"Gemini API Error: {e}")
#         if category in FALLBACK_DATA:
#             logger.info(f"Going for FallBack Option, Gemini is tired now.")
#             print(f"Gemini API Fallback triggered for category: {category}")
#             return get_fallback(category)
        
#         # Absolute Emergency Fallback
#         logger.info(f"Going for Emergency FallBack Option, Gemini is tired now.")
#         return {"player_topic": "Sun", "imposter_topic": "Moon"}

# if __name__ == "__main__":
#     # Quick test run
#     category = "movies"
#     topics = generate_game_topics(category)
#     print(json.dumps(topics, indent=2))