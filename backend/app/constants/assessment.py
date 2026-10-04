"""Evidence packets and validation: text-size limits and verification rules for Claude's assessments."""

# ------------------------------------------------------------------ packets
RESUME_PARAGRAPH_CHARS = 700  # a resume paragraph is split once it grows past this many characters
# Search-document excerpts (used when there is no resume) get resume_char_cap // this.
SEARCH_EXCERPT_CAP_DIVISOR = 2
INTERACTION_EVIDENCE_CHARS = 1200  # interaction content kept per evidence item
YEARS_REQUIREMENT_ID = "ry"  # id of the synthetic minimum-years requirement

# ------------------------------------------------------------------ validation
# Requirement kinds whose met / partial verdicts must cite text that mentions the requirement.
TEXT_CHECKED_KINDS = {"skill", "keyword", "title"}
CONTRIBUTION_SUMMARY_CHARS = 240
REASON_CHARS = 320
CONCERN_CHARS = 160
MAX_CONCERNS = 4

# ------------------------------------------------------------------ results
EVIDENCE_QUOTE_CHARS = 300  # evidence quote length shown in the UI
