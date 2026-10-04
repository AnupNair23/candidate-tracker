"""Server-sent events framing for the search stream."""

from __future__ import annotations

import json
from typing import Any


def sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n".encode()
