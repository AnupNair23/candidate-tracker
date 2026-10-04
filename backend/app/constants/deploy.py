"""Deployment: basic-auth realm, the unauthenticated health-check path and SPA fallback rules."""

BASIC_AUTH_REALM = "Candidate Tracker"
HEALTHZ_PATH = "/healthz"  # Render's health check; the only path served without credentials
SPA_INDEX = "index.html"
