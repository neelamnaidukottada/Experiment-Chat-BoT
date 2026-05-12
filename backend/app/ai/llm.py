"""LiteLLM client singletons. All AI calls route through litellm.amzur.com."""

from langchain_openai import ChatOpenAI
import os
import logging

from app.core.settings import settings

logger = logging.getLogger(__name__)


def get_chat_llm() -> ChatOpenAI:
    """
    Get LangChain ChatOpenAI client using LiteLLM proxy.
    
    Routes requests to https://litellm.amzur.com instead of OpenAI directly.
    Compatible with langchain-openai==1.2.1 and openai==2.36.0
    """
    try:
        # Initialize ChatOpenAI with LiteLLM proxy as the base URL
        llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.LITELLM_API_KEY,
            base_url=settings.LITELLM_PROXY_URL,
            temperature=0.7,
        )
        logger.info("✅ ChatOpenAI initialized successfully (via LiteLLM proxy)")
        return llm
    except Exception as e:
        logger.error(f"❌ ChatOpenAI initialization failed: {e}")
        raise
