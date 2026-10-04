"""JobDiva error types. `code` is the stable identifier the UI switches on."""


class JobDivaError(Exception):
    """Base error for JobDiva calls. `code` is a stable identifier surfaced to the UI."""

    code = "jobdiva_error"

    def __init__(self, message: str, *, status: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.retry_after = retry_after


class JobDivaNotConfigured(JobDivaError):
    code = "jobdiva_not_configured"


class JobDivaAuthError(JobDivaError):
    code = "jobdiva_auth_failed"


class JobDivaRateLimited(JobDivaError):
    code = "rate_limited"


class JobDivaUnavailable(JobDivaError):
    code = "jobdiva_unavailable"


class JobDivaNotFound(JobDivaError):
    code = "not_found"


class CallBudgetExhausted(JobDivaError):
    code = "call_budget_exhausted"


# Errors that abort a whole search / request instead of being reported per source.
FATAL_ERRORS = (JobDivaRateLimited, JobDivaAuthError, JobDivaNotConfigured)
