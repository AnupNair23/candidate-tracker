"""HTTP API: route prefix, CORS methods and request limits."""

API_PREFIX = "/api"
CORS_ALLOW_METHODS = ["GET", "POST"]

# Jobs list page size (UI pages are mapped onto JobDiva pages of JOBDIVA_PAGE_SIZE).
JOBS_PAGE_SIZE_DEFAULT = 30
JOBS_PAGE_SIZE_MIN = 10
JOBS_PAGE_SIZE_MAX = 50

REQUEST_TEXT_MAX_CHARS = 4000  # recruiter query / notes
NAME_HINT_MAX_CHARS = 200
