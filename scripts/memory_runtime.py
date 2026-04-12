"""Automatic temporary-memory updates after each authorized interaction."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from memory_access import MemoryAccessError, can_memory_update


ROOT_DIR: Final[Path] = Path(__file__).resolve().parent.parent
AI_CONTEXT_DIR: Final[Path] = ROOT_DIR / "ai_context"
MEMORY_DIR: Final[Path] = AI_CONTEXT_DIR / "memory"

INTERACTION_EVENTS_PATH: Final[Path] = MEMORY_DIR / "interaction_events.jsonl"
RECENT_MEMORY_PATH: Final[Path] = AI_CONTEXT_DIR / "recent_memory.md"
MAX_EVENTS_IN_RECENT: Final[int] = 10
MAX_SUMMARY_CHARS: Final[int] = 240


class MemoryRuntimeError(Exception):
    """Raised when runtime memory update fails."""


def trim_summary(text: str, *, limit: int = MAX_SUMMARY_CHARS) -> str:
    """Trim and compact text for event summary storage."""
    compact = " ".join(str(text).split()).strip()
    if len(compact) <= limit:
        return compact
    if limit <= 3:
        return compact[:limit]
    return compact[: limit - 3].rstrip() + "..."


def append_event_jsonl(event: dict[str, Any]) -> None:
    """Append one event object as JSON line."""
    try:
        INTERACTION_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with INTERACTION_EVENTS_PATH.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise MemoryRuntimeError(
            f"Failed to append interaction event: {INTERACTION_EVENTS_PATH}"
        ) from exc


def read_tail_lines(file_path: Path, *, max_lines: int, chunk_size: int = 4096) -> list[str]:
    """Read latest lines from a UTF-8 text file without loading the full file."""
    if max_lines <= 0:
        return []

    try:
        with file_path.open("rb") as fp:
            fp.seek(0, 2)
            file_size = fp.tell()
            if file_size <= 0:
                return []

            buffer = b""
            pointer = file_size
            newline_count = 0

            while pointer > 0 and newline_count <= max_lines:
                read_size = min(chunk_size, pointer)
                pointer -= read_size
                fp.seek(pointer)
                chunk = fp.read(read_size)
                buffer = chunk + buffer
                newline_count = buffer.count(b"\n")

        text = buffer.decode("utf-8", errors="ignore")
        lines = text.splitlines()
        if len(lines) <= max_lines:
            return lines
        return lines[-max_lines:]
    except OSError as exc:
        raise MemoryRuntimeError(f"Failed to read interaction event log: {file_path}") from exc


def read_last_events(limit: int = MAX_EVENTS_IN_RECENT) -> list[dict[str, Any]]:
    """Read and return the latest N events (newest first)."""
    if not INTERACTION_EVENTS_PATH.exists() or not INTERACTION_EVENTS_PATH.is_file():
        return []
    lines = read_tail_lines(
        INTERACTION_EVENTS_PATH,
        max_lines=max(limit * 3, limit),
    )

    events: list[dict[str, Any]] = []
    for raw in reversed(lines):
        text = raw.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            events.append(obj)
        if len(events) >= limit:
            break
    return events


def render_recent_memory(events: list[dict[str, Any]]) -> str:
    """Render compact temporary context markdown from recent events."""
    now_utc = datetime.now(timezone.utc).isoformat()
    lines: list[str] = [
        "# RECENT_MEMORY",
        "",
        "## 1. Runtime Window",
        f"- Last refresh (UTC): {now_utc}",
        f"- Source: {INTERACTION_EVENTS_PATH.relative_to(ROOT_DIR).as_posix()}",
        f"- Window size: latest {len(events)} events",
        "",
        "## 2. Latest Interaction Events (newest first)",
    ]

    if not events:
        lines.append("- No recent interaction events recorded yet.")
    else:
        for event in events:
            timestamp = str(event.get("timestamp", "")).strip() or "<unknown-time>"
            interaction_type = str(event.get("interaction_type", "")).strip() or "<unknown-type>"
            principal = str(event.get("principal_account", "")).strip() or "<unknown-account>"
            source = str(event.get("source_summary", "")).strip() or "<empty-source-summary>"
            ai = str(event.get("ai_summary", "")).strip() or "<empty-ai-summary>"
            reference = str(event.get("reference", "")).strip()
            lines.append(
                f"- [{timestamp}] type={interaction_type}; principal={principal}; "
                f"source={source}; ai={ai}"
            )
            if reference:
                lines.append(f"- reference: {reference}")

    lines.extend(
        [
            "",
            "## 3. Carry-Forward Guidance",
            "- Keep unresolved tensions from the latest events active in next replies.",
            "- Prefer recurring themes over one-off details when token budget is tight.",
            "- Treat this file as temporary context; migrate only repeated high-confidence signals.",
            "",
            "## 4. Expiration Notes",
            "- This file is replacement-oriented and auto-regenerated from recent events.",
            "- Stable facts belong in ai_context/memory/*.md, not here.",
            "- If events become noisy, prune interaction_events.jsonl and regenerate.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def refresh_recent_memory_from_events() -> None:
    """Rebuild recent_memory.md from latest interaction events."""
    events = read_last_events(limit=MAX_EVENTS_IN_RECENT)
    rendered = render_recent_memory(events)
    try:
        RECENT_MEMORY_PATH.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        raise MemoryRuntimeError(
            f"Failed to write recent memory file: {RECENT_MEMORY_PATH}"
        ) from exc


def record_interaction_event(
    *,
    principal_account: str,
    interaction_type: str,
    source_summary: str,
    ai_summary: str,
    reference: str = "",
) -> bool:
    """
    Record one interaction event and refresh temporary memory.

    Args:
        principal_account: Identity that interaction is about.
        interaction_type: Event type label.
        source_summary: Human-side concise summary.
        ai_summary: AI output concise summary.
        reference: Optional URL/slug/id.

    Returns:
        True when event is recorded; False when permission denies update.
    """
    try:
        if not can_memory_update(principal_account):
            return False
    except MemoryAccessError as exc:
        raise MemoryRuntimeError(f"Failed to evaluate memory update permission: {exc}") from exc

    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "principal_account": str(principal_account).strip(),
        "interaction_type": str(interaction_type).strip(),
        "source_summary": trim_summary(source_summary),
        "ai_summary": trim_summary(ai_summary),
        "reference": trim_summary(reference, limit=320),
    }
    append_event_jsonl(event)
    refresh_recent_memory_from_events()
    return True
