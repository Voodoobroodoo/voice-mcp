"""Voice MCP error codes matching docs/mcp-voice-schema.md."""

from __future__ import annotations

from typing import Any


class VoiceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        session_id: str | None = None,
        state: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.session_id = session_id
        self.state = state

    def to_dict(self) -> dict[str, Any]:
        err: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.session_id is not None:
            err["session_id"] = self.session_id
        if self.state is not None:
            err["state"] = self.state
        return {"error": err}
