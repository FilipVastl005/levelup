"""
services/ollama.py — Ollama LLaVA integration for LevelUp
Improved JSON extraction with multiple fallback strategies.
"""

import os
import json
import base64
import re
import httpx
import logging

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
MODEL = "llava"

SYSTEM_PROMPTS = {
    "physical": """You are an energetic personal trainer called Coach. You evaluate physical activities.
Reply ONLY with a JSON object. No other text before or after.
Format: {"xp_awarded": <number 5-50>, "message": "<short motivational message max 100 chars>", "verified": <true/false>}
If the activity sounds legitimate, set verified=true. If the description is nonsensical or suspicious, set verified=false and xp_awarded=0.
If an image is provided, use it to verify the activity.""",

    "sharpness": """You are a focused mentor called Mentor. You evaluate study and mental activities.
Reply ONLY with a JSON object. No other text before or after.
Format: {"xp_awarded": <number 5-50>, "message": "<short encouraging message max 100 chars>", "verified": <true/false>}
If the activity sounds legitimate, set verified=true. If not, set verified=false and xp_awarded=0.
Award more XP for longer or more difficult study sessions.""",

    "wellbeing": """You are a calm wellbeing guide called Harmony. You evaluate mental wellbeing journal entries.
Reply ONLY with a JSON object. No other text before or after.
Format: {"xp_awarded": <number 5-30>, "message": "<short kind message max 100 chars>", "verified": true}
Wellbeing entries are always verified=true as long as they are genuine and meaningful.""",
}

FALLBACK = {
    "xp_awarded": 10,
    "message": "Great work! Keep it up, every step counts.",
    "verified": True,
}


def _extract_json(text: str) -> dict | None:
    """Try multiple strategies to extract JSON from LLaVA output."""
    # Strategy 1: parse whole response
    try:
        return json.loads(text.strip())
    except Exception:
        pass

    # Strategy 2: find first {...} block
    match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass

    # Strategy 3: extract individual fields manually
    xp_match = re.search(r'"xp_awarded"\s*:\s*(\d+)', text)
    msg_match = re.search(r'"message"\s*:\s*"([^"]+)"', text)
    ver_match = re.search(r'"verified"\s*:\s*(true|false)', text, re.IGNORECASE)

    if xp_match and msg_match:
        return {
            "xp_awarded": int(xp_match.group(1)),
            "message": msg_match.group(1),
            "verified": ver_match.group(1).lower() == "true" if ver_match else True,
        }

    return None


async def evaluate_activity(
    category: str,
    description: str,
    screenshot_path: str | None = None,
    duration: int | None = None,
) -> dict:
    """Send activity to Ollama for evaluation. Returns XP decision dict."""
    system = SYSTEM_PROMPTS.get(category, SYSTEM_PROMPTS["physical"])

    prompt_parts = [f"Activity: {description}"]
    if duration:
        prompt_parts.append(f"Duration: {duration} minutes")
    prompt_parts.append("\nEvaluate this activity and return a JSON object.")
    prompt = "\n".join(prompt_parts)

    payload: dict = {
        "model": MODEL,
        "prompt": f"{system}\n\n{prompt}",
        "stream": False,
    }

    # Attach image if provided
    if screenshot_path and os.path.exists(screenshot_path):
        try:
            with open(screenshot_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            payload["images"] = [img_b64]
        except Exception as e:
            logger.warning(f"Could not read screenshot {screenshot_path}: {e}")

    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("response", "")
            logger.info(f"Ollama raw response: {raw[:200]}")

            result = _extract_json(raw)
            if result:
                # Validate and clamp values
                result["xp_awarded"] = max(0, min(100, int(result.get("xp_awarded", 10))))
                result["message"] = str(result.get("message", FALLBACK["message"]))[:200]
                result["verified"] = bool(result.get("verified", True))
                return result
            else:
                logger.warning(f"No JSON found in Ollama response: {raw[:300]}")
                return FALLBACK

    except httpx.TimeoutException:
        logger.error("Ollama request timed out")
        return FALLBACK
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        return FALLBACK
