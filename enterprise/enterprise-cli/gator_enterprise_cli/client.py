"""HTTP client for the Enterprise API. Pure HTTP — no app internals."""

import sys

import httpx

from gator_enterprise_cli.config import CliConfig


class CliError(Exception):
    """CLI-level error with formatted message."""
    def __init__(self, message: str, exit_code: int = 1):
        self.message = message
        self.exit_code = exit_code
        super().__init__(message)


class EnterpriseClient:
    """Thin HTTP client wrapping the Enterprise API."""

    def __init__(self, config: CliConfig):
        self._base = config.base_url
        self._headers = {
            "Authorization": f"Bearer {config.token}",
            "Content-Type": "application/json",
        }

    def get(self, path: str, params: dict | None = None) -> dict:
        """GET request. Returns parsed JSON or raises CliError."""
        url = f"{self._base}{path}"
        try:
            resp = httpx.get(url, headers=self._headers, params=params, timeout=30.0)
        except httpx.ConnectError:
            raise CliError(f"Connection failed: {self._base}")
        except httpx.TimeoutException:
            raise CliError(f"Request timed out: {url}")

        return self._handle_response(resp)

    def post(self, path: str, json: dict | None = None) -> dict:
        """POST request. Returns parsed JSON or raises CliError."""
        url = f"{self._base}{path}"
        try:
            resp = httpx.post(url, headers=self._headers, json=json, timeout=30.0)
        except httpx.ConnectError:
            raise CliError(f"Connection failed: {self._base}")
        except httpx.TimeoutException:
            raise CliError(f"Request timed out: {url}")

        return self._handle_response(resp)

    def put(self, path: str, json: dict | None = None) -> dict:
        """PUT request. Returns parsed JSON or raises CliError."""
        url = f"{self._base}{path}"
        try:
            resp = httpx.put(url, headers=self._headers, json=json, timeout=30.0)
        except httpx.ConnectError:
            raise CliError(f"Connection failed: {self._base}")
        except httpx.TimeoutException:
            raise CliError(f"Request timed out: {url}")

        return self._handle_response(resp)

    def _handle_response(self, resp: httpx.Response) -> dict:
        """Parse response. Raises CliError on non-2xx with formatted message."""
        if resp.status_code >= 200 and resp.status_code < 300:
            return resp.json()

        # Try to extract error envelope
        try:
            body = resp.json()
            error = body.get("error", {})
            code = error.get("code", "unknown")
            message = error.get("message", resp.text)
            raise CliError(f"Error ({resp.status_code} {code}): {message}")
        except (ValueError, KeyError):
            raise CliError(f"Error ({resp.status_code}): {resp.text}")
