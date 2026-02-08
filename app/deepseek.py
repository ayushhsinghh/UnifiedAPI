# pip install transformers torch accelerate bitsandbytes sentencepiece

from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
import torch
import json
import logging

logger = logging.getLogger(__name__)

# 8-bit quantization to reduce memory usage
quantization_config = BitsAndBytesConfig(
    load_in_8bit=True,
    llm_int8_enable_fp32_cpu_offload=True
)

model_name = "deepseek-ai/deepseek-coder-6.7b-base"  # Can handle larger models with quantization

try:
    logger.info("Loading model with 8-bit quantization...")
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=quantization_config,
        device_map="cpu",
        trust_remote_code=True,
        low_cpu_mem_usage=True
    )
    logger.info("Model loaded successfully")
except Exception as e:
    logger.error(f"Failed to load model: {str(e)}")
    tokenizer = None
    model = None

# Interactive chat function
def chat(prompt, max_tokens=512):
    """Generate a response from the model given a prompt"""
    if model is None or tokenizer is None:
        raise RuntimeError("Model not loaded. Please ensure transformers and torch are properly installed.")
    
    inputs = tokenizer(prompt, return_tensors="pt")
    
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            temperature=0.7,
            do_sample=True,
            top_p=0.95,
            repetition_penalty=1.1
        )
    
    return tokenizer.decode(outputs[0], skip_special_tokens=True)

def generate_game_topics(category: str) -> dict:
    """
    Generate two related but different topics for Guess the Imposter game.
    
    Args:
        category: The game category (e.g., "animals", "professions", "countries")
    
    Returns:
        dict with keys:
            - player_topic: Topic for most players
            - imposter_topic: Different topic for the imposter
            - category: The category used
    """
    try:
        if model is None or tokenizer is None:
            # Fallback topics if model is not loaded
            fallback_topics = {
                "animals": {
                    "player_topic": "Lion",
                    "imposter_topic": "Tiger"
                },
                "professions": {
                    "player_topic": "Doctor",
                    "imposter_topic": "Nurse"
                },
                "countries": {
                    "player_topic": "France",
                    "imposter_topic": "Germany"
                },
                "fruits": {
                    "player_topic": "Apple",
                    "imposter_topic": "Orange"
                },
                "sports": {
                    "player_topic": "Basketball",
                    "imposter_topic": "Volleyball"
                },
                "movies": {
                    "player_topic": "Avatar",
                    "imposter_topic": "Inception"
                }
            }
            
            if category.lower() in fallback_topics:
                topics = fallback_topics[category.lower()]
            else:
                topics = {"player_topic": category, "imposter_topic": "Unknown"}
            
            logger.info(f"Using fallback topics for category: {category}")
            return {
                "player_topic": topics["player_topic"],
                "imposter_topic": topics["imposter_topic"],
                "category": category
            }
        
        # Use the model to generate topics
        prompt = f"""You are a creative game designer. Given a category, generate two SIMILAR but DIFFERENT related words or topics.
        
Category: {category}

Requirements:
1. The two topics should be similar enough that they relate to the same category
2. But different enough that an "imposter" can bluff
3. Return ONLY a JSON object with keys "player_topic" and "imposter_topic"
4. Each topic should be a single word or short phrase (max 3 words)
5. Do NOT include any other text, only the JSON object

Example:
{{"player_topic": "Lion", "imposter_topic": "Tiger"}}

Now generate for category: {category}"""

        response = chat(prompt, max_tokens=256)
        
        # Extract JSON from response
        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                topics = json.loads(json_str)
                logger.info(f"Generated topics for category {category}: {topics}")
                return {
                    "player_topic": topics.get("player_topic", category),
                    "imposter_topic": topics.get("imposter_topic", category),
                    "category": category
                }
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse JSON response: {str(e)}")
            
        # Fallback to default topics if JSON parsing fails
        default_topics = {
            "player_topic": f"{category} (Original)",
            "imposter_topic": f"{category} (Variant)",
            "category": category
        }
        return default_topics
        
    except Exception as e:
        logger.error(f"Error generating topics: {str(e)}")
        return {
            "player_topic": category,
            "imposter_topic": f"{category} Related",
            "category": category
        }