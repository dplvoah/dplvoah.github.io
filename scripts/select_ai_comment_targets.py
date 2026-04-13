# Purpose: Select blog slugs that need AI comment refresh based on author and significant changes.

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Final

import yaml


ROOT_DIR: Final[Path] = Path(__file__).resolve().parent.parent
BLOG_DIR: Final[Path] = ROOT_DIR / "src" / "content" / "blog"
DEFAULT_COMMENT_RECORD_DIR: Final[Path] = ROOT_DIR / "ai_output" / "comments"
FRONTMATTER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$",
    re.DOTALL,
)


class SelectCommentTargetError(Exception):
    """Raised when target selection fails."""


@dataclass(frozen=True)
class ParsedPostSnapshot:
    """Minimal parsed post fields used for significance comparison."""

    title: str
    description: str
    author: str
    pub_date: str
    group: str
    tags: tuple[str, ...]
    draft: bool
    body: str


def normalize_text(text: str) -> str:
    """
    Normalize text for significance comparison.

    Args:
        text: Raw text.

    Returns:
        Normalized text.
    """
    return re.sub(r"\s+", " ", text).strip()


def parse_markdown_snapshot(raw_text: str, source: str) -> ParsedPostSnapshot:
    """
    Parse markdown snapshot from raw text.

    Args:
        raw_text: Markdown content.
        source: Source label for errors.

    Returns:
        Parsed post snapshot.

    Raises:
        SelectCommentTargetError: If parse or required fields fail.
    """
    match = FRONTMATTER_PATTERN.match(raw_text)
    if not match:
        raise SelectCommentTargetError(f"Invalid frontmatter format: {source}")

    frontmatter_text, body_text = match.groups()
    try:
        frontmatter = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as exc:
        raise SelectCommentTargetError(f"Invalid YAML in {source}") from exc

    if not isinstance(frontmatter, dict):
        raise SelectCommentTargetError(f"Frontmatter is not an object: {source}")

    title = str(frontmatter.get("title", "")).strip()
    description = str(frontmatter.get("description", "")).strip()
    author = str(frontmatter.get("author", "")).strip()
    pub_date = str(frontmatter.get("pubDate", frontmatter.get("date", ""))).strip()
    group = str(frontmatter.get("group", "")).strip()
    draft = bool(frontmatter.get("draft", False))
    raw_tags = frontmatter.get("tags", [])
    tags: tuple[str, ...]
    if isinstance(raw_tags, list):
        tags = tuple(str(item).strip() for item in raw_tags if str(item).strip())
    else:
        tags = tuple()
    body = body_text.strip()

    if not title:
        raise SelectCommentTargetError(f"Missing title in {source}")
    if not description:
        raise SelectCommentTargetError(f"Missing description in {source}")
    if not author:
        raise SelectCommentTargetError(f"Missing author in {source}")
    if not body:
        raise SelectCommentTargetError(f"Empty body in {source}")

    return ParsedPostSnapshot(
        title=title,
        description=description,
        author=author,
        pub_date=pub_date,
        group=group,
        tags=tags,
        draft=draft,
        body=body,
    )


def run_git_text(args: list[str]) -> tuple[int, str]:
    """
    Run git command and capture text output.

    Args:
        args: Git args without leading "git".

    Returns:
        Tuple of (return_code, stdout_text).
    """
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout


def list_changed_slugs(event_name: str, before_sha: str, head_sha: str) -> list[str]:
    """
    List changed blog slugs between two revisions.

    Args:
        event_name: GitHub event name.
        before_sha: Previous SHA.
        head_sha: Current SHA.

    Returns:
        Sorted changed slugs.
    """
    if event_name == "workflow_dispatch":
        return []

    if not head_sha:
        return []

    if not before_sha or before_sha == "0000000000000000000000000000000000000000":
        code, output = run_git_text(
            ["diff-tree", "--no-commit-id", "--name-only", "-r", head_sha, "--", "src/content/blog/*.md"]
        )
    else:
        code, output = run_git_text(
            ["diff", "--name-only", before_sha, head_sha, "--", "src/content/blog/*.md"]
        )
    if code != 0:
        return []

    slugs = []
    for line in output.splitlines():
        line = line.strip()
        match = re.match(r"^src/content/blog/(.+)\.md$", line)
        if match:
            slugs.append(match.group(1))
    return sorted(set(slugs))


def list_all_blog_slugs() -> list[str]:
    """List all markdown slugs in blog directory from working tree."""
    if not BLOG_DIR.exists() or not BLOG_DIR.is_dir():
        return []
    return sorted(path.stem for path in BLOG_DIR.glob("*.md") if path.is_file())


def select_unrecorded_slugs(
    *,
    allowed_author: str,
    max_count: int,
    record_dir: Path,
) -> list[str]:
    """
    Select newest slugs missing local AI comment record files.

    Args:
        allowed_author: Required post author.
        max_count: Maximum slugs to return.
        record_dir: Directory containing comment generation records.

    Returns:
        Selected slugs in descending recency.
    """
    if max_count <= 0:
        return []

    candidates: list[tuple[str, str]] = []
    for slug in list_all_blog_slugs():
        snapshot = read_current_snapshot(slug)
        if snapshot is None:
            continue
        if snapshot.author.strip() != allowed_author:
            continue
        if snapshot.draft:
            continue

        record_path = record_dir / f"{slug}.json"
        if record_path.exists():
            continue

        # pub_date is expected to be ISO-like and sortable as text.
        candidates.append((snapshot.pub_date.strip(), slug))

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [slug for _, slug in candidates[:max_count]]


def read_snapshot_from_ref(slug: str, ref: str) -> ParsedPostSnapshot | None:
    """
    Read post snapshot from a git ref.

    Args:
        slug: Post slug.
        ref: Git ref or SHA.

    Returns:
        Parsed snapshot, or None if file does not exist in ref.

    Raises:
        SelectCommentTargetError: If markdown exists but parse fails.
    """
    code, output = run_git_text([ "show", f"{ref}:src/content/blog/{slug}.md" ])
    if code != 0:
        return None
    return parse_markdown_snapshot(output, f"{ref}:{slug}")


def read_current_snapshot(slug: str) -> ParsedPostSnapshot | None:
    """
    Read snapshot from working tree file.

    Args:
        slug: Post slug.

    Returns:
        Parsed snapshot, or None if file missing.
    """
    file_path = BLOG_DIR / f"{slug}.md"
    if not file_path.exists() or not file_path.is_file():
        return None
    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError:
        return None
    return parse_markdown_snapshot(raw, str(file_path))


def is_significant_change(
    *,
    previous: ParsedPostSnapshot | None,
    current: ParsedPostSnapshot,
    similarity_threshold: float,
    char_delta_threshold: int,
) -> tuple[bool, str]:
    """
    Determine whether a post changed significantly.

    Args:
        previous: Previous snapshot (None for new post).
        current: Current snapshot.
        similarity_threshold: Body similarity threshold.
        char_delta_threshold: Minimum character delta to treat as significant.

    Returns:
        Tuple of (is_significant, reason).
    """
    if previous is None:
        return True, "new_post"

    title_changed = normalize_text(previous.title) != normalize_text(current.title)
    description_changed = (
        normalize_text(previous.description) != normalize_text(current.description)
    )
    if title_changed or description_changed:
        return True, "title_or_description_changed"

    if normalize_text(previous.pub_date) != normalize_text(current.pub_date):
        return True, "pub_date_changed"

    if normalize_text(previous.group) != normalize_text(current.group):
        return True, "group_changed"

    if previous.tags != current.tags:
        return True, "tags_changed"

    if previous.draft != current.draft:
        return True, "draft_flag_changed"

    prev_body = normalize_text(previous.body)
    curr_body = normalize_text(current.body)
    if prev_body == curr_body:
        return False, "body_equivalent_after_normalization"

    similarity = SequenceMatcher(None, prev_body, curr_body).ratio()
    char_delta = abs(len(curr_body) - len(prev_body))

    if similarity < similarity_threshold:
        return True, f"body_similarity_below_threshold({similarity:.4f})"
    if char_delta >= char_delta_threshold:
        return True, f"body_char_delta_above_threshold({char_delta})"

    return False, f"body_change_below_threshold(similarity={similarity:.4f},char_delta={char_delta})"


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments.

    Returns:
        Parsed CLI namespace.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Select blog slugs that should trigger AI comment refresh "
            "based on author and significant content change."
        )
    )
    parser.add_argument("--event-name", default="", type=str)
    parser.add_argument("--manual-slug", default="", type=str)
    parser.add_argument("--before-sha", default="", type=str)
    parser.add_argument("--head-sha", default="", type=str)
    parser.add_argument("--allowed-author", default="dplvoah", type=str)
    parser.add_argument("--similarity-threshold", default=0.98, type=float)
    parser.add_argument("--char-delta-threshold", default=120, type=int)
    parser.add_argument(
        "--include-unrecorded-if-empty",
        action="store_true",
        help=(
            "When no changed slugs are selected on push events, "
            "fallback to newest posts missing ai_output/comments/<slug>.json."
        ),
    )
    parser.add_argument(
        "--unrecorded-max-slugs",
        default=1,
        type=int,
        help="Maximum fallback slugs selected by --include-unrecorded-if-empty.",
    )
    parser.add_argument(
        "--comment-record-dir",
        default=str(DEFAULT_COMMENT_RECORD_DIR),
        type=str,
        help="Directory containing AI comment generation records.",
    )
    parser.add_argument(
        "--slugs-only",
        action="store_true",
        help="Print only selected slugs as a space-separated string.",
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
        allowed_author = args.allowed_author.strip()
        if not allowed_author:
            raise SelectCommentTargetError("--allowed-author cannot be empty.")

        manual_slug = args.manual_slug.strip()
        if manual_slug:
            candidate_slugs = [manual_slug]
        else:
            candidate_slugs = list_changed_slugs(
                args.event_name.strip(),
                args.before_sha.strip(),
                args.head_sha.strip(),
            )

        selected_slugs: list[str] = []
        details: list[dict[str, str]] = []

        for slug in candidate_slugs:
            current = read_current_snapshot(slug)
            if current is None:
                details.append({"slug": slug, "selected": "false", "reason": "missing_current_file"})
                continue

            if current.author.strip() != allowed_author:
                details.append(
                    {
                        "slug": slug,
                        "selected": "false",
                        "reason": f"author_mismatch(current={current.author},allowed={allowed_author})",
                    }
                )
                continue

            if manual_slug and slug == manual_slug:
                selected_slugs.append(slug)
                details.append(
                    {"slug": slug, "selected": "true", "reason": "manual_dispatch_slug"}
                )
                continue

            previous = read_snapshot_from_ref(slug, args.before_sha.strip()) if args.before_sha.strip() else None
            significant, reason = is_significant_change(
                previous=previous,
                current=current,
                similarity_threshold=args.similarity_threshold,
                char_delta_threshold=args.char_delta_threshold,
            )
            details.append(
                {
                    "slug": slug,
                    "selected": "true" if significant else "false",
                    "reason": reason,
                }
            )
            if significant:
                selected_slugs.append(slug)

        if (
            not selected_slugs
            and args.include_unrecorded_if_empty
            and not manual_slug
            and args.event_name.strip() == "push"
        ):
            record_dir = Path(args.comment_record_dir).resolve()
            fallback_slugs = select_unrecorded_slugs(
                allowed_author=allowed_author,
                max_count=max(1, int(args.unrecorded_max_slugs)),
                record_dir=record_dir,
            )
            for slug in fallback_slugs:
                selected_slugs.append(slug)
                details.append(
                    {
                        "slug": slug,
                        "selected": "true",
                        "reason": "missing_comment_record_backfill",
                    }
                )

        selected_slugs = sorted(set(selected_slugs))
        if args.slugs_only:
            print(" ".join(selected_slugs))
        else:
            print(
                json.dumps(
                    {
                        "selected_slugs": selected_slugs,
                        "details": details,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return 0

    except SelectCommentTargetError as exc:
        print(f"[select_ai_comment_targets.py] ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
