# Local test command:
# python scripts/post_ai_comment.py --slug first-post

# python scripts/post_ai_comment.py --slug first-post --write-file

# Purpose: Generate an AI comment for a blog post and publish it to the mapped GitHub Discussion.

from __future__ import annotations

import argparse
import json
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
    load_github_token,
)
from load_markdown import BlogPost, MarkdownLoadError, load_post_by_slug


ROOT_DIR: Final[Path] = Path(__file__).resolve().parent.parent
OUTPUT_DIR: Final[Path] = ROOT_DIR / "ai_output" / "comments"


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

    if not post.discussion_id.strip():
        raise PostAICommentError(
            f"Post '{post.slug}' is missing discussionId in frontmatter."
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
        github_token = load_github_token()
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
        print(f"[post_ai_comment.py] slug={post.slug}, discussion_id={post.discussion_id}")

        comment_text, response_data = generate_comment_for_post(
            post=post,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )

        published_comment = publish_comment_to_discussion(
            discussion_id=post.discussion_id,
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
            output_data["discussion_id"] = post.discussion_id
            output_data["published_comment"] = published_comment

            saved_path = write_generation_record(output_data, post.slug)
            print(f"\n[post_ai_comment.py] Output written to: {saved_path}")

        return 0

    except (MarkdownLoadError, PostAICommentError) as exc:
        print(f"[post_ai_comment.py] ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())