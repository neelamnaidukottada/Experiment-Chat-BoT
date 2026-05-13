"""Image generation service using Google Gemini image generation model."""

import asyncio
import base64
import logging
from typing import Any

from app.core.settings import settings

try:
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - handled at runtime if dependency missing
    genai = None  # type: ignore[assignment]
    types = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class ImageService:
    """Service for generating images using Google Gemini 2.0 image model."""

    def __init__(self):
        """Initialize Google GenAI client."""
        if not settings.GOOGLE_GEMINI_API_KEY:
            logger.error("❌ GOOGLE_GEMINI_API_KEY not set in environment variables!")
            raise ValueError("GOOGLE_GEMINI_API_KEY environment variable is required")

        if genai is None or types is None:
            raise RuntimeError(
                "google-genai package is not installed. Install it with `pip install google-genai`."
            )

        self.model_name = settings.GEMINI_IMAGE_MODEL
        logger.info(f"[ImageService] Initializing with model: {self.model_name}")
        self.client = genai.Client(api_key=settings.GOOGLE_GEMINI_API_KEY)
        logger.info(f"[ImageService] ✅ Initialized successfully")

    async def generate_image(self, prompt: str, size: str = "1024x1024") -> dict:
        """
        Generate an image using Gemini image generation.
        
        Args:
            prompt: Image description/prompt.
            size: Preferred image size (currently advisory only).
            
        Returns:
            Dictionary with data URL and revised prompt.
        """
        try:
            if not prompt or not prompt.strip():
                raise ValueError("Prompt cannot be empty")

            logger.info(f"[ImageService] 🎨 Generating image with prompt: {prompt[:60]}...")
            logger.info(f"[ImageService] Using model: {self.model_name}")

            def _generate() -> Any:
                logger.info("[ImageService] 🔄 Calling Gemini image generation API...")
                return self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["TEXT", "IMAGE"],
                    ),
                )

            response = await asyncio.to_thread(_generate)
            logger.info(f"[ImageService] ✅ Response generated successfully")

            image_data_url, revised_prompt = self._extract_image_and_text(response, prompt)
            return {
                "url": image_data_url,
                "revised_prompt": revised_prompt,
                "model": self.model_name,
                "source": "google-gemini",
                "requested_size": size,
            }
        except Exception as e:
            logger.error(f"[ImageService] ❌ Error during image generation: {str(e)}")
            raise Exception(f"Image generation failed: {str(e)}")

    def _extract_image_and_text(self, response: Any, fallback_prompt: str) -> tuple[str, str]:
        """Extract generated image bytes and revised prompt text from Gemini response."""
        revised_prompt_parts: list[str] = []
        encoded_image: str | None = None
        mime_type = "image/png"

        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                text = getattr(part, "text", None)
                if text:
                    revised_prompt_parts.append(text.strip())

                inline_data = getattr(part, "inline_data", None)
                if inline_data and getattr(inline_data, "data", None):
                    raw_data = inline_data.data
                    mime_type = getattr(inline_data, "mime_type", None) or mime_type
                    if isinstance(raw_data, bytes):
                        encoded_image = base64.b64encode(raw_data).decode("utf-8")
                    elif isinstance(raw_data, str):
                        encoded_image = raw_data

        if not encoded_image:
            raise ValueError("Gemini response did not include image data")

        revised_prompt = " ".join(part for part in revised_prompt_parts if part).strip() or fallback_prompt
        return f"data:{mime_type};base64,{encoded_image}", revised_prompt


def get_image_service() -> ImageService:
    """Get ImageService singleton."""
    return ImageService()
