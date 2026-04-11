# Purpose: Load blog markdown files, parse frontmatter and body, and return normalized post data.

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Final

import yaml


ROOT_DIR: Final[Path] = Path(__file__).resolve().parent.parent
BLOG_DIR: Final[Path] = ROOT_DIR / "src" / "content" / "blog"

FRONTMATTER_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^---\n(.*?)\n---\n?(.*)$",
    re.DOTALL,
)


class MarkdownLoadError(Exception):
    """Raised when markdown post loading or parsing fails."""


@dataclass(frozen=True)
class BlogPost:
    """Normalized blog post structure."""

    slug: str
    source_path: str
    title: str
    date: str
    description: str
    author: str
    draft: bool
    discussion_id: str
    body: str
    metadata: dict[str, Any]


def read_text_file(file_path: Path) -> str:
    """
    Read a UTF-8 text file and return raw text.

    Args:
        file_path: File path to read.

    Returns:
        Raw file content.

    Raises:
        MarkdownLoadError: If file is missing, invalid, or unreadable.
    """
    if not file_path.exists():
        raise MarkdownLoadError(f"Missing markdown file: {file_path}")

    if not file_path.is_file():
        raise MarkdownLoadError(f"Path is not a file: {file_path}")

    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise MarkdownLoadError(f"Failed to decode file as UTF-8: {file_path}") from exc
    except OSError as exc:
        raise MarkdownLoadError(f"Failed to read file: {file_path}") from exc


def split_frontmatter(raw_text: str, file_path: Path) -> tuple[dict[str, Any], str]:
    """
    Split markdown into YAML frontmatter and body.

    Args:
        raw_text: Raw markdown text.
        file_path: Source file path for error reporting.

    Returns:
        Tuple of (frontmatter_dict, markdown_body).

    Raises:
        MarkdownLoadError: If frontmatter is missing or invalid.
    """
    match = FRONTMATTER_PATTERN.match(raw_text)
    if not match:
        raise MarkdownLoadError(f"Missing or invalid frontmatter format: {file_path}")

    frontmatter_text, body_text = match.groups()

    try:
        frontmatter = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as exc:
        raise MarkdownLoadError(f"Invalid YAML frontmatter: {file_path}") from exc

    if not isinstance(frontmatter, dict):
        raise MarkdownLoadError(f"Frontmatter must be a mapping object: {file_path}")

    body = body_text.strip()
    if not body:
        raise MarkdownLoadError(f"Markdown body is empty: {file_path}")

    return frontmatter, body


def build_slug(file_path: Path) -> str:
    """
    Build slug from markdown filename.

    Args:
        file_path: Markdown file path.

    Returns:
        Filename stem as slug.
    """
    return file_path.stem.strip()


def extract_date(frontmatter: dict[str, Any], file_path: Path) -> str:
    """
    Extract date value from frontmatter, supporting both 'date' and 'pubDate'.

    Args:
        frontmatter: Parsed YAML frontmatter.
        file_path: Source file path for error reporting.

    Returns:
        Normalized date string.

    Raises:
        MarkdownLoadError: If neither field exists or the value is empty.
    """
    raw_date = frontmatter.get("date")
    if raw_date is None:
        raw_date = frontmatter.get("pubDate")

    date_text = str(raw_date).strip() if raw_date is not None else ""
    if not date_text:
        raise MarkdownLoadError(
            f"Missing required field 'date' or 'pubDate': {file_path}"
        )

    return date_text


def extract_discussion_id(frontmatter: dict[str, Any]) -> str:
    """
    Extract discussionId from frontmatter.

    Args:
        frontmatter: Parsed YAML frontmatter.

    Returns:
        discussionId string, or empty string if not provided.
    """
    raw_discussion_id = frontmatter.get("discussionId")
    if raw_discussion_id is None:
        return ""

    return str(raw_discussion_id).strip()


def extract_author(frontmatter: dict[str, Any], file_path: Path) -> str:
    """
    Extract author from frontmatter.

    Args:
        frontmatter: Parsed YAML frontmatter.
        file_path: Source file path for error reporting.

    Returns:
        Author string.

    Raises:
        MarkdownLoadError: If author is missing or empty.
    """
    author = str(frontmatter.get("author", "")).strip()
    if not author:
        raise MarkdownLoadError(f"Missing required field 'author': {file_path}")

    return author


def parse_date_as_date(date_text: str, file_path: Path) -> date:
    """
    Parse date text into datetime.date.

    Args:
        date_text: Date string from frontmatter.
        file_path: Source file path for error reporting.

    Returns:
        Parsed date object.

    Raises:
        MarkdownLoadError: If date cannot be parsed as ISO date.
    """
    normalized = date_text.strip()
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00")).date()
        except ValueError as exc:
            raise MarkdownLoadError(
                f"Invalid date format '{date_text}', expected ISO date (YYYY-MM-DD): {file_path}"
            ) from exc


def normalize_post(file_path: Path) -> BlogPost:
    """
    Parse one markdown file into normalized BlogPost data.

    Args:
        file_path: Markdown file path.

    Returns:
        BlogPost object.

    Raises:
        MarkdownLoadError: If required fields are missing or invalid.
    """
    raw_text = read_text_file(file_path)
    frontmatter, body = split_frontmatter(raw_text, file_path)

    title = str(frontmatter.get("title", "")).strip()
    date = extract_date(frontmatter, file_path)
    description = str(frontmatter.get("description", "")).strip()
    author = extract_author(frontmatter, file_path)
    draft = bool(frontmatter.get("draft", False))
    discussion_id = extract_discussion_id(frontmatter)

    if not title:
        raise MarkdownLoadError(f"Missing required field 'title': {file_path}")

    if not description:
        raise MarkdownLoadError(f"Missing required field 'description': {file_path}")

    slug = build_slug(file_path)
    metadata = dict(frontmatter)

    return BlogPost(
        slug=slug,
        source_path=str(file_path.resolve()),
        title=title,
        date=date,
        description=description,
        author=author,
        draft=draft,
        discussion_id=discussion_id,
        body=body,
        metadata=metadata,
    )


def load_post_by_slug(slug: str) -> BlogPost:
    """
    Load a single blog post by slug.

    Args:
        slug: Markdown filename stem without extension.

    Returns:
        BlogPost object.

    Raises:
        MarkdownLoadError: If target file does not exist or is invalid.
    """
    file_path = BLOG_DIR / f"{slug}.md"
    return normalize_post(file_path)


def load_all_posts(include_drafts: bool = False) -> list[BlogPost]:
    """
    Load all markdown posts in the blog directory.

    Args:
        include_drafts: Whether to include draft posts.

    Returns:
        List of BlogPost objects sorted by filename.

    Raises:
        MarkdownLoadError: If blog directory is missing.
    """
    if not BLOG_DIR.exists():
        raise MarkdownLoadError(f"Blog directory does not exist: {BLOG_DIR}")

    if not BLOG_DIR.is_dir():
        raise MarkdownLoadError(f"Blog path is not a directory: {BLOG_DIR}")

    posts: list[BlogPost] = []
    for file_path in sorted(BLOG_DIR.glob("*.md")):
        post = normalize_post(file_path)
        if not include_drafts and post.draft:
            continue
        posts.append(post)

    return posts


def load_latest_post_by_author(
    author: str,
    *,
    include_drafts: bool = False,
) -> BlogPost | None:
    """
    Load the latest post by a specific author.

    Args:
        author: Author name to match exactly after trim.
        include_drafts: Whether draft posts should be considered.

    Returns:
        Latest BlogPost by author, or None when no post exists.

    Raises:
        MarkdownLoadError: If author is empty or any post is invalid.
    """
    normalized_author = author.strip()
    if not normalized_author:
        raise MarkdownLoadError("Author cannot be empty when querying latest post.")

    posts = [
        post
        for post in load_all_posts(include_drafts=include_drafts)
        if post.author.strip() == normalized_author
    ]
    if not posts:
        return None

    posts.sort(
        key=lambda post: (
            parse_date_as_date(post.date, Path(post.source_path)),
            post.slug,
        ),
        reverse=True,
    )
    return posts[0]


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments.

    Returns:
        Parsed CLI namespace.
    """
    parser = argparse.ArgumentParser(
        description="Load blog markdown posts from src/content/blog."
    )
    parser.add_argument(
        "--slug",
        type=str,
        help="Load a single post by slug.",
    )
    parser.add_argument(
        "--include-drafts",
        action="store_true",
        help="Include draft posts when loading all posts.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
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
        if args.slug:
            result: BlogPost | list[BlogPost] = load_post_by_slug(args.slug)
        else:
            result = load_all_posts(include_drafts=args.include_drafts)

        output_data: Any
        if isinstance(result, BlogPost):
            output_data = asdict(result)
        else:
            output_data = [asdict(post) for post in result]

        if args.pretty:
            print(json.dumps(output_data, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(output_data, ensure_ascii=False))

        return 0

    except MarkdownLoadError as exc:
        print(f"[load_markdown.py] ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
