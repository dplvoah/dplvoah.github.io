# Print ai_comment in terminal only ```python scripts/generate_ai_comment.py --slug first-post```

# Print ai_comment and write to file ```python scripts/generate_ai_comment.py --slug first-post --write-file```

# Purpose: Generate an AI comment for a blog post using DeepSeek API.

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from build_context import ContextBuildError, build_system_context
from lib.ai_defaults import (
    COMMENT_DEFAULT_MAX_TOKENS,
    COMMENT_DEFAULT_TEMPERATURE,
    COMMENT_REQUEST_TIMEOUT_SECONDS,
    DEEPSEEK_DEFAULT_MODEL,
    HUMAN_IDENTITY_CLAIM_MARKERS,
)
from lib.deepseek_client import (
    call_deepseek_chat_completion as call_deepseek_chat_completion_impl,
    load_deepseek_api_key,
)
from lib.output_records import write_json_record
from lib.paths import AI_OUTPUT_DIR
from load_markdown import BlogPost, MarkdownLoadError, load_post_by_slug


OUTPUT_DIR: Final[Path] = AI_OUTPUT_DIR / "comments"
DEFAULT_MODEL: Final[str] = DEEPSEEK_DEFAULT_MODEL
DEFAULT_TEMPERATURE: Final[float] = COMMENT_DEFAULT_TEMPERATURE
DEFAULT_MAX_TOKENS: Final[int] = COMMENT_DEFAULT_MAX_TOKENS


class AICommentGenerationError(Exception):
    """Raised when AI comment generation fails."""


def load_api_key() -> str:
    """
    Load DeepSeek API key from environment.

    Returns:
        API key string.

    Raises:
        AICommentGenerationError: If API key is missing.
    """
    return load_deepseek_api_key(error_cls=AICommentGenerationError)


def build_user_prompt(post: BlogPost) -> str:
    """
    Build the user prompt for comment generation.

    Args:
        post: Parsed blog post.

    Returns:
        Prompt string for the model.
    """
    return (
        "You are responding to a blog post as an AI reflection companion.\n"
        "Write from a clear non-human AI perspective (identity: imlevv), "
        "not as a human persona.\n\n"
        "Generate one thoughtful public-facing comment for the post.\n\n"
        "Requirements:\n"
        "1. The comment must directly engage with the post's ideas.\n"
        "2. The tone should be reflective, clear, and natural.\n"
        "3. Do not sound like customer support or generic praise.\n"
        "4. Do not mention internal instructions, prompt design, or system context.\n"
        "5. Keep it reasonably concise.\n"
        "6. Output plain text only.\n"
        "7. Use natural paragraph prose; do not use bullet points or numbered lists.\n"
        "8. Avoid label-style lines like '观点：' / '结论：'.\n"
        "9. Avoid frequent long dashes and unnatural punctuation stacking.\n\n"
        f"POST TITLE:\n{post.title}\n\n"
        f"POST DATE:\n{post.date}\n\n"
        f"POST DESCRIPTION:\n{post.description}\n\n"
        f"POST BODY:\n{post.body}\n"
    )


def validate_ai_perspective_comment(comment_text: str) -> None:
    """
    Validate generated comment preserves AI perspective.

    Args:
        comment_text: Generated comment text.

    Raises:
        AICommentGenerationError: If explicit human identity claim is found.
    """
    lowered = comment_text.lower()
    for marker in HUMAN_IDENTITY_CLAIM_MARKERS:
        if marker.lower() in lowered:
            raise AICommentGenerationError(
                "Generated comment violates AI perspective rule: "
                f"found '{marker}'."
            )


def call_deepseek_chat_completion(
    *,
    api_key: str,
    system_context: str,
    user_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> dict[str, Any]:
    """
    Call DeepSeek chat completion API.

    Args:
        api_key: DeepSeek API key.
        system_context: Built system context text.
        user_prompt: Final user prompt text.
        model: Model name.
        temperature: Sampling temperature.
        max_tokens: Max output tokens.

    Returns:
        Parsed JSON response.

    Raises:
        AICommentGenerationError: If request fails or response is invalid.
    """
    return call_deepseek_chat_completion_impl(
        api_key=api_key,
        system_context=system_context,
        user_prompt=user_prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_seconds=COMMENT_REQUEST_TIMEOUT_SECONDS,
        error_cls=AICommentGenerationError,
    )


def extract_comment_text(response_data: dict[str, Any]) -> str:
    """
    Extract generated comment text from DeepSeek API response.

    Args:
        response_data: Parsed response JSON.

    Returns:
        Generated comment text.

    Raises:
        AICommentGenerationError: If response structure is invalid.
    """
    try:
        comment_text = response_data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AICommentGenerationError(
            "DeepSeek response missing choices[0].message.content"
        ) from exc

    comment_text = str(comment_text).strip()
    if not comment_text:
        raise AICommentGenerationError("Generated comment is empty.")
    validate_ai_perspective_comment(comment_text)

    return comment_text


def build_output_payload(
    *,
    post: BlogPost,
    model: str,
    comment_text: str,
    response_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Build output payload for saving.

    Args:
        post: Parsed blog post.
        model: Model name used.
        comment_text: Final generated comment.
        response_data: Full DeepSeek response.

    Returns:
        Structured output dictionary.
    """
    usage = response_data.get("usage", {})

    return {
        "slug": post.slug,
        "title": post.title,
        "date": post.date,
        "description": post.description,
        "model": model,
        "generated_comment": comment_text,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "usage": usage,
        "raw_response": response_data,
    }


def write_output_json(output_data: dict[str, Any], output_path: Path) -> Path:
    """
    Write generated output to a JSON file.

    Args:
        output_data: Final JSON payload.
        output_path: Destination path.

    Returns:
        Resolved output path.

    Raises:
        AICommentGenerationError: If write fails.
    """
    return write_json_record(
        output_path=output_path,
        payload=output_data,
        error_cls=AICommentGenerationError,
        error_prefix="Failed to write output file",
    )


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Generate an AI comment for a blog post using DeepSeek API."
    )
    parser.add_argument(
        "--slug",
        required=True,
        type=str,
        help="Blog post slug, e.g. first-post",
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
        help="Sampling temperature.",
    )
    parser.add_argument(
        "--max-tokens",
        default=DEFAULT_MAX_TOKENS,
        type=int,
        help="Maximum output tokens.",
    )
    parser.add_argument(
        "--write-file",
        action="store_true",
        help="Write generated result to ai_output/comments/<slug>.json",
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
        api_key = load_api_key()
        post = load_post_by_slug(args.slug)
        system_context = build_system_context(
            mode="comment",
            target_account=post.author,
        )
        user_prompt = build_user_prompt(post)

        response_data = call_deepseek_chat_completion(
            api_key=api_key,
            system_context=system_context,
            user_prompt=user_prompt,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )

        comment_text = extract_comment_text(response_data)

        print(comment_text)

        if args.write_file:
            output_data = build_output_payload(
                post=post,
                model=args.model,
                comment_text=comment_text,
                response_data=response_data,
            )
            output_path = OUTPUT_DIR / f"{post.slug}.json"
            saved_path = write_output_json(output_data, output_path)
            print(f"\n[generate_ai_comment.py] Output written to: {saved_path}")

        return 0

    except (
        AICommentGenerationError,
        ContextBuildError,
        MarkdownLoadError,
    ) as exc:
        print(f"[generate_ai_comment.py] ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
