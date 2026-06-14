from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.assistant.agent_service import AgentService
from app.services.assistant.memory_service import DEFAULT_THREAD_ID

router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class AssistantMessageRequest(BaseModel):
    content: str = Field(..., min_length=0, max_length=8000)
    confirm_action_id: Optional[int] = None


class AssistantMessageResponse(BaseModel):
    ok: bool = True
    type: str = "answer"
    content: str = ""
    message_id: Optional[int] = None
    tool_runs: list = Field(default_factory=list)
    pending_confirm: Optional[dict] = None
    error: Optional[str] = None


@router.get("/status")
async def assistant_status():
    return await AgentService().status()


@router.get("/threads/{thread_id}/messages")
async def assistant_messages(thread_id: str = DEFAULT_THREAD_ID):
    return {"thread_id": thread_id, "messages": await AgentService().list_messages(thread_id)}


@router.post("/threads/{thread_id}/messages", response_model=AssistantMessageResponse)
async def assistant_send_message(
    thread_id: str,
    body: AssistantMessageRequest,
):
    if thread_id != DEFAULT_THREAD_ID:
        raise HTTPException(status_code=404, detail="Nieznany wątek")
    result = await AgentService().handle_message(
        body.content,
        thread_id=thread_id,
        confirm_action_id=body.confirm_action_id,
    )
    if not result.get("ok") and result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])
    return AssistantMessageResponse(**{k: v for k, v in result.items() if k in AssistantMessageResponse.model_fields})


@router.get("/memory")
async def assistant_memory_list():
    from app.services.assistant.memory_service import MemoryService

    facts = await MemoryService().list_facts()
    return {"facts": facts, "count": len(facts)}


@router.delete("/memory/{memory_id}")
async def assistant_memory_delete(memory_id: int):
    from app.services.assistant.memory_service import MemoryService

    ok = await MemoryService().delete_fact(memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Nie znaleziono faktu")
    return {"deleted": True, "id": memory_id}
