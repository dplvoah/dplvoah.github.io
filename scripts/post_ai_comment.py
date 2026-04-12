# Local test command:
# python scripts/post_ai_comment.py --slug first-post

# python scripts/post_ai_comment.py --slug first-post --write-file

# Purpose: Generate an AI comment for a blog post and publish it to the mapped GitHub Discussion.

from __future__ import annotations

import argparse
import json
import os
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
from lib.ai_defaults import (
    COMMENT_DEFAULT_MAX_TOKENS,
    COMMENT_DEFAULT_TEMPERATURE,
    DEEPSEEK_DEFAULT_MODEL,
)
from lib.discussion_service import (
    ensure_post_discussion as ensure_post_discussion_impl,
    persist_discussion_id_to_frontmatter as persist_discussion_id_to_frontmatter_impl,
    resolve_discussion_id as resolve_discussion_id_impl,
    resolve_repo_for_discussion_lookup as resolve_repo_for_discussion_lookup_impl,
)
from lib.output_records import write_json_record
from lib.paths import AI_OUTPUT_DIR
from github_discussions import (
    GitHubDiscussionError,
    add_discussion_comment,
    delete_discussion_comment,
    list_discussion_comments,
    load_github_token,
)
from load_markdown import BlogPost, MarkdownLoadError, load_post_by_slug
from memory_access import (
    MemoryAccessError,
    can_personalized_read,
    unauthorized_behavior_for_channel,
)
from memory_runtime import MemoryRuntimeError, record_interaction_event


OUTPUT_DIR: Final[Path] = AI_OUTPUT_DIR / "comments"


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


def should_skip_post_by_author(*, post: BlogPost, allowed_author: str) -> bool:
    """
    Check whether a post should be skipped due to author restriction.

    Args:
        post: Parsed blog post object.
        allowed_author: Restrictive author value. Empty means no restriction.

    Returns:
        True when post should be skipped, otherwise False.
    """
    normalized_allowed_author = allowed_author.strip()
    if not normalized_allowed_author:
        return False

    return post.author.strip() != normalized_allowed_author


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
    return resolve_repo_for_discussion_lookup_impl(
        repo_owner=repo_owner,
        repo_name=repo_name,
        error_cls=PostAICommentError,
    )


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
    return resolve_discussion_id_impl(
        post=post,
        github_token=github_token,
        repo_owner=repo_owner,
        repo_name=repo_name,
        discussion_search_limit=discussion_search_limit,
        discussion_category_id=discussion_category_id,
        discussion_category_name=discussion_category_name,
        error_cls=PostAICommentError,
    )


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
    return persist_discussion_id_to_frontmatter_impl(
        post=post,
        discussion_id=discussion_id,
        error_cls=PostAICommentError,
    )


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
    return ensure_post_discussion_impl(
        post=post,
        repo_owner=repo_owner,
        repo_name=repo_name,
        discussion_search_limit=discussion_search_limit,
        discussion_category_id=discussion_category_id,
        discussion_category_name=discussion_category_name,
        error_cls=PostAICommentError,
        github_token=github_token,
    )


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
        system_context = build_system_context(
            mode="comment",
            target_account=post.author,
        )
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


def delete_ai_comments_in_discussion(
    *,
    github_token: str,
    discussion_id: str,
    ai_author_login: str,
    limit: int = 200,
) -> int:
    """
    Delete existing AI comments in a discussion.

    Args:
        github_token: GitHub token.
        discussion_id: Discussion node ID.
        ai_author_login: AI account login to match.
        limit: Maximum comments to inspect.

    Returns:
        Number of deleted comments.

    Raises:
        PostAICommentError: If listing or deletion fails.
    """
    normalized_login = ai_author_login.strip()
    if not normalized_login:
        raise PostAICommentError("--ai-author-login cannot be empty.")

    try:
        comments = list_discussion_comments(
            token=github_token,
            discussion_id=discussion_id,
            limit=limit,
        )
    except GitHubDiscussionError as exc:
        raise PostAICommentError(
            f"Failed to list discussion comments for replacement: {exc}"
        ) from exc

    target_comments = [
        item
        for item in comments
        if item.get("author_login", "").strip().lower() == normalized_login.lower()
    ]

    deleted_count = 0
    for item in target_comments:
        comment_id = str(item.get("id", "")).strip()
        if not comment_id:
            continue
        try:
            delete_discussion_comment(
                token=github_token,
                comment_id=comment_id,
            )
        except GitHubDiscussionError as exc:
            raise PostAICommentError(
                f"Failed to delete existing AI comment '{comment_id}': {exc}"
            ) from exc
        deleted_count += 1

    return deleted_count


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

    return write_json_record(
        output_path=output_path,
        payload=output_data,
        error_cls=PostAICommentError,
        error_prefix="Failed to write generation record",
    )


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
        default=DEEPSEEK_DEFAULT_MODEL,
        type=str,
        help="DeepSeek model name.",
    )
    parser.add_argument(
        "--temperature",
        default=COMMENT_DEFAULT_TEMPERATURE,
        type=float,
        help="Sampling temperature.",
    )
    parser.add_argument(
        "--max-tokens",
        default=COMMENT_DEFAULT_MAX_TOKENS,
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
    parser.add_argument(
        "--allowed-author",
        default="",
        type=str,
        help=(
            "If set, only posts whose frontmatter author exactly matches this value "
            "will be processed. Non-matching posts are skipped."
        ),
    )
    parser.add_argument(
        "--replace-existing-ai-comment",
        action="store_true",
        help=(
            "Delete existing AI comments in the target discussion before "
            "publishing a new one."
        ),
    )
    parser.add_argument(
        "--ai-author-login",
        default=os.getenv("AI_AUTHOR_LOGIN", "imlevv").strip() or "imlevv",
        type=str,
        help="GitHub login used to identify AI-authored discussion comments.",
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
        if should_skip_post_by_author(post=post, allowed_author=args.allowed_author):
            print(
                "[post_ai_comment.py] Skip post by author filter: "
                f"slug={post.slug}, author={post.author}, allowed={args.allowed_author.strip()}"
            )
            return 0
        if not can_personalized_read(post.author):
            unauthorized_behavior = unauthorized_behavior_for_channel("blog_comment")
            if unauthorized_behavior == "skip":
                print(
                    "[post_ai_comment.py] Skip unauthorized identity for blog comment: "
                    f"author={post.author}"
                )
                return 0
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
        if args.replace_existing_ai_comment:
            deleted_count = delete_ai_comments_in_discussion(
                github_token=github_token,
                discussion_id=discussion_id,
                ai_author_login=args.ai_author_login,
            )
            print(
                "[post_ai_comment.py] Deleted existing AI comments: "
                f"{deleted_count}"
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

        try:
            record_interaction_event(
                principal_account=post.author,
                interaction_type="blog_comment",
                source_summary=f"{post.slug}: {post.title}",
                ai_summary=comment_text,
                reference=str(published_comment.get("url", "")).strip() or post.slug,
            )
        except MemoryRuntimeError as exc:
            print(
                "[post_ai_comment.py] WARN: memory runtime update failed: "
                f"{exc}"
            )

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

    except (MarkdownLoadError, MemoryAccessError, PostAICommentError) as exc:
        print(f"[post_ai_comment.py] ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
