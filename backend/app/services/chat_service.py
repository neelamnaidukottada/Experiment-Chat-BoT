"""Chat service containing all business logic for conversation handling."""

from sqlalchemy.orm import Session
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import logging
from typing import List, Optional

from app.ai.llm import get_chat_llm
from app.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)


class ChatService:
    """Service for handling chat interactions with LLM."""

    def __init__(self, db: Session = None):
        """Initialize the chat service with LLM and chain."""
        self.llm = get_chat_llm()
        self.db = db
        self.conversation_history_context = ""

    def _build_system_prompt(self, conversation_history: str = "") -> str:
        """
        Build the system prompt with optional conversation history context.
        
        Args:
            conversation_history: Formatted string of previous conversation context.
            
        Returns:
            Complete system prompt.
        """
        base_prompt = (
            "You are a helpful, friendly AI assistant. "
            "Answer questions clearly and concisely. "
            "When you see file content marked with ===== FILE START: filename ===== and ===== FILE END: filename =====, "
            "you MUST read and analyze that file content carefully. "
            "Always respond based on the actual file content provided, not by asking for it again. "
            "Extract information, summarize, explain, or analyze the file as requested by the user."
        )
        
        if conversation_history:
            base_prompt += (
                "\n\n--- PREVIOUS CONVERSATION CONTEXT ---\n"
                "You have access to the following 5 most recent previous conversations for context:\n\n"
                f"{conversation_history}\n"
                "--- END PREVIOUS CONTEXT ---\n"
                "Use this context to provide better, more informed responses and to maintain consistency with previous discussions."
            )
        
        return base_prompt

    def _format_conversation_history(self, conversations: List) -> str:
        """
        Format previous conversations into a readable context string.
        
        Args:
            conversations: List of Conversation objects (in reverse chronological order).
            
        Returns:
            Formatted conversation history string.
        """
        if not conversations:
            return ""
        
        formatted_parts = []
        
        for i, conversation in enumerate(conversations, 1):
            # Reverse to show chronological order within each conversation
            messages = sorted(conversation.messages, key=lambda m: m.created_at)
            
            formatted_parts.append(f"[Previous Conversation {i}: {conversation.title}]")
            for msg in messages:
                sender = "You" if msg.sender == "user" else "Assistant"
                # Truncate long messages to 200 chars in context
                content = msg.content[:200] + "..." if len(msg.content) > 200 else msg.content
                formatted_parts.append(f"{sender}: {content}")
            formatted_parts.append("")
        
        return "\n".join(formatted_parts)

    def _init_chain(self, system_prompt: str) -> None:
        """Initialize LCEL chain for chat with dynamic system prompt."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])
        
        # LCEL chain: prompt | llm | parser
        self.chain = prompt | self.llm | StrOutputParser()

    def generate_response(
        self,
        user_message: str,
        user_email: str = "anonymous@example.com",
        conversation_id: int = None,
        user_id: int = None,
        previous_conversations: Optional[List] = None,
    ) -> str:
        """
        Generate an AI response to a user message with optional previous conversation context.
        
        Args:
            user_message: The user's input message (may include file content).
            user_email: Email for usage tracking with LiteLLM.
            conversation_id: Conversation ID for storing message (optional).
            user_id: User ID for authorization (optional).
            previous_conversations: List of previous conversation objects for context (optional).
            
        Returns:
            The AI-generated response.
        """
        try:
            logger.info(f"[ChatService] Generating response for user: {user_email}")
            logger.info(f"[ChatService] Message length: {len(user_message)} characters")
            logger.info(f"[ChatService] Message preview (first 300 chars): {user_message[:300]}")
            
            if "[File:" in user_message:
                logger.info(f"[ChatService] ✅ File content detected in message")
            else:
                logger.warning(f"[ChatService] ⚠️ NO file content detected in message")
            
            # Format previous conversation context
            conversation_history = ""
            if previous_conversations:
                logger.info(f"[ChatService] 📚 Processing {len(previous_conversations)} previous conversations for context")
                conversation_history = self._format_conversation_history(previous_conversations)
                logger.info(f"[ChatService] 📚 Formatted conversation history: {len(conversation_history)} characters")
            else:
                logger.info(f"[ChatService] ℹ️ No previous conversations provided")
            
            # Build system prompt with conversation context
            system_prompt = self._build_system_prompt(conversation_history)
            logger.info(f"[ChatService] 📋 System prompt built: {len(system_prompt)} characters")
            
            # Initialize chain with dynamic system prompt
            self._init_chain(system_prompt)
            
            # Invoke chain with metadata for usage tracking
            logger.info(f"[ChatService] Invoking LLM chain...")
            response = self.chain.invoke(
                {"input": user_message},
                config={"metadata": {"user_email": user_email}}
            )
            logger.info(f"[ChatService] LLM response received: {len(response)} characters")
            logger.info(f"[ChatService] Response preview: {response[:200]}")
            
            # Store messages in database if conversation_id provided
            if conversation_id and user_id and self.db:
                logger.info(f"[ChatService] Storing messages in database")
                ConversationService.add_message(
                    self.db,
                    conversation_id,
                    user_id,
                    "user",
                    user_message,
                )
                ConversationService.add_message(
                    self.db,
                    conversation_id,
                    user_id,
                    "assistant",
                    response,
                )
            
            return response
        except Exception as e:
            logger.error(f"[ChatService] Error generating response: {str(e)}", exc_info=True)
            raise RuntimeError(f"Failed to generate response: {str(e)}")


# Singleton instance
_chat_service: ChatService | None = None


def get_chat_service(db: Session = None) -> ChatService:
    """Get or create the chat service instance."""
    return ChatService(db=db)
