"""Shared GitHub GraphQL utilities."""

from __future__ import annotations

import json
import os
from typing import Any, Final

import requests
from dotenv import load_dotenv


GITHUB_GRAPHQL_API_URL: Final[str] = "https://api.github.com/graphql"
GITHUB_REQUEST_TIMEOUT_SECONDS: Final[int] = 60


def load_ai_github_token(*, error_cls: type[Exception]) -> str:
    """Load AI GitHub token from env/.env."""
    load_dotenv()
    token = os.getenv("AI_GITHUB_TOKEN", "").strip()
    if not token:
        raise error_cls("Missing AI_GITHUB_TOKEN. Set it in environment or .env file.")
    return token


def execute_github_graphql_query(
    *,
    token: str,
    query: str,
    variables: dict[str, Any],
    error_cls: type[Exception],
) -> dict[str, Any]:
    """Execute one GitHub GraphQL request and return parsed JSON."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
    }
    payload = {
        "query": query,
        "variables": variables,
    }

    try:
        response = requests.post(
            GITHUB_GRAPHQL_API_URL,
            headers=headers,
            json=payload,
            timeout=GITHUB_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise error_cls(f"GitHub GraphQL request failed: {exc}") from exc

    if response.status_code != 200:
        raise error_cls(f"GitHub GraphQL API returned {response.status_code}: {response.text}")

    try:
        data = response.json()
    except ValueError as exc:
        raise error_cls("Failed to decode GitHub GraphQL JSON response.") from exc

    if "errors" in data and data["errors"]:
        raise error_cls(
            "GitHub GraphQL returned errors: "
            f"{json.dumps(data['errors'], ensure_ascii=False)}"
        )
    return data

