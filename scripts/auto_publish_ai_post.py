# Purpose: Auto-publish AI blog posts every 2-3 days with optional force mode.

from __future__ import annotations

import argparse
import json
import os
import random
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Final

import yaml

from generate_ai_post import (
    AIPostGenerationError,
    DEFAULT_BRIEF_PATH,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    DEFAULT_TARGET_ACCOUNT,
    GeneratedAIPostDraft,
    generate_ai_post_draft,
)
from load_markdown import (
    BlogPost,
    MarkdownLoadError,
    load_latest_post_by_author,
    load_post_by_slug,
)
from lib.discussion_service import ensure_post_discussion as ensure_post_discussion_impl
from lib.output_records import write_json_record
from lib.paths import AI_OUTPUT_DIR, BLOG_DIR


OUTPUT_DIR: Final[Path] = AI_OUTPUT_DIR / "posts"

DEFAULT_AUTHOR: Final[str] = "imlevv"
DEFAULT_MIN_DAYS: Final[int] = 2
DEFAULT_MAX_DAYS: Final[int] = 3
DEFAULT_DISCUSSION_SEARCH_LIMIT: Final[int] = 100


class AutoPublishAIPostError(Exception):
    """Raised when auto publish workflow fails."""


def parse_iso_date(date_text: str) -> date:
    """
    Parse an ISO date string.

    Args:
        date_text: Date string to parse.

    Returns:
        Parsed date object.

    Raises:
        AutoPublishAIPostError: If date format is invalid.
    """
    normalized = date_text.strip()
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00")).date()
        except ValueError as exc:
            raise AutoPublishAIPostError(
                f"Invalid ISO date '{date_text}', expected ISO-compatible date."
            ) from exc


def decide_should_publish(
    *,
    latest_post: BlogPost | None,
    today: date,
    min_days: int,
    max_days: int,
    force: bool,
    rng: random.Random,
) -> tuple[bool, str, int | None]:
    """
    Decide whether to publish today.

    Args:
        latest_post: Latest post by target author, if any.
        today: Current date.
        min_days: Minimum publish interval.
        max_days: Maximum publish interval.
        force: Whether to force publish.
        rng: Random generator for min-day gate.

    Returns:
        Tuple: (should_publish, reason, diff_days or None)
    """
    if force:
        return True, "force_publish_enabled", None

    if latest_post is None:
        return True, "no_previous_post", None

    latest_date = parse_iso_date(latest_post.date)
    diff_days = (today - latest_date).days

    if diff_days < min_days:
        return False, f"interval_too_short(diff_days={diff_days})", diff_days

    if diff_days >= max_days:
        return True, f"interval_reached_max(diff_days={diff_days})", diff_days

    gate_value = rng.random()
    should_publish = gate_value < 0.5
    decision = (
        f"interval_min_gate_pass(diff_days={diff_days}, gate={gate_value:.4f})"
        if should_publish
        else f"interval_min_gate_skip(diff_days={diff_days}, gate={gate_value:.4f})"
    )
    return should_publish, decision, diff_days


def build_post_slug(today: date) -> str:
    """
    Build a unique slug using ai-YYYY-MM-DD base.

    Args:
        today: Current date.

    Returns:
        Unique slug string.
    """
    base_slug = f"ai-{today.isoformat()}"
    candidate = base_slug
    suffix = 2

    while (BLOG_DIR / f"{candidate}.md").exists():
        candidate = f"{base_slug}-{suffix}"
        suffix += 1

    return candidate


def render_markdown_post(
    *,
    draft: GeneratedAIPostDraft,
    pub_date: date,
    author: str,
) -> str:
    """
    Render markdown with YAML frontmatter.

    Args:
        draft: Generated draft payload.
        pub_date: Publish date.
        author: Author value.

    Returns:
        Markdown text.
    """
    frontmatter = {
        "title": draft.title,
        "description": draft.description,
        "pubDate": pub_date.isoformat(),
        "author": author,
    }
    frontmatter_text = yaml.safe_dump(
        frontmatter,
        allow_unicode=True,
        sort_keys=False,
    ).strip()
    body = draft.body_markdown.strip()
    return f"---\n{frontmatter_text}\n---\n\n{body}\n"


def write_markdown_post(*, slug: str, markdown_text: str) -> Path:
    """
    Write markdown post file.

    Args:
        slug: Target slug.
        markdown_text: Full markdown content.

    Returns:
        Resolved path to written file.

    Raises:
        AutoPublishAIPostError: If write fails.
    """
    output_path = BLOG_DIR / f"{slug}.md"
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown_text, encoding="utf-8")
    except OSError as exc:
        raise AutoPublishAIPostError(f"Failed to write markdown post: {output_path}") from exc
    return output_path.resolve()


def write_generation_record(
    *,
    slug: str,
    draft: GeneratedAIPostDraft,
    pub_date: date,
    author: str,
    model: str,
    response_data: dict[str, Any],
    discussion_id: str,
) -> Path:
    """
    Write generation record for debugging.

    Args:
        slug: Post slug.
        draft: Generated draft payload.
        pub_date: Publish date.
        author: Author string.
        model: Model used.
        response_data: Raw model response.
        discussion_id: Resolved discussion ID.

    Returns:
        Resolved output path.

    Raises:
        AutoPublishAIPostError: If file write fails.
    """
    output_path = OUTPUT_DIR / f"{slug}.json"
    payload = {
        "slug": slug,
        "author": author,
        "pubDate": pub_date.isoformat(),
        "model": model,
        "discussion_id": discussion_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "draft": asdict(draft),
        "usage": response_data.get("usage", {}),
        "raw_response": response_data,
    }
    return write_json_record(
        output_path=output_path,
        payload=payload,
        error_cls=AutoPublishAIPostError,
        error_prefix="Failed to write generation record",
    )


def validate_args(args: argparse.Namespace) -> None:
    """
    Validate CLI argument ranges.

    Args:
        args: Parsed args namespace.

    Raises:
        AutoPublishAIPostError: If args are invalid.
    """
    if args.min_days < 1:
        raise AutoPublishAIPostError("--min-days must be >= 1.")
    if args.max_days < args.min_days:
        raise AutoPublishAIPostError("--max-days must be >= --min-days.")
    if not args.author.strip():
        raise AutoPublishAIPostError("--author cannot be empty.")
    if args.discussion_search_limit <= 0:
        raise AutoPublishAIPostError("--discussion-search-limit must be > 0.")


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments.

    Returns:
        Parsed args namespace.
    """
    parser = argparse.ArgumentParser(
        description="Auto publish AI blog post based on 2-3 day interval rules."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force publish regardless of interval.",
    )
    parser.add_argument(
        "--author",
        default=DEFAULT_AUTHOR,
        type=str,
        help="Frontmatter author and latest-post query target.",
    )
    parser.add_argument(
        "--min-days",
        default=DEFAULT_MIN_DAYS,
        type=int,
        help="Minimum interval in days before publish can happen.",
    )
    parser.add_argument(
        "--max-days",
        default=DEFAULT_MAX_DAYS,
        type=int,
        help="Maximum interval in days before publish is mandatory.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=None,
        help="Optional random seed for deterministic gate behavior.",
    )
    parser.add_argument(
        "--repo-owner",
        default="",
        type=str,
        help="Repository owner for discussion resolution (optional).",
    )
    parser.add_argument(
        "--repo-name",
        default="",
        type=str,
        help="Repository name for discussion resolution (optional).",
    )
    parser.add_argument(
        "--discussion-search-limit",
        default=DEFAULT_DISCUSSION_SEARCH_LIMIT,
        type=int,
        help="Recent discussion search limit when resolving discussionId.",
    )
    parser.add_argument(
        "--discussion-category-id",
        default=os.getenv("GISCUS_CATEGORY_ID", "").strip(),
        type=str,
        help="Discussion category node ID for auto-create fallback.",
    )
    parser.add_argument(
        "--discussion-category-name",
        default=os.getenv("GISCUS_CATEGORY", "Comments").strip() or "Comments",
        type=str,
        help="Discussion category name fallback for auto-create.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        type=str,
        help="DeepSeek model name.",
    )
    parser.add_argument(
        "--temperature",
        default=DEFAULT_TEMPERATURE,
        type=float,
        help="Sampling temperature for post generation.",
    )
    parser.add_argument(
        "--max-tokens",
        default=DEFAULT_MAX_TOKENS,
        type=int,
        help="Maximum output tokens for post generation.",
    )
    parser.add_argument(
        "--brief-path",
        default=str(DEFAULT_BRIEF_PATH),
        type=str,
        help="Optional brief file path.",
    )
    parser.add_argument(
        "--target-account",
        default=DEFAULT_TARGET_ACCOUNT,
        type=str,
        help="Identity account used for context permission checks.",
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
        validate_args(args)

        today = datetime.now(timezone.utc).date()
        rng = random.Random(args.random_seed)

        latest_post = load_latest_post_by_author(
            args.author,
            include_drafts=False,
        )
        should_publish, decision_reason, diff_days = decide_should_publish(
            latest_post=latest_post,
            today=today,
            min_days=args.min_days,
            max_days=args.max_days,
            force=args.force,
            rng=rng,
        )

        decision_payload = {
            "should_publish": should_publish,
            "reason": decision_reason,
            "diff_days": diff_days,
            "latest_slug": latest_post.slug if latest_post else "",
            "latest_date": latest_post.date if latest_post else "",
            "today": today.isoformat(),
        }
        print(
            f"[auto_publish_ai_post.py] decision={json.dumps(decision_payload, ensure_ascii=False)}"
        )

        if not should_publish:
            print("[auto_publish_ai_post.py] Skip publish.")
            return 0

        draft, response_data = generate_ai_post_draft(
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            brief_path=Path(args.brief_path),
            target_account=args.target_account,
            today=today,
        )

        slug = build_post_slug(today)
        markdown_text = render_markdown_post(
            draft=draft,
            pub_date=today,
            author=args.author.strip(),
        )
        written_markdown_path = write_markdown_post(
            slug=slug,
            markdown_text=markdown_text,
        )
        print(f"[auto_publish_ai_post.py] Wrote markdown: {written_markdown_path}")

        post = load_post_by_slug(slug)
        discussion_id, saved_markdown_path = ensure_post_discussion_impl(
            post=post,
            repo_owner=args.repo_owner,
            repo_name=args.repo_name,
            discussion_search_limit=args.discussion_search_limit,
            discussion_category_id=args.discussion_category_id,
            discussion_category_name=args.discussion_category_name,
            error_cls=AutoPublishAIPostError,
        )
        if saved_markdown_path is not None:
            print(
                "[auto_publish_ai_post.py] Backfilled discussionId to: "
                f"{saved_markdown_path}"
            )

        record_path = write_generation_record(
            slug=slug,
            draft=draft,
            pub_date=today,
            author=args.author.strip(),
            model=args.model,
            response_data=response_data,
            discussion_id=discussion_id,
        )
        print(f"[auto_publish_ai_post.py] Wrote generation record: {record_path}")
        print(
            "[auto_publish_ai_post.py] Publish prepared successfully: "
            f"slug={slug}, discussion_id={discussion_id}"
        )
        return 0

    except (
        AIPostGenerationError,
        AutoPublishAIPostError,
        MarkdownLoadError,
    ) as exc:
        print(f"[auto_publish_ai_post.py] ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
