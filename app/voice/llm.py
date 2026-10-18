from __future__ import annotations

import logging

import httpx

from app.config import Settings

logger = logging.getLogger("harbor.llm")


def rephrase(settings: Settings, lang: str, meaning: str) -> str:
    """Soften a scripted line. The meaning stays; the model may not add facts."""
    target = settings.llm_target()
    if target is None or not meaning.strip():
        return meaning
    base_url, api_key, model = target
    language = "Spanish" if lang == "es" else "English"
    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "temperature": 0.4,
                "max_tokens": 120,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are the voice of a clinic front desk. "
                            f"Say the user's meaning naturally in {language}. "
                            "One or two short sentences. Do not add questions, names, "
                            "or facts that are not in the meaning."
                        ),
                    },
                    {"role": "user", "content": meaning},
                ],
            },
            timeout=4.0,
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        logger.exception("llm rephrase failed; using the scripted line")
        return meaning
    if not text or len(text) > 400:
        return meaning
    return text
