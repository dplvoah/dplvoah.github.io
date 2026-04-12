"""Shared output writing helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json_record(
    *,
    output_path: Path,
    payload: dict[str, Any],
    error_cls: type[Exception],
    error_prefix: str,
) -> Path:
    """Write one JSON payload to a UTF-8 file with stable formatting."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        raise error_cls(f"{error_prefix}: {output_path}") from exc
    return output_path.resolve()

