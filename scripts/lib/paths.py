"""Shared filesystem paths for scripts."""

from __future__ import annotations

from pathlib import Path
from typing import Final


ROOT_DIR: Final[Path] = Path(__file__).resolve().parent.parent.parent
AI_CONTEXT_DIR: Final[Path] = ROOT_DIR / "ai_context"
BLOG_DIR: Final[Path] = ROOT_DIR / "src" / "content" / "blog"
AI_OUTPUT_DIR: Final[Path] = ROOT_DIR / "ai_output"

