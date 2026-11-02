"""The TUI's only way to the daemon. Nothing under tui/ imports the daemon, the
stores, or a provider, so the Claude Code provider replaces the mock with no TUI
change. A test holds that line."""

import json
import uuid
from pathlib import Path

import httpx


class ApiError(Exception):
    def __init__(self, status, code, message, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


class ConnectionLost(Exception):
    """The daemon cannot be reached."""


def run_path(slug, run_id):
    return f"/v1/projects/{slug}/runs/{run_id}"


class ApiClient:
    def __init__(self, base_url, token):
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {token}"}
        self.http = httpx.AsyncClient(base_url=base_url, headers=self.headers, timeout=30)

    @classmethod
    def from_home(cls, home):
        """Find a running daemon from the files it wrote. Raises OSError with none."""
        home = Path(home)
        port = json.loads((home / "daemon.json").read_text())["port"]
        return cls(f"http://127.0.0.1:{port}", (home / "api-token").read_text().strip())

    async def close(self):
        await self.http.aclose()

    def _raise_for(self, response):
        if response.status_code < 400:
            return
        try:
            error = response.json()["error"]
        except (ValueError, KeyError):
            error = {"code": "internal", "message": response.text[:200]}
        raise ApiError(response.status_code, error["code"], error["message"], error.get("details"))

    async def _request(self, method, path, **kwargs):
        try:
            response = await self.http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise ConnectionLost(str(exc)) from exc
        self._raise_for(response)
        return response

    async def get(self, path, **params):
        params = {k: v for k, v in params.items() if v is not None}
        return (await self._request("GET", path, params=params)).json()

    async def post(self, path, body):
        """A read that takes a body (e.g. proofreading text not yet written)."""
        return (await self._request("POST", path, json=body)).json()

    async def get_text(self, path):
        return (await self._request("GET", path)).text

    async def op(self, kind, args=None, project=None, run_id=None, confirm_token=None, op_id=None):
        body = {"op_id": op_id or str(uuid.uuid4()), "type": kind, "project": project, "run_id": run_id,
                "args": args or {}, "confirm_token": confirm_token}
        return (await self._request("POST", "/v1/operations", json=body)).json()

    async def stream(self, path, method="GET", **kwargs):
        """Yield (event, data, id) frames until the server closes the stream."""
        event, data, frame_id = None, None, None
        try:
            async with self.http.stream(method, path, timeout=None, **kwargs) as response:
                if response.status_code >= 400:
                    await response.aread()
                    self._raise_for(response)
                async for line in response.aiter_lines():
                    if line.startswith("id: "):
                        frame_id = line[4:]
                    elif line.startswith("event: "):
                        event = line[7:]
                    elif line.startswith("data: "):
                        data = json.loads(line[6:])
                    elif not line and event:
                        yield event, data, frame_id
                        event, data, frame_id = None, None, None
        except httpx.TransportError as exc:
            raise ConnectionLost(str(exc)) from exc
