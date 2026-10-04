"""Claude call parameters and the stub assessor's labels."""

FALLBACK_BETA = "server-side-fallback-2026-07-01"  # beta header for server-side refusal fallback
DEFAULT_MAX_TOKENS = 16000
INTENT_MAX_TOKENS = 8000
ASSESS_MAX_TOKENS = 16000
UNAVAILABLE_STATUS_CODES = (529, 503, 500, 502, 504)  # HTTP statuses reported as "Claude is unavailable"

# LLM_MODE=stub
STUB_MODEL = "stub (keyword matcher — not Claude)"
STUB_VERDICT_EVIDENCE = 2  # evidence ids cited per stub verdict
STUB_CONTRIBUTION_EVIDENCE = 3  # evidence ids cited per stub source contribution
