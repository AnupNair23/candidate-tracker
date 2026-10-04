"""Search-intent limits: normalization caps applied to Claude's (or the recruiter's) intent, and the stub parser."""

MAX_TITLES = 4
MAX_SYNONYMS = 6  # per title
MAX_ALIASES = 6  # per requirement
MAX_REQUIREMENTS = 15
MAX_RADIUS_MI = 500
MAX_LIST_ITEMS = 10  # keywords, exclusions, preferences_from_notes, ambiguities
SUMMARY_CHARS = 300
JOB_DESCRIPTION_CHARS = 12000  # job description text sent to Claude

# LLM_MODE=stub parser
STUB_REQUIREMENT_CHARS = 60
STUB_MAX_REQUIREMENTS = 8
