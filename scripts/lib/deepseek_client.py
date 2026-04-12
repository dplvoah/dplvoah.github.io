"""Shared DeepSeek API helpers."""

from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv

from lib.ai_defaults import DEEPSEEK_API_URL


def load_deepseek_api_key(*, error_cls: type[Exception]) -> str:
    """Load DeepSeek key from env/.env with consistent error handling."""
    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise error_cls("Missing DEEPSEEK_API_KEY. Set it in environment or .env file.")
    return api_key


def call_deepseek_chat_completion(
    *,
    api_key: str,
    system_context: str,
    user_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout_seconds: int,
    error_cls: type[Exception],
) -> dict[str, Any]:
    """Call DeepSeek chat completion API and return parsed JSON."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_context},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }

    try:
        response = requests.post(
            DEEPSEEK_API_URL,
            headers=headers,
            json=payload,
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        raise error_cls(f"DeepSeek request failed: {exc}") from exc

    if response.status_code != 200:
        raise error_cls(f"DeepSeek API returned {response.status_code}: {response.text}")

    try:
        return response.json()
    except ValueError as exc:
        raise error_cls("Failed to decode DeepSeek JSON response.") from exc

