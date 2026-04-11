# Local test command:
# python scripts/post_ai_comment.py --slug first-post

# python scripts/post_ai_comment.py --slug first-post --write-file

# Purpose: Generate an AI comment for a blog post and publish it to the mapped GitHub Discussion.

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Final

from build_context import ContextBuildError, build_system_context
from generate_ai_comment import (
    AICommentGenerationError,
    build_output_payload,
    build_user_prompt,
    call_deepseek_chat_completion,
    extract_comment_text,
    load_api_key,
)
from github_discussions import (
    GitHubDiscussionError,
    add_discussion_comment,
    create_discussion,
    find_discussion_by_title,
    load_github_token,
    update_discussion_title,
)
from load_markdown import BlogPost, MarkdownLoadError, load_post_by_slug


ROOT_DIR: Final[Path] = Path(__file__).resolve().parent.parent
OUTPUT_DIR: Final[Path] = ROOT_DIR / "ai_output" / "comments"
FRONTMATTER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^---\r?\n(.*?)\r?\n---(\r?\n?.*)$",
    re.DOTALL,
)


class PostAICommentError(Exception):
    """Raised when AI comment posting workflow fails."""


def validate_post_for_comment(post: BlogPost) -> None:
    """
    Validate whether the blog post is ready for AI comment posting.

    Args:
        post: Parsed blog post object.

    Raises:
        PostAICommentError: If the post should not be processed.
    """
    if post.draft:
        raise PostAICommentError(
            f"Post '{post.slug}' is marked as draft and cannot receive AI comments."
        )


def resolve_repo_for_discussion_lookup(
    *,
    repo_owner: str,
    repo_name: str,
) -> tuple[str, str]:
    """
    Resolve repository owner/name for discussion lookup.

    Priority:
    1) CLI args (--repo-owner / --repo-name)
    2) GITHUB_REPOSITORY env (owner/repo)

    Args:
        repo_owner: CLI repository owner value.
        repo_name: CLI repository name value.

    Returns:
        Tuple of (owner, repo).

    Raises:
        PostAICommentError: If repo info is unavailable or invalid.
    """
    owner = repo_owner.strip()
    name = repo_name.strip()
    if owner and name:
        return owner, name

    if owner or name:
        raise PostAICommentError(
            "Both --repo-owner and --repo-name are required together."
        )

    github_repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    if "/" not in github_repository:
        raise PostAICommentError(
            "Missing repository info. Set --repo-owner/--repo-name, "
            "or provide GITHUB_REPOSITORY=owner/repo."
        )

    env_owner, env_repo = github_repository.split("/", 1)
    env_owner = env_owner.strip()
    env_repo = env_repo.strip()
    if not env_owner or not env_repo:
        raise PostAICommentError(
            f"Invalid GITHUB_REPOSITORY value: {github_repository}"
        )

    return env_owner, env_repo


def resolve_discussion_id(
    *,
    post: BlogPost,
    github_token: str,
    repo_owner: str,
    repo_name: str,
    discussion_search_limit: int,
    discussion_category_id: str,
    discussion_category_name: str,
) -> str:
    """
    Resolve the GitHub Discussion ID for a post.

    Args:
        post: Parsed blog post.
        github_token: GitHub token.
        repo_owner: Repository owner.
        repo_name: Repository name.
        discussion_search_limit: Number of recent discussions to inspect.
        discussion_category_id: Preferred discussion category ID for auto-create.
        discussion_category_name: Preferred discussion category name for auto-create.

    Returns:
        Resolved discussion ID.

    Raises:
        PostAICommentError: If discussion cannot be resolved safely.
    """
    configured_discussion_id = post.discussion_id.strip()
    if configured_discussion_id:
        return configured_discussion_id

    owner, name = resolve_repo_for_discussion_lookup(
        repo_owner=repo_owner,
        repo_name=repo_name,
    )

    if discussion_search_limit <= 0:
        raise PostAICommentError("--discussion-search-limit must be greater than 0.")

    # Keep discussion title aligned with giscus mapping=pathname.
    # Existing discussions in this repo use title format: blog/<slug>/
    canonical_mapping_key = f"blog/{post.slug}/"

    def find_by_title(title_text: str) -> list[dict[str, Any]]:
        try:
            return find_discussion_by_title(
                token=github_token,
                owner=owner,
                repo=name,
                title=title_text,
                limit=discussion_search_limit,
            )
        except GitHubDiscussionError as exc:
            raise PostAICommentError(
                f"Failed to look up discussion by title '{title_text}': {exc}"
            ) from exc

    matches = find_by_title(canonical_mapping_key)

    if not matches:
        legacy_title_matches = find_by_title(post.title)
        if len(legacy_title_matches) > 1:
            legacy_candidates = ", ".join(
                f"{item.get('id', '')}:{item.get('title', '')}"
                for item in legacy_title_matches[:5]
            )
            raise PostAICommentError(
                f"Multiple legacy discussions match title '{post.title}'. "
                f"Set discussionId in frontmatter to disambiguate. "
                f"Candidates: {legacy_candidates}"
            )
        if len(legacy_title_matches) == 1:
            legacy_discussion = legacy_title_matches[0]
            legacy_discussion_id = str(legacy_discussion.get("id", "")).strip()
            if not legacy_discussion_id:
                raise PostAICommentError(
                    f"Found legacy discussion for '{post.title}', but ID is empty."
                )
            try:
                updated_discussion = update_discussion_title(
                    token=github_token,
                    discussion_id=legacy_discussion_id,
                    title=canonical_mapping_key,
                )
            except GitHubDiscussionError as exc:
                raise PostAICommentError(
                    f"Failed to rename legacy discussion '{post.title}' "
                    f"to '{canonical_mapping_key}': {exc}"
                ) from exc
            print(
                "[post_ai_comment.py] Renamed legacy discussion title to pathname key: "
                f"{updated_discussion.get('url', '')}"
            )
            return legacy_discussion_id

    if not matches:
        discussion_body = (
            f"Auto-created discussion for blog post **{post.title}**.\n\n"
            f"- Pathname key: `{canonical_mapping_key}`\n"
            f"- Slug: `{post.slug}`\n"
            f"- Date: `{post.date}`\n\n"
            f"{post.description}"
        )
        try:
            created_discussion = create_discussion(
                token=github_token,
                owner=owner,
                repo=name,
                title=canonical_mapping_key,
                body=discussion_body,
                category_id=discussion_category_id,
                category_name=discussion_category_name,
            )
        except GitHubDiscussionError as exc:
            raise PostAICommentError(
                f"Post '{post.slug}' has no discussionId, no matching discussion by canonical key, "
                f"and auto-create failed: {exc}"
            ) from exc

        created_discussion_id = str(created_discussion.get("id", "")).strip()
        if not created_discussion_id:
            raise PostAICommentError(
                f"Discussion auto-created for post '{post.slug}', but returned ID is empty."
            )
        print(
            "[post_ai_comment.py] Created discussion automatically: "
            f"{created_discussion.get('url', '')}"
        )
        return created_discussion_id

    if len(matches) > 1:
        candidates = ", ".join(
            f"{item.get('id', '')}:{item.get('title', '')}" for item in matches[:5]
        )
        raise PostAICommentError(
            f"Multiple discussions match canonical key '{canonical_mapping_key}'. "
            f"Set discussionId in frontmatter to disambiguate. Candidates: {candidates}"
        )

    resolved_discussion_id = str(matches[0].get("id", "")).strip()
    if not resolved_discussion_id:
        raise PostAICommentError(
            f"Found discussion for title '{post.title}', but ID is empty."
        )

    return resolved_discussion_id


def persist_discussion_id_to_frontmatter(
    *,
    post: BlogPost,
    discussion_id: str,
) -> Path | None:
    """
    Persist resolved discussionId back to markdown frontmatter when missing.

    Args:
        post: Parsed blog post.
        discussion_id: Discussion ID already resolved for the post.

    Returns:
        Resolved markdown path if written, otherwise None.

    Raises:
        PostAICommentError: If markdown cannot be updated safely.
    """
    if post.discussion_id.strip():
        return None

    markdown_path = Path(post.source_path)
    try:
        raw_text = markdown_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PostAICommentError(
            f"Failed to read markdown for discussionId backfill: {markdown_path}"
        ) from exc

    match = FRONTMATTER_PATTERN.match(raw_text)
    if not match:
        raise PostAICommentError(
            f"Cannot backfill discussionId because frontmatter format is invalid: {markdown_path}"
        )

    frontmatter_text, remainder = match.groups()
    if re.search(r"(?m)^\s*discussionId\s*:", frontmatter_text):
        return None

    newline = "\r\n" if "\r\n" in raw_text else "\n"
    updated_frontmatter = (
        frontmatter_text.rstrip()
        + newline
        + f'discussionId: "{discussion_id}"'
    )
    updated_text = f"---{newline}{updated_frontmatter}{newline}---{remainder}"

    try:
        markdown_path.write_text(updated_text, encoding="utf-8")
    except OSError as exc:
        raise PostAICommentError(
            f"Failed to backfill discussionId to markdown: {markdown_path}"
        ) from exc

    return markdown_path.resolve()


def ensure_post_discussion(
    *,
    post: BlogPost,
    repo_owner: str,
    repo_name: str,
    discussion_search_limit: int,
    discussion_category_id: str,
    discussion_category_name: str,
    github_token: str | None = None,
) -> tuple[str, Path | None]:
    """
    Ensure a post has an associated GitHub Discussion and optional backfilled ID.

    Args:
        post: Parsed blog post.
        repo_owner: Repository owner for discussion lookup.
        repo_name: Repository name for discussion lookup.
        discussion_search_limit: Number of recent discussions to inspect.
        discussion_category_id: Preferred category ID for auto-create.
        discussion_category_name: Preferred category name for auto-create.
        github_token: Optional preloaded token; if missing, loaded from env.

    Returns:
        Tuple of (resolved_discussion_id, saved_markdown_path_or_none).

    Raises:
        PostAICommentError: If discussion cannot be resolved or backfilled.
    """
    token = github_token or load_github_token()
    discussion_id = resolve_discussion_id(
        post=post,
        github_token=token,
        repo_owner=repo_owner,
        repo_name=repo_name,
        discussion_search_limit=discussion_search_limit,
        discussion_category_id=discussion_category_id,
        discussion_category_name=discussion_category_name,
    )
    saved_markdown_path = persist_discussion_id_to_frontmatter(
        post=post,
        discussion_id=discussion_id,
    )
    return discussion_id, saved_markdown_path


def generate_comment_for_post(
    *,
    post: BlogPost,
    model: str,
    temperature: float,
    max_tokens: int,
) -> tuple[str, dict[str, Any]]:
    """
    Generate AI comment text for a blog post.

    Args:
        post: Parsed blog post object.
        model: DeepSeek model name.
        temperature: Sampling temperature.
        max_tokens: Maximum output tokens.

    Returns:
        Tuple of (comment_text, raw_response_data).

    Raises:
        PostAICommentError: If generation fails.
    """
    try:
        api_key = load_api_key()
        system_context = build_system_context()
        user_prompt = build_user_prompt(post)

        response_data = call_deepseek_chat_completion(
            api_key=api_key,
            system_context=system_context,
            user_prompt=user_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        comment_text = extract_comment_text(response_data)
        return comment_text, response_data

    except (AICommentGenerationError, ContextBuildError) as exc:
        raise PostAICommentError(f"AI comment generation failed: {exc}") from exc


def publish_comment_to_discussion(
    *,
    github_token: str,
    discussion_id: str,
    comment_text: str,
) -> dict[str, Any]:
    """
    Publish generated comment to GitHub Discussion.

    Args:
        discussion_id: GitHub Discussion node ID.
        comment_text: Generated AI comment text.

    Returns:
        Created discussion comment payload.

    Raises:
        PostAICommentError: If publishing fails.
    """
    try:
        return add_discussion_comment(
            token=github_token,
            discussion_id=discussion_id,
            body=comment_text,
        )
    except GitHubDiscussionError as exc:
        raise PostAICommentError(f"GitHub discussion publish failed: {exc}") from exc


def write_generation_record(output_data: dict[str, Any], slug: str) -> Path:
    """
    Write generation record to ai_output/comments/<slug>.json.

    Args:
        output_data: Structured output payload.
        slug: Blog post slug.

    Returns:
        Resolved file path.

    Raises:
        PostAICommentError: If write fails.
    """
    output_path = OUTPUT_DIR / f"{slug}.json"

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(output_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        raise PostAICommentError(
            f"Failed to write generation record: {output_path}"
        ) from exc

    return output_path.resolve()


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments.

    Returns:
        Parsed CLI namespace.
    """
    parser = argparse.ArgumentParser(
        description="Generate an AI comment for a blog post and publish it to GitHub Discussion."
    )
    parser.add_argument(
        "--slug",
        required=True,
        type=str,
        help="Blog post slug, e.g. first-post",
    )
    parser.add_argument(
        "--model",
        default="deepseek-chat",
        type=str,
        help="DeepSeek model name.",
    )
    parser.add_argument(
        "--temperature",
        default=0.9,
        type=float,
        help="Sampling temperature.",
    )
    parser.add_argument(
        "--max-tokens",
        default=800,
        type=int,
        help="Maximum output tokens.",
    )
    parser.add_argument(
        "--write-file",
        action="store_true",
        help="Write generation record to ai_output/comments/<slug>.json",
    )
    parser.add_argument(
        "--repo-owner",
        default="",
        type=str,
        help=(
            "Repository owner for discussion lookup when discussionId is missing. "
            "Falls back to GITHUB_REPOSITORY."
        ),
    )
    parser.add_argument(
        "--repo-name",
        default="",
        type=str,
        help=(
            "Repository name for discussion lookup when discussionId is missing. "
            "Falls back to GITHUB_REPOSITORY."
        ),
    )
    parser.add_argument(
        "--discussion-search-limit",
        default=100,
        type=int,
        help="Number of recent discussions to inspect when resolving discussionId.",
    )
    parser.add_argument(
        "--discussion-category-id",
        default=os.getenv("GISCUS_CATEGORY_ID", "").strip(),
        type=str,
        help=(
            "Discussion category node ID used for auto-create. "
            "Falls back to GISCUS_CATEGORY_ID."
        ),
    )
    parser.add_argument(
        "--discussion-category-name",
        default=os.getenv("GISCUS_CATEGORY", "Comments").strip() or "Comments",
        type=str,
        help=(
            "Discussion category name used when category ID is not set. "
            "Falls back to GISCUS_CATEGORY (default: Comments)."
        ),
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
        post = load_post_by_slug(args.slug)
        validate_post_for_comment(post)
        github_token = load_github_token()
        discussion_id, saved_markdown_path = ensure_post_discussion(
            post=post,
            repo_owner=args.repo_owner,
            repo_name=args.repo_name,
            discussion_search_limit=args.discussion_search_limit,
            discussion_category_id=args.discussion_category_id,
            discussion_category_name=args.discussion_category_name,
            github_token=github_token,
        )
        print(f"[post_ai_comment.py] slug={post.slug}, discussion_id={discussion_id}")
        if saved_markdown_path is not None:
            print(
                "[post_ai_comment.py] Backfilled discussionId to: "
                f"{saved_markdown_path}"
            )

        comment_text, response_data = generate_comment_for_post(
            post=post,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )

        published_comment = publish_comment_to_discussion(
            github_token=github_token,
            discussion_id=discussion_id,
            comment_text=comment_text,
        )

        print(json.dumps(published_comment, ensure_ascii=False, indent=2))

        if args.write_file:
            output_data = build_output_payload(
                post=post,
                model=args.model,
                comment_text=comment_text,
                response_data=response_data,
            )
            output_data["discussion_id"] = discussion_id
            output_data["published_comment"] = published_comment

            saved_path = write_generation_record(output_data, post.slug)
            print(f"\n[post_ai_comment.py] Output written to: {saved_path}")

        return 0

    except (MarkdownLoadError, PostAICommentError) as exc:
        print(f"[post_ai_comment.py] ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
