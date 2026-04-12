"""Shared AI generation defaults and validation markers."""

from __future__ import annotations

from typing import Final


DEEPSEEK_API_URL: Final[str] = "https://api.deepseek.com/chat/completions"
DEEPSEEK_DEFAULT_MODEL: Final[str] = "deepseek-chat"

COMMENT_DEFAULT_TEMPERATURE: Final[float] = 0.9
COMMENT_DEFAULT_MAX_TOKENS: Final[int] = 800
COMMENT_REQUEST_TIMEOUT_SECONDS: Final[int] = 60

REPLY_DEFAULT_TEMPERATURE: Final[float] = 0.9
REPLY_DEFAULT_MAX_TOKENS: Final[int] = 800
REPLY_REQUEST_TIMEOUT_SECONDS: Final[int] = 60

POST_DEFAULT_TEMPERATURE: Final[float] = 0.8
POST_DEFAULT_MAX_TOKENS: Final[int] = 2200
POST_REQUEST_TIMEOUT_SECONDS: Final[int] = 90

HUMAN_IDENTITY_CLAIM_MARKERS: Final[list[str]] = [
    "作为人类",
    "身为人类",
    "我作为人类",
    "我们人类",
    "as a human",
    "as humans",
    "i am human",
    "i'm human",
    "we humans",
]

