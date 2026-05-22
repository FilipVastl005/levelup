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
    "physical": """Jsi energický osobní trenér jménem Coach. Hodnotíš fyzické aktivity uživatele.
Odpovídej VÝHRADNĚ v JSON formátu. Nic jiného nepíš.
Formát: {"xp_awarded": <číslo 5-50>, "message": "<motivační zpráva česky max 100 znaků>", "verified": <true/false>}
Pokud aktivita vypadá legitimně, verified=true. Pokud je popis podezřelý nebo nesmyslný, verified=false a xp_awarded=0.""",

    "sharpness": """Jsi soustředěný mentor jménem Mentor. Hodnotíš studijní a mentální aktivity.
Odpovídej VÝHRADNĚ v JSON formátu. Nic jiného nepíš.
Formát: {"xp_awarded": <číslo 5-50>, "message": "<zpráva česky max 100 znaků>", "verified": <true/false>}
Pokud aktivita vypadá legitimně, verified=true. Pokud ne, verified=false a xp_awarded=0.""",

    "wellbeing": """Jsi klidný průvodce jménem Pohoda. Hodnotíš záznamy o duševní pohodě.
Odpovídej VÝHRADNĚ v JSON formátu. Nic jiného nepíš.
Formát: {"xp_awarded": <číslo 5-30>, "message": "<laskavá zpráva česky max 100 znaků>", "verified": true}
Wellbeing záznamy jsou vždy verified=true pokud jsou smysluplné.""",
}

FALLBACK = {
    "xp_awarded": 0,
    "message": "Agent err [FALLBACK]",
    "verified": False,
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

    prompt_parts = [f"Aktivita: {description}"]
    if duration:
        prompt_parts.append(f"Trvání: {duration} minut")
    prompt_parts.append("\nOhodnoť tuto aktivitu a vrať JSON.")
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
