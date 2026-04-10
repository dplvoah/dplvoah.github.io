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