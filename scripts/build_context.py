# Print contexts result only: ```python scripts/build_context.py```

# Write contexts result to a file: ```python scripts/build_context.py --write-file```

# Write contexts result to a custom file: ```python scripts/build_context.py --write-file --output ai_output/tmp/test_context.md```

# Purpose: Build a stable system context string from ai_context markdown files.

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Final


ROOT_DIR: Final[Path] = Path(__file__).resolve().parent.parent
AI_CONTEXT_DIR: Final[Path] = ROOT_DIR / "ai_context"
TMP_DIR: Final[Path] = ROOT_DIR / "ai_output" / "tmp"

PROFILE_PATH: Final[Path] = AI_CONTEXT_DIR / "profile.md"
PREFERENCES_PATH: Final[Path] = AI_CONTEXT_DIR / "preferences.md"
RECENT_MEMORY_PATH: Final[Path] = AI_CONTEXT_DIR / "recent_memory.md"


class ContextBuildError(Exception):
    """Raised when system context cannot be built correctly."""


def read_markdown_file(file_path: Path) -> str:
    """
    Read a markdown file as UTF-8 text and return stripped content.

    Args:
        file_path: Absolute or relative path to the markdown file.

    Returns:
        File content with surrounding whitespace removed.

    Raises:
        ContextBuildError: If the file does not exist, is not a file,
        cannot be decoded, or is empty after stripping.
    """
    if not file_path.exists():
        raise ContextBuildError(f"Missing required file: {file_path}")

    if not file_path.is_file():
        raise ContextBuildError(f"Path is not a file: {file_path}")

    try:
        content = file_path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ContextBuildError(f"Failed to decode file as UTF-8: {file_path}") from exc
    except OSError as exc:
        raise ContextBuildError(f"Failed to read file: {file_path}") from exc

    if not content:
        raise ContextBuildError(f"File is empty: {file_path}")

    return content


def build_system_context() -> str:
    """
    Build the final system context from three markdown files.

    Returns:
        A single formatted system context string.

    Raises:
        ContextBuildError: If any required file is invalid.
    """
    profile_text = read_markdown_file(PROFILE_PATH)
    preferences_text = read_markdown_file(PREFERENCES_PATH)
    recent_memory_text = read_markdown_file(RECENT_MEMORY_PATH)

    sections = [
        "# PROFILE",
        profile_text,
        "",
        "# PREFERENCES",
        preferences_text,
        "",
        "# RECENT_MEMORY",
        recent_memory_text,
    ]

    return "\n".join(sections).strip()


def write_context_file(context_text: str, output_path: Path) -> Path:
    """
    Write context text to a UTF-8 file.

    Args:
        context_text: Final system context string.
        output_path: Destination file path.

    Returns:
        The resolved output path.

    Raises:
        ContextBuildError: If the file cannot be written.
    """
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(context_text, encoding="utf-8")
    except OSError as exc:
        raise ContextBuildError(f"Failed to write context file: {output_path}") from exc

    return output_path.resolve()


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments.

    Returns:
        Parsed CLI namespace.
    """
    parser = argparse.ArgumentParser(
        description="Build system context from ai_context markdown files."
    )
    parser.add_argument(
        "--write-file",
        action="store_true",
        help="Write the built context to a temporary file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=TMP_DIR / "system_context.md",
        help="Output file path used when --write-file is enabled.",
    )
    return parser.parse_args()


def main() -> int:
    """
    CLI entry point.

    Returns:
        Process exit code.
    """
    args = parse_args()

    try:
        context = build_system_context()

        if args.write_file:
            output_path = write_context_file(context, args.output)
            print(f"[build_context.py] Context written to: {output_path}")
        else:
            print(context)

        return 0

    except ContextBuildError as exc:
        print(f"[build_context.py] ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())