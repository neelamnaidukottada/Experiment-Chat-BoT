"""Pydantic schemas for chat API requests and responses."""

from pydantic import BaseModel, Field


class ChatMessageRequest(BaseModel):
    """Request schema for sending a chat message."""

    user_message: str = Field(..., min_length=1, max_length=10000)


class ChatMessageResponse(BaseModel):
    """Response schema for chat message response."""

    user_message: str
    assistant_response: str
