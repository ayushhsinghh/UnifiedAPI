import asyncio
import base64
import logging
import os
from openai import AsyncOpenAI

from configs.config import get_config

logger = logging.getLogger(__name__)
cfg = get_config()


async def generate_and_save_image(prompt: str, image_filename: str) -> bool:
    """
    Asynchronously trigger image generation and save it locally using the OpenAI Python SDK
    pointing to NVIDIA's integrate API.
    
    Args:
        prompt: The visual suggestion prompt.
        image_filename: The filename (e.g. 'fact_xyz.jpg') to save as.
        
    Returns:
        True if successful, False otherwise.
    """
    if not cfg.NVIDIA_API_KEY:
        logger.error("NVIDIA_API_KEY is not set. Cannot generate image.")
        return False

    client = AsyncOpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=cfg.NVIDIA_API_KEY
    )

    # Ensure static/images dir exists at project root
    static_images_dir = os.path.join(os.getcwd(), "static", "images")
    os.makedirs(static_images_dir, exist_ok=True)
    output_path = os.path.join(static_images_dir, image_filename)

    try:
        logger.info(f"Sending text-to-image prompt to NVIDIA Qwen-Image NIM: {prompt[:50]}...")
        response = await client.images.generate(
            model="qwen-image",
            prompt=prompt,
            size="1024x1024",
            response_format="b64_json",
            n=1
        )
        
        image_b64 = response.data[0].b64_json
        if image_b64:
            image_bytes = base64.b64decode(image_b64)
            with open(output_path, "wb") as f:
                f.write(image_bytes)
            logger.info(f"Successfully saved generated image to {output_path}")
            return True
            
        logger.error("No base64 image data returned from NVIDIA API.")
        return False

    except Exception as e:
        logger.error(f"Failed to generate or save image: {e}")
        return False

