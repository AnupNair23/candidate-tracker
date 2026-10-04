"""Logging setup, including redaction of query strings (JobDiva v1 credentials) from every log line."""

from __future__ import annotations

import logging
import re


class RedactQueryStrings(logging.Filter):
    """JobDiva v1 authenticates with credentials in the query string — never let them reach logs."""

    _re = re.compile(r"(https?://[^\s?\"']+)\?[^\s\"']*")

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._re.sub(r"\1?<redacted>", str(record.msg))
        if record.args:
            record.args = tuple(self._re.sub(r"\1?<redacted>", a) if isinstance(a, str) else a for a in record.args)
        return True


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    redact = RedactQueryStrings()
    for name in ("httpx", "httpcore", "uvicorn.access", "app"):
        logger = logging.getLogger(name)
        logger.addFilter(redact)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
