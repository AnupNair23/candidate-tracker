"""Claude error types. `code` is the stable identifier the UI switches on."""

from __future__ import annotations


class ClaudeError(Exception):
    code = "claude_error"

    def __init__(self, message: str, *, retry_after: float | None = None, raw_text: str | None = None):
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after
        self.raw_text = raw_text


class ClaudeNotConfigured(ClaudeError):
    code = "claude_not_configured"


class ClaudeAuthError(ClaudeError):
    code = "claude_auth_failed"


class ClaudeRateLimited(ClaudeError):
    code = "rate_limited"


class ClaudeUnavailable(ClaudeError):
    code = "claude_unavailable"


class ClaudeRefusal(ClaudeError):
    code = "claude_refusal"


class ClaudeTruncated(ClaudeError):
    code = "claude_max_tokens"


class ClaudeOutputInvalid(ClaudeError):
    code = "claude_output_invalid"
