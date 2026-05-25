"""
routers/coach.py — Free-form AI Coach chat endpoint
Calls Ollama directly (no queue, instant response).
"""

import logging
import httpx
import json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from services.ollama import client, OLLAMA_URL, MODEL

router = APIRouter()
logger = logging.getLogger(__name__)

COACH_SYSTEM = """You are an enthusiastic personal coach called Coach inside the LevelUp app.
The user tracks physical fitness, studying (sharpness), and mental wellbeing.
They earn XP for their activities. Be encouraging, concise, and practical.
Keep replies under 120 words. Do not use markdown formatting — plain text only.
If the user writes in a language other than English, gently remind them that English works best."""


class ChatRequest(BaseModel):
    message: str
    history: list = []
    user_stats: dict = {}


def _get_current_user(request: Request):
    from services import db
    token = request.cookies.get("session_token")
    if not token:
        return None
    return db.get_session_user(token)


@router.post("/coach/chat")
async def coach_chat(request: Request, body: ChatRequest):
    user = _get_current_user(request)
    if not user:
        return JSONResponse({"status": "error", "reply": "Not logged in."}, status_code=401)

    if len(body.message.strip()) < 2:
        return JSONResponse({"reply": "Please type a message."})

    # Build context string from user stats
    stats = body.user_stats
    context = (
        f"User stats — Physical Lvl: {stats.get('physical_level', '?')}, "
        f"Sharpness Lvl: {stats.get('sharpness_level', '?')}, "
        f"Wellbeing Lvl: {stats.get('wellbeing_level', '?')}, "
        f"Total XP: {stats.get('total_xp', '?')}, "
        f"Streak: {stats.get('current_streak', '?')} days."
    )

    # Build conversation history string (last 6 messages for brevity)
    history_lines = []
    for msg in body.history[-6:]:
        role = "User" if msg.get("role") == "user" else "Coach"
        history_lines.append(f"{role}: {msg.get('text', '')}")
    history_str = "\n".join(history_lines)

    prompt = f"""{COACH_SYSTEM}

{context}

Conversation so far:
{history_str}

User: {body.message.strip()}
Coach:"""

    async def generate():
        try:
            logger.info(f"Streaming coach chat request to Ollama: {OLLAMA_URL}")
            async with client.stream(
                "POST",
                f"{OLLAMA_URL}/api/generate",
                json={"model": MODEL, "prompt": prompt, "stream": True},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        chunk = data.get("response", "")
                        if chunk:
                            yield chunk
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"\n[Error: {type(e).__name__}. Try again later.]"

    return StreamingResponse(generate(), media_type="text/plain")
