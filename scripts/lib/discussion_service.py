"""Discussion resolve/backfill service shared by publishing flows."""

from __future__ import annotations

import os
import re
from pathlib import Path

from github_discussions import (
    GitHubDiscussionError,
    create_discussion,
    find_discussion_by_title,
    load_github_token,
    update_discussion_title,
)
from load_markdown import BlogPost


FRONTMATTER_PATTERN = re.compile(
    r"^---\r?\n(.*?)\r?\n---(\r?\n?.*)$",
    re.DOTALL,
)


def resolve_repo_for_discussion_lookup(
    *,
    repo_owner: str,
    repo_name: str,
    error_cls: type[Exception],
) -> tuple[str, str]:
    """Resolve owner/name from CLI args or GITHUB_REPOSITORY."""
    owner = repo_owner.strip()
    name = repo_name.strip()
    if owner and name:
        return owner, name
    if owner or name:
        raise error_cls("Both --repo-owner and --repo-name are required together.")

    github_repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    if "/" not in github_repository:
        raise error_cls(
            "Missing repository info. Set --repo-owner/--repo-name, "
            "or provide GITHUB_REPOSITORY=owner/repo."
        )
    env_owner, env_repo = github_repository.split("/", 1)
    env_owner = env_owner.strip()
    env_repo = env_repo.strip()
    if not env_owner or not env_repo:
        raise error_cls(f"Invalid GITHUB_REPOSITORY value: {github_repository}")
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
    error_cls: type[Exception],
) -> str:
    """Resolve one discussion ID by frontmatter / canonical title / auto-create."""
    configured_discussion_id = post.discussion_id.strip()
    if configured_discussion_id:
        return configured_discussion_id

    owner, name = resolve_repo_for_discussion_lookup(
        repo_owner=repo_owner,
        repo_name=repo_name,
        error_cls=error_cls,
    )
    if discussion_search_limit <= 0:
        raise error_cls("--discussion-search-limit must be greater than 0.")

    canonical_mapping_key = f"blog/{post.slug}/"

    def find_by_title(title_text: str) -> list[dict[str, object]]:
        try:
            return find_discussion_by_title(
                token=github_token,
                owner=owner,
                repo=name,
                title=title_text,
                limit=discussion_search_limit,
            )
        except GitHubDiscussionError as exc:
            raise error_cls(
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
            raise error_cls(
                f"Multiple legacy discussions match title '{post.title}'. "
                f"Set discussionId in frontmatter to disambiguate. "
                f"Candidates: {legacy_candidates}"
            )
        if len(legacy_title_matches) == 1:
            legacy_discussion = legacy_title_matches[0]
            legacy_discussion_id = str(legacy_discussion.get("id", "")).strip()
            if not legacy_discussion_id:
                raise error_cls(
                    f"Found legacy discussion for '{post.title}', but ID is empty."
                )
            try:
                updated_discussion = update_discussion_title(
                    token=github_token,
                    discussion_id=legacy_discussion_id,
                    title=canonical_mapping_key,
                )
            except GitHubDiscussionError as exc:
                raise error_cls(
                    f"Failed to rename legacy discussion '{post.title}' "
                    f"to '{canonical_mapping_key}': {exc}"
                ) from exc
            print(
                "[discussion_service] Renamed legacy discussion title to pathname key: "
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
            raise error_cls(
                f"Post '{post.slug}' has no discussionId, no matching discussion by canonical key, "
                f"and auto-create failed: {exc}"
            ) from exc

        created_discussion_id = str(created_discussion.get("id", "")).strip()
        if not created_discussion_id:
            raise error_cls(
                f"Discussion auto-created for post '{post.slug}', but returned ID is empty."
            )
        print(
            "[discussion_service] Created discussion automatically: "
            f"{created_discussion.get('url', '')}"
        )
        return created_discussion_id

    if len(matches) > 1:
        candidates = ", ".join(
            f"{item.get('id', '')}:{item.get('title', '')}" for item in matches[:5]
        )
        raise error_cls(
            f"Multiple discussions match canonical key '{canonical_mapping_key}'. "
            f"Set discussionId in frontmatter to disambiguate. Candidates: {candidates}"
        )

    resolved_discussion_id = str(matches[0].get("id", "")).strip()
    if not resolved_discussion_id:
        raise error_cls(
            f"Found discussion for title '{post.title}', but ID is empty."
        )
    return resolved_discussion_id


def persist_discussion_id_to_frontmatter(
    *,
    post: BlogPost,
    discussion_id: str,
    error_cls: type[Exception],
) -> Path | None:
    """Backfill discussionId into markdown frontmatter when it is missing."""
    if post.discussion_id.strip():
        return None

    markdown_path = Path(post.source_path)
    try:
        raw_text = markdown_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise error_cls(
            f"Failed to read markdown for discussionId backfill: {markdown_path}"
        ) from exc

    match = FRONTMATTER_PATTERN.match(raw_text)
    if not match:
        raise error_cls(
            "Cannot backfill discussionId because frontmatter format is invalid: "
            f"{markdown_path}"
        )

    frontmatter_text, remainder = match.groups()
    if re.search(r"(?m)^\s*discussionId\s*:", frontmatter_text):
        return None

    newline = "\r\n" if "\r\n" in raw_text else "\n"
    updated_frontmatter = frontmatter_text.rstrip() + newline + f'discussionId: "{discussion_id}"'
    updated_text = f"---{newline}{updated_frontmatter}{newline}---{remainder}"

    try:
        markdown_path.write_text(updated_text, encoding="utf-8")
    except OSError as exc:
        raise error_cls(
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
    error_cls: type[Exception],
    github_token: str | None = None,
) -> tuple[str, Path | None]:
    """Resolve and backfill discussion ID for a post."""
    token = github_token or load_github_token()
    discussion_id = resolve_discussion_id(
        post=post,
        github_token=token,
        repo_owner=repo_owner,
        repo_name=repo_name,
        discussion_search_limit=discussion_search_limit,
        discussion_category_id=discussion_category_id,
        discussion_category_name=discussion_category_name,
        error_cls=error_cls,
    )
    saved_markdown_path = persist_discussion_id_to_frontmatter(
        post=post,
        discussion_id=discussion_id,
        error_cls=error_cls,
    )
    return discussion_id, saved_markdown_path

