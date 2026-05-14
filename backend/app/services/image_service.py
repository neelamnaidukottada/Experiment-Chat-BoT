"""Image generation service using Gemini Imagen via LiteLLM proxy."""

import logging
import httpx
from app.core.settings import settings

logger = logging.getLogger(__name__)


class ImageService:
    """Service for generating images using Gemini Imagen via the Amzur LiteLLM proxy."""

    def __init__(self):
        logger.info(f"[ImageService] Initializing with model: {settings.IMAGE_GEN_MODEL}")

    async def generate_image(self, prompt: str, size: str = "1024x1024") -> dict:
        """
        Generate an image using Gemini Imagen via the LiteLLM proxy.

        Args:
            prompt: Image description/prompt.
            size: Image size (e.g. "1024x1024").

        Returns:
            Dictionary with url (data URI or remote URL), revised_prompt, model, source.
        """
        try:
            logger.info(f"[ImageService] 🎨 Generating image — model: {settings.IMAGE_GEN_MODEL}, prompt: {prompt[:80]}...")

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{settings.LITELLM_PROXY_URL}/v1/images/generations",
                    headers={
                        "Authorization": f"Bearer {settings.LITELLM_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.IMAGE_GEN_MODEL,
                        "prompt": prompt,
                        "n": 1,
                        "size": size,
                        "response_format": "b64_json",
                    },
                )

            if response.status_code != 200:
                error_body = response.text
                logger.error(f"[ImageService] ❌ Proxy returned {response.status_code}: {error_body}")
                raise Exception(f"LiteLLM proxy error {response.status_code}: {error_body}")

            data = response.json()
            logger.info(f"[ImageService] ✅ Proxy responded OK")

            image_data = data["data"][0]

            if image_data.get("b64_json"):
                image_url = f"data:image/png;base64,{image_data['b64_json']}"
            elif image_data.get("url"):
                image_url = image_data["url"]
            else:
                raise ValueError(f"No image data in proxy response: {data}")

            return {
                "url": image_url,
                "revised_prompt": image_data.get("revised_prompt", prompt),
                "model": settings.IMAGE_GEN_MODEL,
                "source": "litellm-proxy",
            }

        except Exception as e:
            logger.error(f"[ImageService] ❌ Error: {str(e)}")
            raise Exception(f"Image generation failed: {str(e)}")


def get_image_service() -> ImageService:
    """Get ImageService instance."""
    return ImageService()
