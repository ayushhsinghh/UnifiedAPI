import asyncio
import base64
import logging
import httpx
from typing import Optional

try:
    import oci
except ImportError:
    oci = None

from configs.config import get_config

logger = logging.getLogger(__name__)
cfg = get_config()


def _upload_to_oci_and_get_par(image_bytes: bytes, image_filename: str) -> Optional[str]:
    if not oci:
        logger.error("oci package is not installed.")
        return None
        
    try:
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        object_storage_client = oci.object_storage.ObjectStorageClient(config={}, signer=signer)
        namespace = cfg.OCI_NAMESPACE
        bucket_name = cfg.OCI_BUCKET_NAME

        # 1. Upload Object
        logger.info(f"Uploading {image_filename} to OCI bucket {bucket_name}...")
        object_storage_client.put_object(
            namespace,
            bucket_name,
            image_filename,
            image_bytes,
            content_type="image/jpeg"
        )
        
        # 2. Create PAR (5 years)
        import datetime
        expiration_time = datetime.datetime.utcnow() + datetime.timedelta(days=365*5)
        
        par_details = oci.object_storage.models.CreatePreauthenticatedRequestDetails(
            name=f"par_{image_filename}",
            object_name=image_filename,
            access_type="ObjectRead",
            time_expires=expiration_time
        )
        
        par_response = object_storage_client.create_preauthenticated_request(
            namespace,
            bucket_name,
            par_details
        )
        
        # 3. Construct URL
        # We need the region to construct the full URL. We can get it from the client config or signer
        region = signer.region
        full_url = f"https://objectstorage.{region}.oraclecloud.com{par_response.data.access_uri}"
        logger.info(f"Successfully generated PAR for {image_filename}")
        
        return full_url
        
    except Exception as e:
        logger.error(f"Failed to upload to OCI or generate PAR: {e}", exc_info=True)
        return None


async def generate_and_save_image(prompt: str, image_filename: str, aspect_ratio: str = "1:1", extra_context: str = "", max_retries: int = 3, retry_delay: int = 20) -> Optional[str]:
    """
    Asynchronously trigger image generation using OpenRouter with retries.
    Uploads to OCI Object Storage and returns the PAR URL.
    """
    if not cfg.OPENROUTER_API_KEY:
        logger.error("OPENROUTER_API_KEY is not set. Cannot generate image.")
        return None

    full_prompt = f"{extra_context}\n\nActual Image Prompt: {prompt}" if extra_context else prompt

    for attempt in range(max_retries):
        try:
            logger.info(f"Attempt {attempt + 1}/{max_retries} - Sending text-to-image prompt to OpenRouter: {full_prompt[:50]}... (aspect_ratio={aspect_ratio})")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url="https://openrouter.ai/api/v1/images",
                    headers={
                        "Authorization": f"Bearer {cfg.OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "black-forest-labs/flux.2-pro",
                        "prompt": full_prompt,
                        "aspect_ratio": aspect_ratio
                    },
                    timeout=90.0
                )
                response.raise_for_status()
                result = response.json()
                
                # Extract first image
                data = result.get("data", [])
                if data and "b64_json" in data[0]:
                    image_b64 = data[0]["b64_json"]
                    image_bytes = base64.b64decode(image_b64)
                    
                    # Upload to OCI in a separate thread to avoid blocking event loop
                    par_url = await asyncio.to_thread(_upload_to_oci_and_get_par, image_bytes, image_filename)
                    if par_url:
                        return par_url
                    
            logger.error("No base64 image data returned or upload failed.")
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error during OpenRouter API call: {e}")
        except Exception as e:
            logger.error(f"Failed to generate and save image from OpenRouter: {e}", exc_info=True)
            
        if attempt < max_retries - 1:
            logger.info(f"Retrying in {retry_delay} seconds...")
            await asyncio.sleep(retry_delay)

    logger.error(f"Failed to generate image {image_filename} after {max_retries} attempts.")
    return None
