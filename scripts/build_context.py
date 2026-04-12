# Print contexts result only: ```python scripts/build_context.py```
#
# Write contexts result to a file:
# ```python scripts/build_context.py --write-file```
#
# Write contexts result to a custom file:
# ```python scripts/build_context.py --write-file --output ai_output/tmp/test_context.md```
#
# Purpose: Build a retrieval-policy-driven system context string.

from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import yaml

from memory_access import MemoryAccessError, can_personalized_read


ROOT_DIR: Final[Path] = Path(__file__).resolve().parent.parent
AI_CONTEXT_DIR: Final[Path] = ROOT_DIR / "ai_context"
TMP_DIR: Final[Path] = ROOT_DIR / "ai_output" / "tmp"

RETRIEVAL_POLICY_PATH: Final[Path] = AI_CONTEXT_DIR / "context_retrieval_policy.yaml"
DEFAULT_MODE: Final[str] = "comment"
DEFAULT_TARGET_ACCOUNT: Final[str] = "dplvoah"


@dataclass(frozen=True)
class ModePolicy:
    """One mode retrieval rule from policy yaml."""

    always_on: list[Path]
    optional: list[Path]
    max_chars_by_file: dict[str, int]
    max_total_chars: int | None


@dataclass(frozen=True)
class RetrievalPolicy:
    """Global retrieval configuration."""

    common_always_on: list[Path]
    modes: dict[str, ModePolicy]
    default_max_chars_per_file: int
    default_max_total_chars: int | None


class ContextBuildError(Exception):
    """Raised when system context cannot be built correctly."""


def to_repo_relative(path: Path) -> str:
    """Return a stable repo-relative path string."""
    return path.resolve().relative_to(ROOT_DIR.resolve()).as_posix()


def resolve_repo_path(path_text: str) -> Path:
    """
    Resolve a policy path to an absolute repository path.

    Args:
        path_text: Repo-relative path in policy file.

    Returns:
        Absolute normalized path.

    Raises:
        ContextBuildError: If path is empty or outside repository.
    """
    normalized = str(path_text).strip()
    if not normalized:
        raise ContextBuildError("Context retrieval policy contains an empty path entry.")

    candidate = (ROOT_DIR / normalized).resolve()
    try:
        candidate.relative_to(ROOT_DIR.resolve())
    except ValueError as exc:
        raise ContextBuildError(
            "Context retrieval path escapes repository root: "
            f"{normalized}"
        ) from exc
    return candidate


def parse_policy_paths(value: Any, *, field_name: str) -> list[Path]:
    """
    Parse list of paths from YAML field.

    Args:
        value: Raw field value.
        field_name: Error label.

    Returns:
        List of resolved paths.

    Raises:
        ContextBuildError: If value type is invalid.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise ContextBuildError(f"'{field_name}' must be a list of file paths.")
    parsed: list[Path] = []
    for item in value:
        if not isinstance(item, str):
            raise ContextBuildError(f"'{field_name}' must contain string paths only.")
        parsed.append(resolve_repo_path(item))
    return parsed


def parse_max_chars_map(value: Any, *, field_name: str) -> dict[str, int]:
    """
    Parse file-level max chars mapping.

    Args:
        value: Raw yaml mapping.
        field_name: Error label.

    Returns:
        Repo-relative path -> positive max chars.
    """
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ContextBuildError(f"'{field_name}' must be a mapping.")

    parsed: dict[str, int] = {}
    for key, raw_limit in value.items():
        if not isinstance(key, str):
            raise ContextBuildError(f"'{field_name}' keys must be string file paths.")
        path = resolve_repo_path(key)
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError) as exc:
            raise ContextBuildError(
                f"'{field_name}' limit must be integer for path '{key}'."
            ) from exc
        if limit <= 0:
            raise ContextBuildError(
                f"'{field_name}' limit must be > 0 for path '{key}'."
            )
        parsed[to_repo_relative(path)] = limit
    return parsed


def read_markdown_file(file_path: Path, *, required: bool) -> str:
    """
    Read a markdown file as UTF-8 text.

    Args:
        file_path: Target file path.
        required: Whether missing/empty file is fatal.

    Returns:
        Stripped content, or empty string for optional missing/empty files.

    Raises:
        ContextBuildError: If required file is invalid.
    """
    if not file_path.exists() or not file_path.is_file():
        if required:
            raise ContextBuildError(f"Missing required context file: {file_path}")
        return ""

    try:
        content = file_path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ContextBuildError(f"Failed to decode UTF-8 file: {file_path}") from exc
    except OSError as exc:
        raise ContextBuildError(f"Failed to read file: {file_path}") from exc

    if not content and required:
        raise ContextBuildError(f"Required context file is empty: {file_path}")
    return content


def trim_text(text: str, limit: int) -> str:
    """
    Trim text to char limit with explicit truncation marker.

    Args:
        text: Input text.
        limit: Max char count.

    Returns:
        Trimmed text.
    """
    if len(text) <= limit:
        return text
    if limit <= 20:
        return text[:limit]
    marker = "\n\n[TRUNCATED]"
    head_limit = max(1, limit - len(marker))
    return text[:head_limit].rstrip() + marker


def dedupe_paths(paths: list[Path]) -> list[Path]:
    """Dedupe paths while preserving order."""
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


@lru_cache(maxsize=1)
def load_retrieval_policy() -> RetrievalPolicy:
    """
    Load and validate context retrieval policy yaml.

    Returns:
        Parsed retrieval policy object.

    Raises:
        ContextBuildError: If policy file is missing or malformed.
    """
    if not RETRIEVAL_POLICY_PATH.exists() or not RETRIEVAL_POLICY_PATH.is_file():
        raise ContextBuildError(
            f"Missing context retrieval policy: {RETRIEVAL_POLICY_PATH}"
        )

    try:
        raw = yaml.safe_load(RETRIEVAL_POLICY_PATH.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise ContextBuildError(
            f"Failed to read context retrieval policy: {RETRIEVAL_POLICY_PATH}"
        ) from exc
    except yaml.YAMLError as exc:
        raise ContextBuildError(
            f"Invalid YAML in context retrieval policy: {RETRIEVAL_POLICY_PATH}"
        ) from exc

    if not isinstance(raw, dict):
        raise ContextBuildError("Context retrieval policy root must be a mapping.")

    defaults = raw.get("defaults") or {}
    if defaults and not isinstance(defaults, dict):
        raise ContextBuildError("'defaults' in retrieval policy must be a mapping.")

    default_max_chars_per_file = int(defaults.get("max_chars_per_file", 3500))
    if default_max_chars_per_file <= 0:
        raise ContextBuildError("'defaults.max_chars_per_file' must be > 0.")

    raw_default_total = defaults.get("max_total_chars")
    default_max_total_chars: int | None
    if raw_default_total is None:
        default_max_total_chars = None
    else:
        default_max_total_chars = int(raw_default_total)
        if default_max_total_chars <= 0:
            raise ContextBuildError("'defaults.max_total_chars' must be > 0.")

    common_always_on = parse_policy_paths(
        raw.get("common_always_on"),
        field_name="common_always_on",
    )

    modes_raw = raw.get("modes")
    if not isinstance(modes_raw, dict) or not modes_raw:
        raise ContextBuildError("'modes' in retrieval policy must be a non-empty mapping.")

    modes: dict[str, ModePolicy] = {}
    for mode_name, mode_value in modes_raw.items():
        if not isinstance(mode_name, str) or not mode_name.strip():
            raise ContextBuildError("Every mode key in retrieval policy must be non-empty.")
        if not isinstance(mode_value, dict):
            raise ContextBuildError(f"Mode '{mode_name}' config must be a mapping.")

        always_on = parse_policy_paths(
            mode_value.get("always_on"),
            field_name=f"modes.{mode_name}.always_on",
        )
        optional = parse_policy_paths(
            mode_value.get("optional"),
            field_name=f"modes.{mode_name}.optional",
        )
        max_chars_by_file = parse_max_chars_map(
            mode_value.get("max_chars"),
            field_name=f"modes.{mode_name}.max_chars",
        )

        raw_mode_total = mode_value.get("max_total_chars")
        mode_total: int | None
        if raw_mode_total is None:
            mode_total = None
        else:
            mode_total = int(raw_mode_total)
            if mode_total <= 0:
                raise ContextBuildError(
                    f"'modes.{mode_name}.max_total_chars' must be > 0."
                )

        modes[mode_name.strip()] = ModePolicy(
            always_on=always_on,
            optional=optional,
            max_chars_by_file=max_chars_by_file,
            max_total_chars=mode_total,
        )

    return RetrievalPolicy(
        common_always_on=common_always_on,
        modes=modes,
        default_max_chars_per_file=default_max_chars_per_file,
        default_max_total_chars=default_max_total_chars,
    )


def resolve_mode_name(
    *,
    requested_mode: str,
    target_account: str,
    policy: RetrievalPolicy,
) -> str:
    """
    Resolve effective mode based on identity permissions.

    Args:
        requested_mode: Requested mode (comment/reply/...).
        target_account: Identity key used for permission check.
        policy: Loaded retrieval policy.

    Returns:
        Effective mode name in policy.

    Raises:
        ContextBuildError: If no compatible mode exists.
    """
    normalized_mode = requested_mode.strip() or DEFAULT_MODE
    normalized_target = target_account.strip() or DEFAULT_TARGET_ACCOUNT

    try:
        has_personalized_read = can_personalized_read(normalized_target)
    except MemoryAccessError as exc:
        raise ContextBuildError(
            f"Failed to evaluate memory access permission: {exc}"
        ) from exc

    if has_personalized_read:
        if normalized_mode not in policy.modes:
            raise ContextBuildError(
                f"Requested mode '{normalized_mode}' is not defined in retrieval policy."
            )
        return normalized_mode

    generic_mode = f"generic_{normalized_mode}"
    if generic_mode in policy.modes:
        return generic_mode
    if "generic" in policy.modes:
        return "generic"
    raise ContextBuildError(
        "Target account is not authorized for personalized memory and "
        "no generic fallback mode is defined."
    )


def build_system_context(
    *,
    mode: str = DEFAULT_MODE,
    target_account: str = DEFAULT_TARGET_ACCOUNT,
    include_optional: bool = True,
) -> str:
    """
    Build final system context using retrieval policy and account permissions.

    Args:
        mode: Retrieval mode, e.g. comment/reply/reflection.
        target_account: Identity account for permission gating.
        include_optional: Whether optional files should be loaded.

    Returns:
        A single formatted system context string.

    Raises:
        ContextBuildError: If required context file or policy is invalid.
    """
    policy = load_retrieval_policy()
    effective_mode = resolve_mode_name(
        requested_mode=mode,
        target_account=target_account,
        policy=policy,
    )
    mode_policy = policy.modes[effective_mode]

    always_on_paths = dedupe_paths(policy.common_always_on + mode_policy.always_on)
    optional_paths = dedupe_paths(mode_policy.optional) if include_optional else []

    all_paths: list[tuple[Path, bool]] = [(path, True) for path in always_on_paths]
    all_paths.extend((path, False) for path in optional_paths)

    max_total_chars = (
        mode_policy.max_total_chars
        if mode_policy.max_total_chars is not None
        else policy.default_max_total_chars
    )

    sections: list[str] = []
    total_chars = 0

    for file_path, required in all_paths:
        relative_path = to_repo_relative(file_path)
        content = read_markdown_file(file_path, required=required)
        if not content:
            continue

        max_chars_for_file = mode_policy.max_chars_by_file.get(
            relative_path,
            policy.default_max_chars_per_file,
        )
        if max_chars_for_file <= 0:
            raise ContextBuildError(
                f"Invalid max chars for file '{relative_path}': {max_chars_for_file}"
            )
        content = trim_text(content, max_chars_for_file)

        if max_total_chars is not None:
            remaining = max_total_chars - total_chars
            if remaining <= 0:
                if required:
                    raise ContextBuildError(
                        "Context max_total_chars exhausted before required files loaded. "
                        f"mode={effective_mode}, target_account={target_account}"
                    )
                continue
            if len(content) > remaining:
                content = trim_text(content, remaining)
                if not content and required:
                    raise ContextBuildError(
                        f"Required context file cannot fit under max_total_chars: {relative_path}"
                    )

        sections.append(f"# {relative_path}")
        sections.append(content)
        total_chars += len(content)

    if not sections:
        raise ContextBuildError(
            "No context content loaded; check retrieval policy and source files."
        )

    return "\n\n".join(sections).strip()


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
        description="Build system context from retrieval policy and identity permission."
    )
    parser.add_argument(
        "--mode",
        default=DEFAULT_MODE,
        type=str,
        help="Context mode (comment/reply/reflection/challenge/bridge).",
    )
    parser.add_argument(
        "--target-account",
        default=DEFAULT_TARGET_ACCOUNT,
        type=str,
        help="Identity account used for personalized-memory permission checks.",
    )
    parser.add_argument(
        "--exclude-optional",
        action="store_true",
        help="Exclude optional context files from retrieval policy.",
    )
    parser.add_argument(
        "--write-file",
        action="store_true",
        help="Write built context to a temporary file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=TMP_DIR / "system_context.md",
        help="Output path used when --write-file is enabled.",
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
        context = build_system_context(
            mode=args.mode,
            target_account=args.target_account,
            include_optional=not args.exclude_optional,
        )

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
