# List recent discussions ```python scripts/github_discussions.py --owner dplvoah --repo dplvoah.github.io --list-discussions```

# Find discussions by title ```python scripts/github_discussions.py --owner dplvoah --repo dplvoah.github.io --find-by-title "Discussion Title"```

# Purpose: Query GitHub Discussions and publish AI-generated comments via GraphQL API.

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Final

import requests
from dotenv import load_dotenv


ROOT_DIR: Final[Path] = Path(__file__).resolve().parent.parent
GITHUB_GRAPHQL_API_URL: Final[str] = "https://api.github.com/graphql"
REQUEST_TIMEOUT_SECONDS: Final[int] = 60
DEFAULT_LIST_LIMIT: Final[int] = 20
DEFAULT_DISCUSSION_COMMENT_LIMIT: Final[int] = 100


class GitHubDiscussionError(Exception):
    """Raised when GitHub Discussions API operations fail."""


def load_github_token() -> str:
    """
    Load AI GitHub token from environment.

    Returns:
        GitHub token string.

    Raises:
        GitHubDiscussionError: If token is missing.
    """
    load_dotenv()

    token = os.getenv("AI_GITHUB_TOKEN", "").strip()
    if not token:
        raise GitHubDiscussionError(
            "Missing AI_GITHUB_TOKEN. Set it in environment or .env file."
        )

    return token


def execute_github_graphql_query(
    *,
    token: str,
    query: str,
    variables: dict[str, Any],
) -> dict[str, Any]:
    """
    Execute a GitHub GraphQL request.

    Args:
        token: GitHub authentication token.
        query: GraphQL query or mutation string.
        variables: GraphQL variables.

    Returns:
        Parsed JSON response.

    Raises:
        GitHubDiscussionError: If request fails or response is invalid.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
    }

    payload = {
        "query": query,
        "variables": variables,
    }

    try:
        response = requests.post(
            GITHUB_GRAPHQL_API_URL,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise GitHubDiscussionError(f"GitHub GraphQL request failed: {exc}") from exc

    if response.status_code != 200:
        raise GitHubDiscussionError(
            f"GitHub GraphQL API returned {response.status_code}: {response.text}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise GitHubDiscussionError(
            "Failed to decode GitHub GraphQL JSON response."
        ) from exc

    if "errors" in data and data["errors"]:
        raise GitHubDiscussionError(
            f"GitHub GraphQL returned errors: "
            f"{json.dumps(data['errors'], ensure_ascii=False)}"
        )

    return data


def list_discussions(
    *,
    token: str,
    owner: str,
    repo: str,
    limit: int,
) -> list[dict[str, Any]]:
    """
    List discussions in a repository.

    Args:
        token: GitHub authentication token.
        owner: Repository owner.
        repo: Repository name.
        limit: Max number of discussions to fetch.

    Returns:
        List of normalized discussion dictionaries.

    Raises:
        GitHubDiscussionError: If repository query fails.
    """
    query = """
    query ListDiscussions($owner: String!, $repo: String!, $limit: Int!) {
      repository(owner: $owner, name: $repo) {
        discussions(first: $limit, orderBy: {field: CREATED_AT, direction: DESC}) {
          nodes {
            id
            number
            title
            url
            createdAt
            updatedAt
          }
        }
      }
    }
    """

    variables = {
        "owner": owner,
        "repo": repo,
        "limit": limit,
    }

    data = execute_github_graphql_query(
        token=token,
        query=query,
        variables=variables,
    )

    try:
        nodes = data["data"]["repository"]["discussions"]["nodes"]
    except (KeyError, TypeError) as exc:
        raise GitHubDiscussionError(
            "GitHub response missing repository.discussions.nodes"
        ) from exc

    if nodes is None:
        raise GitHubDiscussionError(
            f"Repository not found or discussions unavailable: {owner}/{repo}"
        )

    discussions: list[dict[str, Any]] = []
    for node in nodes:
        if not node:
            continue

        discussions.append(
            {
                "id": node.get("id", ""),
                "number": node.get("number"),
                "title": node.get("title", ""),
                "url": node.get("url", ""),
                "createdAt": node.get("createdAt", ""),
                "updatedAt": node.get("updatedAt", ""),
            }
        )

    return discussions


def find_discussion_by_title(
    *,
    token: str,
    owner: str,
    repo: str,
    title: str,
    limit: int,
) -> list[dict[str, Any]]:
    """
    Find discussions by exact or partial title match.

    Args:
        token: GitHub authentication token.
        owner: Repository owner.
        repo: Repository name.
        title: Title text to search.
        limit: Max number of discussions to inspect.

    Returns:
        Matching discussion dictionaries.

    Raises:
        GitHubDiscussionError: If title is empty.
    """
    search_text = title.strip()
    if not search_text:
        raise GitHubDiscussionError("Discussion title search text cannot be empty.")

    discussions = list_discussions(
        token=token,
        owner=owner,
        repo=repo,
        limit=limit,
    )

    exact_matches = [
        item for item in discussions
        if item["title"].strip().lower() == search_text.lower()
    ]
    if exact_matches:
        return exact_matches

    partial_matches = [
        item for item in discussions
        if search_text.lower() in item["title"].strip().lower()
    ]
    return partial_matches


def add_discussion_comment(
    *,
    token: str,
    discussion_id: str,
    body: str,
) -> dict[str, Any]:
    """
    Add a comment to a GitHub Discussion.

    Args:
        token: GitHub authentication token.
        discussion_id: GitHub Discussion node ID.
        body: Comment body text.

    Returns:
        Parsed comment data.

    Raises:
        GitHubDiscussionError: If body is empty or API call fails.
    """
    normalized_discussion_id = discussion_id.strip()
    if not normalized_discussion_id:
        raise GitHubDiscussionError("Discussion ID cannot be empty.")

    comment_body = body.strip()
    if not comment_body:
        raise GitHubDiscussionError("Discussion comment body cannot be empty.")

    mutation = """
    mutation AddDiscussionComment($discussionId: ID!, $body: String!) {
      addDiscussionComment(input: {discussionId: $discussionId, body: $body}) {
        comment {
          id
          url
          body
          createdAt
          author {
            login
          }
          discussion {
            id
          }
        }
      }
    }
    """

    variables = {
        "discussionId": normalized_discussion_id,
        "body": comment_body,
    }

    data = execute_github_graphql_query(
        token=token,
        query=mutation,
        variables=variables,
    )

    try:
        comment = data["data"]["addDiscussionComment"]["comment"]
    except (KeyError, TypeError) as exc:
        raise GitHubDiscussionError(
            "GitHub response missing addDiscussionComment.comment"
        ) from exc

    return comment


def list_discussion_comments(
    *,
    token: str,
    discussion_id: str,
    limit: int = DEFAULT_DISCUSSION_COMMENT_LIMIT,
) -> list[dict[str, Any]]:
    """
    List comments for a GitHub Discussion by discussion node ID.

    Args:
        token: GitHub authentication token.
        discussion_id: GitHub Discussion node ID.
        limit: Maximum comments to fetch.

    Returns:
        List of normalized discussion comments.

    Raises:
        GitHubDiscussionError: If discussion lookup fails.
    """
    normalized_discussion_id = discussion_id.strip()
    if not normalized_discussion_id:
        raise GitHubDiscussionError("Discussion ID cannot be empty.")
    if limit <= 0:
        raise GitHubDiscussionError("Comment list limit must be greater than 0.")

    query = """
    query DiscussionComments($discussionId: ID!, $pageSize: Int!, $cursor: String) {
      node(id: $discussionId) {
        ... on Discussion {
          comments(first: $pageSize, after: $cursor) {
            nodes {
              id
              body
              createdAt
              author {
                login
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
      }
    }
    """

    page_size = min(50, limit)
    cursor: str | None = None
    comments: list[dict[str, Any]] = []

    while len(comments) < limit:
        variables = {
            "discussionId": normalized_discussion_id,
            "pageSize": page_size,
            "cursor": cursor,
        }
        data = execute_github_graphql_query(
            token=token,
            query=query,
            variables=variables,
        )

        try:
            node = data["data"]["node"]
            comment_connection = node["comments"] if node else None
            nodes = comment_connection["nodes"] if comment_connection else None
            page_info = comment_connection["pageInfo"] if comment_connection else None
        except (KeyError, TypeError) as exc:
            raise GitHubDiscussionError(
                "GitHub response missing discussion comments fields."
            ) from exc

        if nodes is None:
            raise GitHubDiscussionError(
                f"Discussion not found or inaccessible: {normalized_discussion_id}"
            )

        for item in nodes:
            if not item:
                continue
            comments.append(
                {
                    "id": str(item.get("id", "")).strip(),
                    "body": str(item.get("body", "")).strip(),
                    "createdAt": str(item.get("createdAt", "")).strip(),
                    "author_login": str(
                        (item.get("author") or {}).get("login", "")
                    ).strip(),
                }
            )
            if len(comments) >= limit:
                break

        has_next_page = bool((page_info or {}).get("hasNextPage"))
        cursor = (page_info or {}).get("endCursor")
        if not has_next_page or not cursor:
            break

    return comments


def delete_discussion_comment(
    *,
    token: str,
    comment_id: str,
) -> None:
    """
    Delete a GitHub Discussion comment by node ID.

    Args:
        token: GitHub authentication token.
        comment_id: Discussion comment node ID.

    Raises:
        GitHubDiscussionError: If deletion fails.
    """
    normalized_comment_id = comment_id.strip()
    if not normalized_comment_id:
        raise GitHubDiscussionError("Comment ID cannot be empty.")

    mutation = """
    mutation DeleteDiscussionComment($id: ID!) {
      deleteDiscussionComment(input: {id: $id}) {
        clientMutationId
      }
    }
    """
    variables = {
        "id": normalized_comment_id,
    }

    execute_github_graphql_query(
        token=token,
        query=mutation,
        variables=variables,
    )


def get_repository_discussion_context(
    *,
    token: str,
    owner: str,
    repo: str,
) -> dict[str, Any]:
    """
    Fetch repository node ID and available discussion categories.

    Args:
        token: GitHub authentication token.
        owner: Repository owner.
        repo: Repository name.

    Returns:
        Dictionary with repository id, url, and discussion categories.

    Raises:
        GitHubDiscussionError: If repository fields are missing.
    """
    query = """
    query RepositoryDiscussionContext($owner: String!, $repo: String!) {
      repository(owner: $owner, name: $repo) {
        id
        url
        discussionCategories(first: 50) {
          nodes {
            id
            name
            emoji
          }
        }
      }
    }
    """
    variables = {
        "owner": owner,
        "repo": repo,
    }

    data = execute_github_graphql_query(
        token=token,
        query=query,
        variables=variables,
    )

    try:
        repository = data["data"]["repository"]
        repository_id = str(repository["id"]).strip()
        repository_url = str(repository.get("url", "")).strip()
        categories = repository["discussionCategories"]["nodes"] or []
    except (KeyError, TypeError) as exc:
        raise GitHubDiscussionError(
            "GitHub response missing repository discussion context."
        ) from exc

    if not repository_id:
        raise GitHubDiscussionError(f"Repository not found or inaccessible: {owner}/{repo}")

    normalized_categories = [
        {
            "id": str(item.get("id", "")).strip(),
            "name": str(item.get("name", "")).strip(),
            "emoji": str(item.get("emoji", "")).strip(),
        }
        for item in categories
        if item
    ]

    return {
        "repository_id": repository_id,
        "repository_url": repository_url,
        "categories": normalized_categories,
    }


def resolve_discussion_category_id(
    *,
    categories: list[dict[str, Any]],
    category_id: str,
    category_name: str,
) -> str:
    """
    Resolve usable category ID from available categories.

    Args:
        categories: Available repository discussion categories.
        category_id: Preferred category node ID.
        category_name: Preferred category name.

    Returns:
        Resolved category ID.

    Raises:
        GitHubDiscussionError: If category cannot be resolved.
    """
    normalized_category_id = category_id.strip()
    normalized_category_name = category_name.strip()

    if not categories:
        raise GitHubDiscussionError(
            "Repository has no discussion categories available."
        )

    if normalized_category_id:
        for item in categories:
            if item.get("id", "").strip() == normalized_category_id:
                return normalized_category_id

        available_ids = ", ".join(
            item.get("id", "") for item in categories if item.get("id", "")
        )
        raise GitHubDiscussionError(
            f"Configured category ID not found: {normalized_category_id}. "
            f"Available IDs: {available_ids}"
        )

    if normalized_category_name:
        target = normalized_category_name.lower()
        for item in categories:
            if item.get("name", "").strip().lower() == target:
                return item.get("id", "").strip()

    available_names = ", ".join(
        item.get("name", "") for item in categories if item.get("name", "")
    )
    raise GitHubDiscussionError(
        f"Discussion category not found by name '{normalized_category_name}'. "
        f"Available categories: {available_names}"
    )


def create_discussion(
    *,
    token: str,
    owner: str,
    repo: str,
    title: str,
    body: str,
    category_id: str = "",
    category_name: str = "Comments",
) -> dict[str, Any]:
    """
    Create a GitHub Discussion in the target repository.

    Args:
        token: GitHub authentication token.
        owner: Repository owner.
        repo: Repository name.
        title: Discussion title.
        body: Discussion body markdown.
        category_id: Optional category node ID.
        category_name: Category name fallback if category_id is absent.

    Returns:
        Created discussion payload.

    Raises:
        GitHubDiscussionError: If validation or API request fails.
    """
    normalized_title = title.strip()
    normalized_body = body.strip()
    if not normalized_title:
        raise GitHubDiscussionError("Discussion title cannot be empty.")
    if not normalized_body:
        raise GitHubDiscussionError("Discussion body cannot be empty.")

    context = get_repository_discussion_context(
        token=token,
        owner=owner,
        repo=repo,
    )
    resolved_category_id = resolve_discussion_category_id(
        categories=context["categories"],
        category_id=category_id,
        category_name=category_name,
    )

    mutation = """
    mutation CreateDiscussion(
      $repositoryId: ID!,
      $categoryId: ID!,
      $title: String!,
      $body: String!
    ) {
      createDiscussion(
        input: {
          repositoryId: $repositoryId,
          categoryId: $categoryId,
          title: $title,
          body: $body
        }
      ) {
        discussion {
          id
          number
          title
          url
          createdAt
          category {
            id
            name
          }
        }
      }
    }
    """
    variables = {
        "repositoryId": context["repository_id"],
        "categoryId": resolved_category_id,
        "title": normalized_title,
        "body": normalized_body,
    }

    data = execute_github_graphql_query(
        token=token,
        query=mutation,
        variables=variables,
    )
    try:
        discussion = data["data"]["createDiscussion"]["discussion"]
    except (KeyError, TypeError) as exc:
        raise GitHubDiscussionError(
            "GitHub response missing createDiscussion.discussion"
        ) from exc

    return discussion


def update_discussion_title(
    *,
    token: str,
    discussion_id: str,
    title: str,
) -> dict[str, Any]:
    """
    Update an existing GitHub Discussion title.

    Args:
        token: GitHub authentication token.
        discussion_id: Discussion node ID.
        title: New discussion title.

    Returns:
        Updated discussion payload.

    Raises:
        GitHubDiscussionError: If inputs are invalid or update fails.
    """
    normalized_discussion_id = discussion_id.strip()
    normalized_title = title.strip()
    if not normalized_discussion_id:
        raise GitHubDiscussionError("Discussion ID cannot be empty for title update.")
    if not normalized_title:
        raise GitHubDiscussionError("Discussion title cannot be empty for update.")

    mutation = """
    mutation UpdateDiscussionTitle($discussionId: ID!, $title: String!) {
      updateDiscussion(input: {discussionId: $discussionId, title: $title}) {
        discussion {
          id
          number
          title
          url
          updatedAt
        }
      }
    }
    """
    variables = {
        "discussionId": normalized_discussion_id,
        "title": normalized_title,
    }

    data = execute_github_graphql_query(
        token=token,
        query=mutation,
        variables=variables,
    )
    try:
        updated = data["data"]["updateDiscussion"]["discussion"]
    except (KeyError, TypeError) as exc:
        raise GitHubDiscussionError(
            "GitHub response missing updateDiscussion.discussion"
        ) from exc

    return updated


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments.

    Returns:
        Parsed CLI arguments.
    """
    parser = argparse.ArgumentParser(
        description="Query GitHub Discussions and publish comments."
    )

    parser.add_argument(
        "--owner",
        type=str,
        help="Repository owner, required for listing or finding discussions.",
    )
    parser.add_argument(
        "--repo",
        type=str,
        help="Repository name, required for listing or finding discussions.",
    )
    parser.add_argument(
        "--list-discussions",
        action="store_true",
        help="List recent discussions in the repository.",
    )
    parser.add_argument(
        "--find-by-title",
        type=str,
        help="Find discussions by title text.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIST_LIMIT,
        help="Max number of discussions to fetch when listing or searching.",
    )
    parser.add_argument(
        "--discussion-id",
        type=str,
        help="GitHub Discussion node ID for publishing a comment.",
    )
    parser.add_argument(
        "--body",
        type=str,
        help="Comment body text to publish.",
    )

    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    """
    Validate CLI argument combinations.

    Args:
        args: Parsed CLI arguments.

    Raises:
        GitHubDiscussionError: If argument combination is invalid.
    """
    if args.list_discussions or args.find_by_title:
        if not args.owner or not args.repo:
            raise GitHubDiscussionError(
                "--owner and --repo are required for listing or finding discussions."
            )

    if args.discussion_id and not args.body:
        raise GitHubDiscussionError(
            "--body is required when using --discussion-id."
        )

    if args.body and not args.discussion_id:
        raise GitHubDiscussionError(
            "--discussion-id is required when using --body."
        )

    if not args.list_discussions and not args.find_by_title and not args.discussion_id:
        raise GitHubDiscussionError(
            "Choose one action: --list-discussions, --find-by-title, or "
            "--discussion-id with --body."
        )


def main() -> int:
    """
    CLI entry point.

    Returns:
        Process exit code.
    """
    args = parse_args()

    try:
        validate_args(args)
        token = load_github_token()

        if args.list_discussions:
            discussions = list_discussions(
                token=token,
                owner=args.owner,
                repo=args.repo,
                limit=args.limit,
            )
            print(json.dumps(discussions, ensure_ascii=False, indent=2))
            return 0

        if args.find_by_title:
            matches = find_discussion_by_title(
                token=token,
                owner=args.owner,
                repo=args.repo,
                title=args.find_by_title,
                limit=args.limit,
            )
            print(json.dumps(matches, ensure_ascii=False, indent=2))
            return 0

        comment = add_discussion_comment(
            token=token,
            discussion_id=args.discussion_id,
            body=args.body,
        )
        print(json.dumps(comment, ensure_ascii=False, indent=2))
        return 0

    except GitHubDiscussionError as exc:
        print(f"[github_discussions.py] ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
