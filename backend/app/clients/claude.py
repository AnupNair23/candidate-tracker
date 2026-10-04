"""Thin async wrapper over the Anthropic SDK for schema-constrained calls.

Uses `beta.messages.create` with `output_config.format` (JSON schema from the Pydantic model via
`anthropic.transform_schema`) rather than `messages.parse`, so `stop_reason` (refusal / max_tokens)
is checked *before* the body is validated, and validation failures keep the raw text for repair.
Server-side refusal fallback (`fallbacks: "default"`) is on unless CLAUDE_FALLBACKS_ENABLED=false.
"""

from __future__ import annotations

import logging
from typing import Any

import anthropic
from anthropic import AsyncAnthropic, transform_schema
from pydantic import ValidationError

from app.clients.claude_errors import (
    ClaudeAuthError,
    ClaudeError,
    ClaudeNotConfigured,
    ClaudeOutputInvalid,
    ClaudeRateLimited,
    ClaudeRefusal,
    ClaudeTruncated,
    ClaudeUnavailable,
)
from app.constants.llm import DEFAULT_MAX_TOKENS, FALLBACK_BETA, UNAVAILABLE_STATUS_CODES
from app.core.config import Settings
from app.models.llm import ClaudeResult, T

log = logging.getLogger("app.claude")


def _retry_after(exc: anthropic.APIStatusError) -> float | None:
    try:
        value = exc.response.headers.get("retry-after")
        return float(value) if value else None
    except (AttributeError, ValueError):
        return None


class ClaudeClient:
    def __init__(self, settings: Settings, client: Any | None = None):
        self.model = settings.claude_model
        self._fallbacks = settings.claude_fallbacks_enabled
        if client is not None:
            self._client = client
        elif settings.anthropic_api_key is None:
            self._client = None
        else:
            self._client = AsyncAnthropic(
                api_key=settings.anthropic_api_key.get_secret_value(),
                max_retries=settings.claude_max_retries,
                timeout=settings.claude_timeout_s,
            )

    @property
    def configured(self) -> bool:
        return self._client is not None

    async def structured(
        self,
        *,
        system: str,
        content: list[dict[str, Any]],
        output_model: type[T],
        effort: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> ClaudeResult[T]:
        if self._client is None:
            raise ClaudeNotConfigured("ANTHROPIC_API_KEY is not configured")
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": content}],
            "output_config": {
                "format": {"type": "json_schema", "schema": transform_schema(output_model)},
                "effort": effort,
            },
        }
        if self._fallbacks:
            kwargs["betas"] = [FALLBACK_BETA]
            kwargs["fallbacks"] = "default"

        try:
            resp = await self._client.beta.messages.create(**kwargs)
        except anthropic.RateLimitError as exc:
            raise ClaudeRateLimited("Claude is rate-limiting requests", retry_after=_retry_after(exc)) from exc
        except anthropic.AuthenticationError as exc:
            raise ClaudeAuthError("Claude rejected the configured API key") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code in UNAVAILABLE_STATUS_CODES:
                raise ClaudeUnavailable(f"Claude is unavailable (HTTP {exc.status_code})") from exc
            raise ClaudeError(f"Claude request failed (HTTP {exc.status_code})") from exc
        except anthropic.APIConnectionError as exc:
            raise ClaudeUnavailable(f"Could not reach Claude: {type(exc).__name__}") from exc

        usage = resp.usage.model_dump() if getattr(resp, "usage", None) is not None else {}
        log.info(
            "claude model=%s stop=%s in=%s out=%s cache_read=%s",
            resp.model,
            resp.stop_reason,
            usage.get("input_tokens"),
            usage.get("output_tokens"),
            usage.get("cache_read_input_tokens"),
        )
        if resp.stop_reason == "refusal":
            raise ClaudeRefusal("Claude declined this request")
        text = "".join(block.text for block in resp.content if getattr(block, "type", None) == "text")
        if resp.stop_reason == "max_tokens":
            raise ClaudeTruncated("Claude output hit max_tokens", raw_text=text)
        try:
            parsed = output_model.model_validate_json(text)
        except ValidationError as exc:
            raise ClaudeOutputInvalid(
                f"Claude output failed schema validation: {exc.error_count()} errors", raw_text=text
            ) from exc
        return ClaudeResult(
            parsed=parsed,
            raw_text=text,
            model=resp.model,
            fallback_used=resp.model != self.model,
            usage=usage,
        )
