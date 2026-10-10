from __future__ import annotations

import os
import json
import logging
import requests
from dotenv import load_dotenv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)

logger = logging.getLogger(__name__)


def get_llm_config() -> dict[str, str]:
    api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
    base_url = os.getenv("OPENROUTER_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://openrouter.ai/api/v1"
    model = os.getenv("OPENROUTER_MODEL") or os.getenv("MODEL_NAME") or "google/gemini-2.5-flash"
    return {
        "api_key": api_key.strip(),
        "base_url": base_url.rstrip("/"),
        "model": model.strip(),
    }


def call_llm(
    prompt: str,
    system_prompt: str = "You are an enterprise AI Procurement Copilot. Follow all procurement rules strictly.",
    response_json: bool = False,
    timeout_seconds: float = 15.0,
) -> str | None:
    """Invokes OpenRouter / OpenAI-compatible endpoint. Returns text or None if unavailable."""
    config = get_llm_config()
    api_key = config["api_key"]
    if not api_key:
        return None

    endpoint = f"{config['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/fde-course/procurement-copilot",
        "X-Title": "FDE AI Procurement Copilot",
    }

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    payload: dict = {
        "model": config["model"],
        "messages": messages,
        "temperature": 0.1,
    }
    if response_json:
        payload["response_format"] = {"type": "json_object"}

    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout_seconds)
        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        else:
            logger.warning(f"LLM call failed with status {response.status_code}: {response.text}")
            return None
    except Exception as exc:
        logger.warning(f"LLM invocation exception: {exc}")
        return None
