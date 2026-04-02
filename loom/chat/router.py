"""FastAPI Chat router with SSE support."""

import asyncio
import json
from typing import Any, AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from loom.chat.organizer import Organizer, detect_organize_marker
from loom.chat.session import (
    ChatSession,
    build_system_prompt,
    session_store,
)
from loom.llm.client import Claude, Model
from loom.storage import DataStorage, InMemoryDataStorage, Profile
from loom.storage.repository import ProfileRepository

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Global instances (will be injected in production)
_claude: Claude | None = None
_storage: DataStorage | None = None


def get_claude() -> Claude:
    """Get Claude client instance."""
    global _claude
    if _claude is None:
        _claude = Claude()
    return _claude


def get_storage() -> DataStorage:
    """Get storage instance."""
    global _storage
    if _storage is None:
        _storage = InMemoryDataStorage()
    return _storage


def set_storage(storage: DataStorage) -> None:
    """Set storage instance (for dependency injection)."""
    global _storage
    _storage = storage


# Request/Response models
class MessageRequest(BaseModel):
    """Request body for sending a message."""

    message: str = Field(..., min_length=1)
    session_id: str | None = Field(default=None)
    language: str = Field(default="zh", description="'zh' or 'en'")


class ChatHistoryItem(BaseModel):
    """A single message in chat history."""

    role: str
    content: str
    timestamp: str


class ChatHistoryResponse(BaseModel):
    """Response for chat history endpoint."""

    session_id: str
    language: str
    messages: list[ChatHistoryItem]
    turn_count: int


class SSEEvent(BaseModel):
    """Server-Sent Event data structure."""

    type: str  # message, organizing, organized, error
    content: str = ""
    saved: dict[str, Any] | None = None


def format_sse(event: SSEEvent) -> str:
    """Format an SSE event for streaming."""
    data = event.model_dump(exclude_none=True)
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_chat_response(
    session: ChatSession,
    user_message: str,
    claude: Claude,
    storage: DataStorage,
    request: Request,
) -> AsyncGenerator[str, None]:
    """Stream chat response with SSE events.

    Handles:
    1. Streaming Claude's response
    2. Detecting [ORGANIZE] marker
    3. Triggering organize flow
    4. Proper cancellation when client disconnects

    Yields:
        SSE formatted strings
    """
    # Add user message to session
    session.add_user_message(user_message)

    # Check if we need to compress context
    if session.should_compress():
        await session.compress_context(claude)

    # Get existing experiences for context
    profile_repo = ProfileRepository(storage)
    profile_data = await profile_repo.get_full_profile(session.user_id)
    existing_experiences = profile_data.get("experiences", []) if profile_data else []

    # Build system prompt
    system_prompt = build_system_prompt(session, existing_experiences)

    # Get messages for API
    messages = session.get_messages_for_api()

    stream_context = None
    try:
        # Stream response from Claude
        full_response = ""

        stream_context = claude.client.messages.stream(
            model=Model.SONNET.value,
            max_tokens=2048,
            system=system_prompt,
            messages=messages,
        )

        async with stream_context as stream:
            async for text in stream.text_stream:
                # Check if client disconnected
                if await request.is_disconnected():
                    # Client disconnected, clean up and exit
                    return

                full_response += text
                # Stream each chunk as a message event
                yield format_sse(SSEEvent(type="message", content=text))

        # Check if client still connected before post-processing
        if await request.is_disconnected():
            return

        # Check for [ORGANIZE] marker after full response
        has_marker, cleaned_response = detect_organize_marker(full_response)

        # Add cleaned response to session
        session.add_assistant_message(cleaned_response)
        session_store.save(session)

        if has_marker:
            # Check if client still connected
            if await request.is_disconnected():
                return

            # Trigger organize flow - bilingual messages
            organizing_msg = (
                "Organizing your experience..."
                if session.language == "en"
                else "正在整理你的经历..."
            )
            yield format_sse(SSEEvent(type="organizing", content=organizing_msg))

            # Get or create profile
            profile = await storage.get_profile(session.user_id)
            if not profile:
                # Create default profile if not exists
                profile = Profile(
                    user_id=session.user_id,
                    name_en="User",
                )
                await storage.save_profile(profile)

            # Run organizer
            organizer = Organizer(claude, storage)
            result = await organizer.process(session, profile.id, session.user_id)

            # Check if client still connected
            if await request.is_disconnected():
                return

            yield format_sse(SSEEvent(
                type="organized",
                content=result["message"],
                saved=result["saved"],
            ))

            # Send follow-up message - bilingual
            follow_up = (
                "Great, I've organized that. Do you have any other experiences you'd like to discuss? "
                "Such as other work experiences, internships, or projects."
                if session.language == "en"
                else "好的，已经整理好了。你还有其他经历想聊吗？比如其他工作经历、实习或者项目。"
            )
            session.add_assistant_message(follow_up)
            session_store.save(session)

            yield format_sse(SSEEvent(type="message", content=follow_up))

    except asyncio.CancelledError:
        # Client disconnected, clean up gracefully
        return
    except Exception as e:
        if not await request.is_disconnected():
            yield format_sse(SSEEvent(type="error", content=str(e)))


@router.post("/message")
async def send_message(request: Request, body: MessageRequest) -> StreamingResponse:
    """Send a message and get streaming response.

    Returns SSE stream with events:
    - message: Streaming message content
    - organizing: Started organizing
    - organized: Finished organizing with saved data
    - error: Error occurred
    """
    print(f"[Chat API] Received message with language: {body.language}")
    try:
        from loom.services.logger import logger as loom_log
        await loom_log.info("user_action", "chat.message",
            f"Chat message ({len(body.content)} chars, lang={body.language})",
            session_id=body.session_id, char_len=len(body.content))
    except Exception:
        pass

    claude = get_claude()
    storage = get_storage()

    # Get or create session with language
    session = session_store.get_or_create(
        body.session_id,
        language=body.language,
    )

    print(f"[Chat API] Session language before update: {session.language}")

    # Update language if session exists but language changed
    if session.language != body.language:
        session.language = body.language
        session_store.save(session)
        print(f"[Chat API] Updated session language to: {session.language}")

    return StreamingResponse(
        stream_chat_response(session, body.message, claude, storage, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Session-Id": session.session_id,
            "X-Language": session.language,
        },
    )


@router.get("/history")
async def get_chat_history(
    session_id: str = Query(..., description="Session ID"),
) -> ChatHistoryResponse:
    """Get chat history for a session."""
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return ChatHistoryResponse(
        session_id=session.session_id,
        language=session.language,
        messages=[
            ChatHistoryItem(
                role=m.role,
                content=m.content,
                timestamp=m.timestamp.isoformat(),
            )
            for m in session.messages
        ],
        turn_count=session.turn_count,
    )


@router.delete("/session/{session_id}")
async def delete_session(session_id: str) -> dict[str, str]:
    """Delete a chat session."""
    deleted = session_store.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}


class RollbackRequest(BaseModel):
    """Request body for rolling back messages."""

    count: int = Field(default=2, ge=1, le=10, description="Number of messages to remove (default 2 = last user + assistant)")


@router.post("/session/{session_id}/rollback")
async def rollback_messages(session_id: str, body: RollbackRequest) -> dict[str, Any]:
    """Rollback (delete) the last N messages from a session.

    Typically used to remove the last user message and assistant response
    so the user can try again with a different message.

    Args:
        session_id: The session ID
        body: Contains count of messages to remove

    Returns:
        Updated session info
    """
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Remove the last N messages
    messages_to_remove = min(body.count, len(session.messages))
    if messages_to_remove > 0:
        session.messages = session.messages[:-messages_to_remove]
        # Adjust turn count (each user message is a turn)
        turns_removed = sum(1 for _ in range(messages_to_remove) if messages_to_remove > 0)
        session.turn_count = max(0, session.turn_count - (messages_to_remove // 2))
        session_store.save(session)

    return {
        "status": "rolled_back",
        "session_id": session_id,
        "messages_removed": messages_to_remove,
        "remaining_messages": len(session.messages),
    }


@router.get("/sessions")
async def list_sessions(user_id: str = Query(default="local")) -> list[dict[str, Any]]:
    """List all sessions for a user."""
    sessions = session_store.list_sessions(user_id)
    return [
        {
            "session_id": s.session_id,
            "language": s.language,
            "turn_count": s.turn_count,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat(),
            "current_focus": s.current_focus,
        }
        for s in sessions
    ]
