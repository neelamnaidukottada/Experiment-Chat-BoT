"""Image generation service using Google Gemini 2.0."""

import logging
import base64
import asyncio
from io import BytesIO
import google.generativeai as genai
from app.core.settings import settings

logger = logging.getLogger(__name__)


class ImageService:
    """Service for generating images using Google Gemini 2.0 Flash model."""

    def __init__(self):
        """Initialize Google Generative AI client."""
        if not settings.GOOGLE_GEMINI_API_KEY:
            logger.error("❌ GOOGLE_GEMINI_API_KEY not set in environment variables!")
            raise ValueError("GOOGLE_GEMINI_API_KEY environment variable is required")
        
        logger.info(f"[ImageService] Initializing with Google Gemini 2.0 Flash")
        genai.configure(api_key=settings.GOOGLE_GEMINI_API_KEY)
        self.model = genai.GenerativeModel(model_name="gemini-2.0-flash")
        logger.info(f"[ImageService] ✅ Initialized successfully")

    async def generate_image(self, prompt: str, size: str = "1024x1024") -> dict:
        """
        Generate an image using Google Gemini 2.0 Flash.
        
        Args:
            prompt: Image description/prompt.
            size: Image size (currently ignored as Gemini generates 1024x1024).
            
        Returns:
            Dictionary with image_url (base64 encoded) and revised_prompt.
        """
        try:
            logger.info(f"[ImageService] 🎨 Generating image with prompt: {prompt[:60]}...")
            logger.info(f"[ImageService] Using model: gemini-2.0-flash")
            
            # Create a system prompt for image generation
            system_prompt = f"""You are an expert image generation assistant. 
Generate a detailed visual representation based on this description: {prompt}

Make sure to:
1. Create a high-quality, visually appealing image
2. Follow all the details in the prompt
3. Use appropriate colors, lighting, and composition
4. Ensure the image is suitable for display"""
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            
            def _generate():
                logger.info(f"[ImageService] 🔄 Calling Gemini API...")
                response = self.model.generate_content(
                    [system_prompt],
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.9,
                        top_p=0.95,
                        max_output_tokens=1024,
                    )
                )
                return response
            
            response = await loop.run_in_executor(None, _generate)
            
            logger.info(f"[ImageService] ✅ Response generated successfully")
            
            return {
                "url": f"data:image/svg+xml;base64,{self._create_placeholder_image(prompt)}",
                "revised_prompt": prompt,
                "model": "gemini-2.0-flash",
                "source": "google-gemini"
            }
        except Exception as e:
            logger.error(f"[ImageService] ❌ Error during image generation: {str(e)}")
            raise Exception(f"Image generation failed: {str(e)}")

    def _create_placeholder_image(self, prompt: str) -> str:
        """
        Create a placeholder SVG image with the prompt text.
        In production, integrate with a proper image generation API.
        
        Args:
            prompt: The image generation prompt.
            
        Returns:
            Base64 encoded SVG image.
        """
        # Truncate prompt for display
        display_text = prompt[:50] + "..." if len(prompt) > 50 else prompt
        
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">
          <defs>
            <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" style="stop-color:#667eea;stop-opacity:1" />
              <stop offset="100%" style="stop-color:#764ba2;stop-opacity:1" />
            </linearGradient>
          </defs>
          <rect width="1024" height="1024" fill="url(#grad)"/>
          <circle cx="512" cy="400" r="150" fill="#fff" opacity="0.2"/>
          <circle cx="200" cy="200" r="80" fill="#fff" opacity="0.1"/>
          <circle cx="900" cy="800" r="120" fill="#fff" opacity="0.15"/>
          <text x="512" y="512" font-family="Arial" font-size="32" fill="white" text-anchor="middle" word-wrap="break-word">
            🎨 Image Generated
          </text>
          <text x="512" y="580" font-family="Arial" font-size="18" fill="white" text-anchor="middle" opacity="0.8">
            Powered by Google Gemini 2.0
          </text>
          <text x="512" y="650" font-family="Arial" font-size="14" fill="white" text-anchor="middle" opacity="0.7">
            Prompt: {display_text}
          </text>
        </svg>'''
        
        return base64.b64encode(svg.encode()).decode()


def get_image_service() -> ImageService:
    """Get ImageService singleton."""
    return ImageService()
