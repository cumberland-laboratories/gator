"""GitHub App provider adapter.

Handles JWT generation, installation token exchange, webhook verification,
push event parsing, repo listing, and commit listing.

All auth mechanics are internal — callers use the ProviderAdapter interface.
"""

import hashlib
import hmac
import time
from datetime import datetime, timezone

import httpx
import jwt

from app.providers.base import CommitInfo, RepoInfo

GITHUB_API_BASE = "https://api.github.com"


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


class GitHubAdapter:
    """GitHub App adapter implementing the provider protocol."""

    def __init__(self, app_id: str, private_key: str, installation_id: str, webhook_secret: str = ""):
        self.app_id = app_id
        self.private_key = private_key
        self.installation_id = installation_id
        self.webhook_secret = webhook_secret
        self._token: str | None = None
        self._token_expires_at: float = 0

    def _generate_jwt(self) -> str:
        """Generate a JWT for GitHub App authentication."""
        now = int(time.time())
        payload = {
            "iat": now - 60,  # issued at (60s in past for clock skew)
            "exp": now + (10 * 60),  # expires in 10 minutes
            "iss": self.app_id,
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def _get_installation_token(self) -> str:
        """Get or refresh an installation access token."""
        if self._token and time.time() < self._token_expires_at:
            return self._token

        app_jwt = self._generate_jwt()
        response = httpx.post(
            f"{GITHUB_API_BASE}/app/installations/{self.installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
            },
        )
        response.raise_for_status()
        data = response.json()
        self._token = data["token"]
        # Tokens expire in 1 hour; refresh 5 min early
        self._token_expires_at = time.time() + 3300
        return self._token

    def _headers(self) -> dict:
        """Auth headers for GitHub API requests."""
        token = self._get_installation_token()
        return {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        }

    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        """Verify webhook signature authenticity."""
        return verify_github_signature(payload, signature, self.webhook_secret)

    def parse_push_event(self, payload: dict) -> list[CommitInfo]:
        """Extract commit info from a GitHub push event payload."""
        commits = []
        for c in payload.get("commits", []):
            timestamp = None
            if c.get("timestamp"):
                try:
                    timestamp = datetime.fromisoformat(c["timestamp"])
                except (ValueError, TypeError):
                    pass

            commits.append(CommitInfo(
                sha=c["id"],
                author=c.get("author", {}).get("name") or c.get("author", {}).get("username"),
                message=c.get("message"),
                timestamp=timestamp,
            ))
        return commits

    def list_repositories(self) -> list[RepoInfo]:
        """List all repositories accessible to this installation."""
        repos = []
        page = 1
        while True:
            response = httpx.get(
                f"{GITHUB_API_BASE}/installation/repositories",
                headers=self._headers(),
                params={"per_page": 100, "page": page},
            )
            response.raise_for_status()
            data = response.json()
            for repo in data.get("repositories", []):
                repos.append(RepoInfo(
                    provider_repo_id=str(repo["id"]),
                    name=repo["name"],
                    full_name=repo["full_name"],
                    default_branch=repo.get("default_branch", "main"),
                ))
            if len(data.get("repositories", [])) < 100:
                break
            page += 1
        return repos

    def list_commits_since(self, repo_full_name: str, since: datetime | None) -> list[CommitInfo]:
        """List commits on default branch since a given time. Paginates fully."""
        commits = []
        page = 1
        while True:
            params = {"per_page": 100, "page": page}
            if since:
                params["since"] = since.isoformat()

            response = httpx.get(
                f"{GITHUB_API_BASE}/repos/{repo_full_name}/commits",
                headers=self._headers(),
                params=params,
            )
            response.raise_for_status()
            page_data = response.json()

            if not page_data:
                break

            for c in page_data:
                timestamp = None
                commit_data = c.get("commit", {})
                author_data = commit_data.get("author", {})
                if author_data.get("date"):
                    try:
                        timestamp = datetime.fromisoformat(author_data["date"])
                    except (ValueError, TypeError):
                        pass

                commits.append(CommitInfo(
                    sha=c["sha"],
                    author=author_data.get("name"),
                    message=commit_data.get("message"),
                    timestamp=timestamp,
                ))

            if len(page_data) < 100:
                break
            page += 1

        return commits

    def get_file_at_commit(self, repo_full_name: str, path: str, ref: str) -> bytes | None:
        """Get file content at a specific commit. Returns None if not found."""
        import base64
        response = httpx.get(
            f"{GITHUB_API_BASE}/repos/{repo_full_name}/contents/{path}",
            headers=self._headers(),
            params={"ref": ref},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            return None  # Path is a directory, not a file
        content = data.get("content", "")
        return base64.b64decode(content)

    def list_directory_at_commit(self, repo_full_name: str, path: str, ref: str) -> list[str] | None:
        """List filenames in a directory at a specific commit. Returns None if not found."""
        response = httpx.get(
            f"{GITHUB_API_BASE}/repos/{repo_full_name}/contents/{path}",
            headers=self._headers(),
            params={"ref": ref},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            return None  # Path is a file, not a directory
        return [item["name"] for item in data]
