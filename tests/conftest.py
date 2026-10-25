"""Ensure stub mode + pytest-asyncio plugin are available."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("VOICE_MCP_STUB", "1")

# Make missing pytest-asyncio an explicit install error (not cryptic async failures)
pytest.importorskip("pytest_asyncio")
