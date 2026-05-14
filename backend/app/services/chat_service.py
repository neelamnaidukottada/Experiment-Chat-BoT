"""Chat service containing all business logic for conversation handling."""

from sqlalchemy.orm import Session
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage
import logging
from typing import List, Optional
from io import BytesIO
import base64

from app.ai.llm import get_chat_llm, get_vision_llm
from app.services.conversation_service import ConversationService
from app.services.rag_service import get_rag_service

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
            "You are a helpful, friendly AI assistant with expertise in analyzing documents, code, data, and all types of files. "
            "Your core responsibility: When the user uploads or shares files, you MUST analyze them directly and provide detailed responses.\n\n"
            "IMPORTANT FILE HANDLING RULES:\n"
            "1. Files are provided to you in the message marked with: ===== FILE START: [filename] ===== and ===== FILE END: [filename] =====\n"
            "2. ALWAYS read the file content between these markers carefully and completely.\n"
            "3. NEVER ask the user to upload the file again - it's already provided.\n"
            "4. NEVER say 'I cannot access files' or 'please provide the file' - the file IS provided in the message.\n"
            "5. Directly answer questions about the file content, extract information, summarize, explain, or analyze as requested.\n"
            "6. If the user asks about a file but doesn't upload it, then ask for it.\n"
            "7. If a file is marked as an error, inform the user about the error.\n\n"
            "Answer questions clearly and concisely, providing helpful and accurate information based on the content provided."
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

    def generate_response(
        self,
        user_message: str,
        retrieval_query: Optional[str] = None,
        user_email: str = "anonymous@example.com",
        conversation_id: int = None,
        user_id: int = None,
        previous_conversations: Optional[List] = None,
    ) -> str:
        """
        Generate an AI response to a user message with optional previous conversation context.
        
        Uses vision LLM for images, text LLM for regular messages.
        
        Args:
            user_message: The user's input message (may include file content or image data).
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
            
            # Check if message contains image data (for vision analysis)
            is_image_message = "[IMAGE ANALYSIS REQUEST]" in user_message
            
            if is_image_message:
                logger.info(f"[ChatService] ✅ IMAGE detected in message - using Vision LLM")
                return self._handle_image_message(user_message, user_email, conversation_id, user_id)
            else:
                logger.info(f"[ChatService] ℹ️ Regular text message - using Text LLM")
                return self._handle_text_message(
                    user_message,
                    user_email,
                    conversation_id,
                    user_id,
                    previous_conversations,
                    retrieval_query,
                )
            
        except Exception as e:
            logger.error(f"[ChatService] Error generating response: {str(e)}", exc_info=True)
            raise RuntimeError(f"Failed to generate response: {str(e)}")
    
    def _handle_image_message(
        self,
        user_message: str,
        user_email: str,
        conversation_id: int,
        user_id: int,
    ) -> str:
        """Handle image analysis using gpt-4o vision via LiteLLM proxy."""
        try:
            logger.info("[ChatService] 🖼️ Processing image message for vision analysis")
            
            # Extract base64 image data from the [IMAGE ANALYSIS REQUEST] block
            start_marker = "[IMAGE ANALYSIS REQUEST]"
            end_marker = "[END IMAGE ANALYSIS REQUEST]"
            
            start = user_message.find(start_marker)
            end = user_message.find(end_marker)
            
            if start == -1 or end == -1:
                logger.warning("[ChatService] Could not find image markers")
                return self._handle_text_message(user_message, user_email, conversation_id, user_id, previous_conversations=None)
            
            image_block = user_message[start:end + len(end_marker)]
            logger.info(f"[ChatService] 🖼️ Extracted image block: {len(image_block)} chars")
            
            # Extract filename for context
            filename_search = image_block.find("image file:")
            if filename_search != -1:
                filename_end = image_block.find("\n", filename_search)
                filename = image_block[filename_search + 11:filename_end].strip()
            else:
                filename = "unknown"
            
            # Extract the data URL
            data_url_start = image_block.find("data:image/")
            data_url_end = image_block.find("\n\nProvide", data_url_start)
            if data_url_end == -1:
                data_url_end = image_block.find("[END IMAGE", data_url_start)
            
            data_url = image_block[data_url_start:data_url_end].strip()
            logger.info(f"[ChatService] 🖼️ Data URL length: {len(data_url)} chars")
            
            # Get the LLM
            llm = get_chat_llm()
            
            # Create message with image in OpenAI format
            # This format is compatible with gpt-4o via LiteLLM proxy
            analysis_prompt = f"""Please analyze this image ({filename}) in detail. Include:
1. What you see in the image
2. Colors, lighting, and mood
3. Any text visible
4. Objects, people, or animals present
5. Overall composition and scene"""
            
            # Use HumanMessage with image_url - gpt-4o/LiteLLM should understand this
            response = llm.invoke([
                HumanMessage(
                    content=[
                        {"type": "text", "text": analysis_prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ]
                )
            ])
            
            logger.info(f"[ChatService] 🖼️ ✅ Response received: {len(response.content)} chars")
            
            # Store in database
            if conversation_id and user_id and self.db:
                ConversationService.add_message(self.db, conversation_id, user_id, "user", f"[Uploaded image: {filename}]")
                ConversationService.add_message(self.db, conversation_id, user_id, "assistant", response.content)
            
            return response.content
            
        except Exception as e:
            logger.error(f"[ChatService] 🖼️ Error in image analysis: {str(e)}", exc_info=True)
            # Fallback to text message handling
            logger.info("[ChatService] 🖼️ Falling back to text message handling")
            return self._handle_text_message(user_message, user_email, conversation_id, user_id, previous_conversations=None)
    
    def _handle_text_message(
        self,
        user_message: str,
        user_email: str,
        conversation_id: int,
        user_id: int,
        previous_conversations: Optional[List] = None,
        retrieval_query: Optional[str] = None,
    ) -> str:
        """Handle regular text messages using Text LLM."""
        try:
            llm_input = user_message

            # Add retrieval context from ChromaDB for this user/conversation.
            if user_id and conversation_id:
                query = retrieval_query or user_message
                rag_context = get_rag_service().retrieve_context(
                    query=query,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    k=5,
                )
                if rag_context:
                    llm_input += (
                        "\n\n===== RAG CONTEXT START =====\n"
                        "The following context was retrieved from uploaded PDFs in ChromaDB. "
                        "Use it to answer accurately.\n\n"
                        f"{rag_context}\n"
                        "===== RAG CONTEXT END ====="
                    )
                    logger.info("[ChatService] 🔎 Added retrieved RAG context to LLM input")

            # Check for file content in message
            has_file_content = "===== FILE START:" in user_message or "===== FILE ERROR:" in user_message
            
            if has_file_content:
                logger.info(f"[ChatService] ✅ FILE CONTENT detected in message")
                # Extract and log file information
                import re
                file_markers = re.findall(r'===== FILE (START|ERROR): (.*?) =====', user_message)
                for marker_type, filename in file_markers:
                    logger.info(f"[ChatService]   📎 File: {filename} ({marker_type})")
            
            # Format previous conversation context
            conversation_history = ""
            if previous_conversations:
                logger.info(f"[ChatService] 📚 Processing {len(previous_conversations)} previous conversations for context")
                conversation_history = self._format_conversation_history(previous_conversations)
            
            # Build system prompt
            system_prompt = self._build_system_prompt(conversation_history)
            logger.info(f"[ChatService] 📋 System prompt built: {len(system_prompt)} characters")
            
            # Log the message being sent (first 500 chars)
            message_preview = llm_input[:500] + "..." if len(llm_input) > 500 else llm_input
            logger.info(f"[ChatService] 📤 Sending to LLM - Message preview: {message_preview}")
            
            # Initialize chain with text LLM
            llm = get_chat_llm()
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", "{input}"),
            ])
            chain = prompt | llm | StrOutputParser()
            
            # Invoke chain
            logger.info(f"[ChatService] ⚙️ Invoking LLM chain...")
            response = chain.invoke(
                {"input": llm_input},
                config={"metadata": {"user_email": user_email}}
            )
            logger.info(f"[ChatService] ✅ LLM response received: {len(response)} characters")
            logger.info(f"[ChatService] 📄 Response preview: {response[:200]}...")
            
            # Store messages in database
            if conversation_id and user_id and self.db:
                ConversationService.add_message(self.db, conversation_id, user_id, "user", user_message)
                ConversationService.add_message(self.db, conversation_id, user_id, "assistant", response)
            
            return response
            
        except Exception as e:
            logger.error(f"[ChatService] ❌ Error in text message handling: {str(e)}", exc_info=True)
            raise RuntimeError(f"Failed to generate response: {str(e)}")


# Singleton instance
_chat_service: ChatService | None = None


def get_chat_service(db: Session = None) -> ChatService:
    """Get or create the chat service instance."""
    return ChatService(db=db)
