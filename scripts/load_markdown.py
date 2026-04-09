# Purpose: Load blog markdown files, parse frontmatter and body, and return normalized post data.

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
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
    draft: bool
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
    draft = bool(frontmatter.get("draft", False))

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
        draft=draft,
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