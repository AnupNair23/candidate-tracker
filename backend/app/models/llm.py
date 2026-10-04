"""Result of a schema-constrained Claude call (see `app.clients.claude.ClaudeClient.structured`)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass
class ClaudeResult(Generic[T]):
    parsed: T
    raw_text: str
    model: str
    fallback_used: bool
    usage: dict[str, Any]
