"""Chat router - HTTP endpoints for chat functionality."""

from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File, Form, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
import logging
from typing import Optional, List
import json

from app.core.database import get_db
from app.core.auth import get_current_user_email
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationSummaryResponse,
)
from app.services.chat_service import get_chat_service
from app.services.conversation_service import ConversationService
from app.services.auth_service import AuthService
from app.services.image_service import get_image_service
from app.services.file_service import FileService
from app.services.rag_service import get_rag_service
from app.services.url_service import URLService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    request: Request,
    user_email: str = Depends(get_current_user_email),
    conversation_id: Optional[int] = None,
    db: Session = Depends(get_db),
) -> ChatMessageResponse:
    """
    Send a message and get an AI response. Supports both JSON and multipart/form-data.
    
    Accepts either:
    - JSON: {"user_message": "text"}
    - FormData: user_message + optional files
    
    Args:
        request: FastAPI request object to handle different content types.
        user_email: Current authenticated user email.
        conversation_id: Conversation ID (optional).
        db: Database session.
        
    Returns:
        ChatMessageResponse with assistant response.
    """
    try:
        logger.info(f"[Chat] ========== NEW MESSAGE REQUEST ==========")
        logger.info(f"[Chat] Request content-type: {request.headers.get('content-type', 'UNKNOWN')}")
        
        # Get user
        user = AuthService.get_user_by_email(db, user_email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        
        user_message = None
        files = []
        
        # Determine if request is JSON or FormData
        content_type = request.headers.get("content-type", "")
        logger.info(f"[Chat] Content-Type header value: '{content_type}'")
        
        if "application/json" in content_type:
            # Handle JSON request (text-only message)
            body = await request.json()
            user_message = body.get("user_message", "")
            logger.info("[Chat] ✅ Received JSON request - TEXT ONLY")
            
        elif "multipart/form-data" in content_type:
            # Handle FormData request (with or without files)
            form_data = await request.form()
            user_message = form_data.get("user_message", "")
            
            # Get files if any - check both uppercase and lowercase
            files_list = form_data.getlist("files") or form_data.getlist("file") or []
            logger.info(f"[Chat] ✅ Received FormData request - Detected {len(files_list)} files")
            if files_list:
                files = [f for f in files_list if hasattr(f, 'filename')]
                logger.info(f"[Chat] ✅ Valid file objects: {len(files)}")
                for f in files:
                    logger.info(f"[Chat]   - File: {f.filename} (type: {f.content_type})")
            else:
                logger.info("[Chat] ℹ️ FormData request but NO FILES detected")
        else:
            logger.warning(f"[Chat] ⚠️ Unsupported content-type: {content_type}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid content type. Expected application/json or multipart/form-data",
            )
        
        if not user_message:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_message is required",
            )
        
        logger.info(f"[Chat] CHECKING FILES: received {len(files)} files")

        # Create conversation early so uploaded files can be indexed per conversation
        if not conversation_id:
            conversation = ConversationService.create_conversation(db, user.id)
            conversation_id = conversation.id
        
        # Process message with files if any
        message_content = user_message
        
        if files and len(files) > 0:
            logger.info(f"[Chat] ⭐ ENTERING FILE PROCESSING BLOCK - {len(files)} file(s) detected")
            file_contents = []
            
            for file in files:
                try:
                    file_content = await file.read()
                    logger.info(f"[Chat] ✅ READ FILE: {file.filename} - {len(file_content)} bytes")
                    
                    content_type_value = file.content_type or "application/octet-stream"
                    extension = file.filename.lower().split('.')[-1] if '.' in file.filename else ''

                    # Use RAG path for PDFs: index in ChromaDB and provide an indexing note in prompt.
                    if extension == "pdf" or "pdf" in content_type_value.lower():
                        rag_service = get_rag_service()
                        chunk_count = rag_service.ingest_pdf(
                            file_content=file_content,
                            filename=file.filename,
                            user_id=user.id,
                            conversation_id=conversation_id,
                        )
                        extracted_text = (
                            f"[PDF indexed for retrieval with ChromaDB. "
                            f"Indexed chunks: {chunk_count}. "
                            "Ask questions and I will use RAG context from this file.]"
                        )
                        logger.info(
                            f"[Chat] ✅ PDF indexed in RAG store: {file.filename}, chunks={chunk_count}"
                        )
                    else:
                        # Extract text from non-PDF files directly into the prompt.
                        logger.info(f"[Chat] 🔄 CALLING FileService.extract_text_from_file() for {file.filename}")
                        extracted_text = FileService.extract_text_from_file(
                            file_content,
                            file.filename,
                            content_type_value,
                        )
                        logger.info(f"[Chat] EXTRACTED: {len(str(extracted_text)) if extracted_text else 0} chars from {file.filename}")
                    
                    # ALWAYS append file content to message (with or without extraction)
                    if extracted_text and len(str(extracted_text).strip()) > 0:
                        file_content_str = str(extracted_text)
                        logger.info(f"[Chat] ✅ Using extracted content: {len(file_content_str)} chars")
                    else:
                        # Even if extraction failed, include a placeholder
                        file_content_str = f"[File could not be read: {file.filename}]"
                        logger.warning(f"[Chat] ⚠️ Extraction empty for {file.filename}")
                    
                    # ALWAYS append with proper formatting
                    formatted_content = f"\n\n===== FILE START: {file.filename} =====\n{file_content_str}\n===== FILE END: {file.filename} ====="
                    file_contents.append(formatted_content)
                    logger.info(f"[Chat] ✅ APPENDED file block: {len(formatted_content)} chars")
                    
                except Exception as e:
                    logger.error(f"[Chat] ❌ ERROR processing file {file.filename}: {str(e)}", exc_info=True)
                    # Still append error message
                    error_block = f"\n\n===== FILE ERROR: {file.filename} =====\nError reading file: {str(e)}\n===== FILE ERROR END ====="
                    file_contents.append(error_block)
                    logger.warning(f"[Chat] ⚠️ Appended error block for {file.filename}")
            
            # CRITICAL: Always append file contents if files were processed
            if file_contents:
                message_content = user_message + "".join(file_contents)
                logger.info(f"[Chat] ✅✅✅ FINAL MESSAGE - Total length: {len(message_content)} chars")
                logger.info(f"[Chat] ✅✅✅ Message preview (first 300 chars): {message_content[:300]}")
            else:
                logger.error(f"[Chat] ❌❌❌ FILES WERE PROCESSED BUT file_contents is EMPTY!")
        else:
            logger.info(f"[Chat] No files - text only message")
        
        logger.info(f"[Chat] BEFORE LLM - Message length: {len(message_content)} chars")
        
        # Check for all types of markers
        has_file_markers = "[File" in message_content or "=====" in message_content
        has_image_marker = "[IMAGE ANALYSIS REQUEST]" in message_content
        
        if has_file_markers or has_image_marker:
            logger.info(f"[Chat] ✅ Confirmed: Content markers present in message!")
            if has_image_marker:
                logger.info(f"[Chat] ✅ IMAGE MARKER DETECTED - Will trigger vision LLM")
            if has_file_markers:
                logger.info(f"[Chat] ✅ FILE MARKERS DETECTED - Will include file content")
        else:
            logger.warning(f"[Chat] ⚠️ Warning: No content markers in message!")
        
        # Fetch previous conversations for context (last 5 conversations excluding current one)
        logger.info(f"[Chat] 📚 Fetching previous conversations for context")
        previous_conversations = ConversationService.get_previous_conversations(
            db,
            user.id,
            current_conversation_id=conversation_id,
            limit=5,
        )
        logger.info(f"[Chat] 📚 Retrieved {len(previous_conversations)} previous conversations")
        
        # Generate response with conversation context
        chat_service = get_chat_service(db=db)
        assistant_response = chat_service.generate_response(
            user_message=message_content,
            retrieval_query=user_message,
            user_email=user_email,
            conversation_id=conversation_id,
            user_id=user.id,
            previous_conversations=previous_conversations,
        )
        
        return ChatMessageResponse(
            user_message=user_message,
            assistant_response=assistant_response,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Chat] Error processing message: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "llm_error", "message": str(e)},
        )


class ImageGenerateRequest(BaseModel):
    prompt: str
    size: str = "1024x1024"


@router.post("/generate-image")
async def generate_image(
    request: ImageGenerateRequest,
    user_email: str = Depends(get_current_user_email),
):
    """
    Generate an image from a text prompt using Gemini Imagen via LiteLLM proxy.

    Returns:
        JSON with url, revised_prompt, model, source.
    """
    try:
        logger.info(f"[Chat] 🎨 Image generation request from {user_email}: {request.prompt[:80]}")
        image_service = get_image_service()
        result = await image_service.generate_image(request.prompt, request.size)
        logger.info(f"[Chat] ✅ Image generated successfully")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Chat] ❌ Image generation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "image_generation_error", "message": str(e)},
        )


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(
    data: ConversationCreate,
    user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
) -> ConversationResponse:
    """
    Create a new conversation.
    
    Args:
        data: Conversation creation data.
        user_email: Current authenticated user email.
        db: Database session.
        
    Returns:
        Created conversation.
    """
    user = AuthService.get_user_by_email(db, user_email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    conversation = ConversationService.create_conversation(db, user.id, data.title)
    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[],
    )


@router.get("/conversations", response_model=list[ConversationSummaryResponse])
async def get_conversations(
    user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
) -> list[ConversationSummaryResponse]:
    """
    Get all conversations for the current user.
    
    Args:
        user_email: Current authenticated user email.
        db: Database session.
        
    Returns:
        List of conversation summaries.
    """
    user = AuthService.get_user_by_email(db, user_email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    return ConversationService.get_user_conversations(db, user.id)


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: int,
    user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
) -> ConversationResponse:
    """
    Get a specific conversation with all messages.
    
    Args:
        conversation_id: Conversation ID.
        user_email: Current authenticated user email.
        db: Database session.
        
    Returns:
        Conversation with messages.
    """
    user = AuthService.get_user_by_email(db, user_email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    try:
        conversation = ConversationService.get_conversation(db, conversation_id, user.id)
        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            messages=[
                {
                    "id": msg.id,
                    "sender": msg.sender,
                    "content": msg.content,
                    "created_at": msg.created_at,
                }
                for msg in conversation.messages
            ],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    """
    Delete a conversation.
    
    Args:
        conversation_id: Conversation ID.
        user_email: Current authenticated user email.
        db: Database session.
    """
    user = AuthService.get_user_by_email(db, user_email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    try:
        ConversationService.delete_conversation(db, conversation_id, user.id)
        return {"status": "deleted"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.put("/conversations/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: int,
    data: ConversationCreate,
    user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
) -> ConversationResponse:
    """
    Update a conversation (e.g., rename).
    
    Args:
        conversation_id: Conversation ID.
        data: Updated conversation data.
        user_email: Current authenticated user email.
        db: Database session.
        
    Returns:
        Updated conversation.
    """
    user = AuthService.get_user_by_email(db, user_email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    
    try:
        if data.title:
            conversation = ConversationService.update_conversation_title(
                db, conversation_id, user.id, data.title
            )
        else:
            conversation = ConversationService.get_conversation(db, conversation_id, user.id)
        
        return ConversationResponse(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            messages=[
                {
                    "id": msg.id,
                    "sender": msg.sender,
                    "content": msg.content,
                    "created_at": msg.created_at,
                }
                for msg in conversation.messages
            ],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


# ============ Image Generation Schemas ============

class GenerateImageRequest(BaseModel):
    """Request to generate an image."""
    prompt: str
    size: str = "1024x1024"


class GenerateImageResponse(BaseModel):
    """Response with generated image."""
    url: str
    prompt: str
    revised_prompt: str
    model: str = "gemini-2.0-flash"
    source: str = "google-gemini"


# ============ Image Generation Endpoint ============

@router.post("/generate-image", response_model=GenerateImageResponse)
async def generate_image(
    request: GenerateImageRequest,
    user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
) -> GenerateImageResponse:
    """
    Generate an image using Google Gemini 2.0 Flash.
    
    Args:
        request: Image generation request with prompt and optional size.
        user_email: Current authenticated user email.
        db: Database session.
        
    Returns:
        GenerateImageResponse with image URL and metadata.
    """
    logger.info(f"[ImageGeneration] Image generation request received from {user_email}")
    logger.info(f"[ImageGeneration] Prompt: {request.prompt[:60]}...")
    
    try:
        # Verify user exists
        user = AuthService.get_user_by_email(db, user_email)
        if not user:
            logger.warning(f"[ImageGeneration] User not found: {user_email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        
        logger.info(f"[ImageGeneration] 🎨 Generating image for user: {user.email}")
        # Generate image
        image_service = get_image_service()
        image_data = await image_service.generate_image(
            prompt=request.prompt,
            size=request.size,
        )
        
        logger.info(f"[ImageGeneration] ✅ Image generated successfully for user: {user.email}")
        return GenerateImageResponse(
            url=image_data["url"],
            prompt=request.prompt,
            revised_prompt=image_data["revised_prompt"],
            model=image_data.get("model", "gemini-2.0-flash"),
            source=image_data.get("source", "google-gemini"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ImageGeneration] ❌ Image generation error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "image_generation_error", "message": str(e)},
        )


# ============ URL Analysis Schemas ============

class URLAnalysisRequest(BaseModel):
    """Request to analyze a URL or video."""
    url: str
    user_message: str = "Analyze this content"
    conversation_id: Optional[int] = None


class URLAnalysisResponse(BaseModel):
    """Response with analyzed URL content."""
    user_message: str
    assistant_response: str


# ============ URL Analysis Endpoint ============

@router.post("/analyze-url", response_model=URLAnalysisResponse)
async def analyze_url(
    request: URLAnalysisRequest,
    user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
) -> URLAnalysisResponse:
    """
    Analyze content from a URL or YouTube video.
    
    Args:
        request: URL analysis request with URL and optional message.
        user_email: Current authenticated user email.
        db: Database session.
        
    Returns:
        URLAnalysisResponse with assistant analysis.
    """
    logger.info(f"[URLAnalysis] ========== NEW URL ANALYSIS REQUEST ==========")
    logger.info(f"[URLAnalysis] URL: {request.url}")
    logger.info(f"[URLAnalysis] User message: {request.user_message}")
    
    try:
        # Verify user exists
        user = AuthService.get_user_by_email(db, user_email)
        if not user:
            logger.warning(f"User not found: {user_email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        
        # Process URL/video and extract content
        logger.info(f"[URLAnalysis] Processing URL: {request.url}")
        url_result = URLService.process_url_or_video(request.url)
        
        # Prepare message content - handle both success and failure cases
        if url_result["success"] and url_result["content"]:
            # Content was successfully extracted
            message_content = f"{request.user_message}\n\n{url_result['content']}"
            logger.info(f"[URLAnalysis] ✅ Content extracted: {len(message_content)} chars")
        else:
            # No content available - send error message to LLM
            error_msg = url_result.get("error", "Unable to fetch content from this URL.")
            metadata_reason = url_result.get("metadata", {}).get("reason", "unknown")
            
            if metadata_reason == "no_captions":
                # YouTube video without captions - ask user for help
                message_content = f"{request.user_message}\n\n[SYSTEM NOTICE: URL Analysis Failed]\nURL: {request.url}\nReason: {error_msg}\n\nPlease provide the video summary, key points, or specific questions about it instead."
            else:
                # Other failures
                message_content = f"{request.user_message}\n\n[SYSTEM NOTICE: URL Analysis Failed]\nURL: {request.url}\nError: {error_msg}\n\nPlease try another URL or provide the content directly."
            
            logger.warning(f"[URLAnalysis] Content unavailable: {error_msg}")
        
        # Create conversation if not provided
        conversation_id = request.conversation_id
        if not conversation_id:
            conversation = ConversationService.create_conversation(db, user.id)
            conversation_id = conversation.id
            logger.info(f"[URLAnalysis] Created new conversation: {conversation_id}")
        
        # Fetch previous conversations for context
        previous_conversations = ConversationService.get_previous_conversations(
            db,
            user.id,
            current_conversation_id=conversation_id,
            limit=5,
        )
        
        # Generate response
        chat_service = get_chat_service(db=db)
        assistant_response = chat_service.generate_response(
            user_message=message_content,
            user_email=user_email,
            conversation_id=conversation_id,
            user_id=user.id,
            previous_conversations=previous_conversations,
        )
        
        logger.info(f"[URLAnalysis] ✅ Analysis complete")
        return URLAnalysisResponse(
            user_message=request.user_message,
            assistant_response=assistant_response,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[URLAnalysis] Error analyzing URL: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "url_analysis_error", "message": str(e)},
        )
