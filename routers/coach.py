"""
routers/coach.py — Free-form AI Coach chat endpoint
Calls Ollama directly (no queue, instant response).
"""

import os
import logging
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
MODEL = "llava"

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

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": MODEL, "prompt": prompt, "stream": False},
            )
            resp.raise_for_status()
            data = resp.json()
            reply = data.get("response", "").strip()

            # Clean up any accidental "Coach:" prefix the model might add
            if reply.lower().startswith("coach:"):
                reply = reply[6:].strip()

            if not reply:
                reply = "I'm not sure how to answer that. Try asking about your training or study habits!"

            return JSONResponse({"reply": reply[:500]})

    except httpx.TimeoutException:
        logger.error("Coach chat timed out")
        return JSONResponse({"reply": "I'm thinking too hard right now — try again in a moment!"})
    except Exception as e:
        logger.error(f"Coach chat error: {e}")
        return JSONResponse({"reply": "Something went wrong on my end. Try again!"})
