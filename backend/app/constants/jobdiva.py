"""JobDiva API v1: endpoint paths, request parameters, error heuristics and payload-mapping hints."""

# ------------------------------------------------------------------ endpoints
# Standard v1 endpoints (/api/jobdiva/...). Parameter casing is exactly as in the v1 spec.
AUTHENTICATE_PATH = "/api/authenticate"
SEARCH_JOB_PATH = "/api/jobdiva/SearchJob"
SEARCH_SUBMITTAL_PATH = "/api/jobdiva/searchSubmittal"
SEARCH_START_PATH = "/api/jobdiva/searchStart"
QUICK_CANDIDATE_SEARCH_PATH = "/api/jobdiva/us/quickCandidateProfileSearch"
SEARCH_CANDIDATE_PROFILE_PATH = "/api/jobdiva/searchCandidateProfile"

# The single approved v2 endpoint: v1 has no skill/title candidate search (v1 universal search matches names only).
# Body fields: skills[] (ANDed), titleSearch, states[] (2-letter), resumeCount (caps the result; no paging).
TALENT_SEARCH_PATH = "/apiv2/jobdiva/TalentSearch"

# Optional BI endpoints (/api/bi/...) — only called when JOBDIVA_USE_BI=true.
BI_CANDIDATE_NOTES_PATH = "/api/bi/CandidateNotesListDetail"
BI_CANDIDATES_RESUMES_PATH = "/api/bi/CandidatesResumesDetail"
BI_RESUME_DETAIL_PATH = "/api/bi/ResumeDetail"
BI_CANDIDATE_EXPERIENCE_PATH = "/api/bi/CandidateExperienceDetail"

# ----------------------------------------------------------- request parameters
BATCH_SIZE = 50  # candidate ids per batched BI call
OPEN_JOB_STATUS = 0  # SearchJob `status` value for open jobs
# searchSubmittal needs a candidate parameter AND a job parameter (verified live). "%" is not a wildcard, but a
# last-name prefix like "a%" is, so a job's submittals are listed by sweeping last-name prefixes a–z.
SUBMITTAL_LASTNAME_PREFIXES = tuple("abcdefghijklmnopqrstuvwxyz")
LINKED_CACHE_TTL_S = 120.0  # job submittal sweeps are cached briefly (Candidates tab + search share them)
DEFAULT_MAX_RETURNED = 30  # default page size of the candidate search / starts helpers
QUICK_SEARCH_MAX_RETURNED = 10  # default page size of quickCandidateProfileSearch

# ----------------------------------------------------------- error heuristics
# Response-body fragments that mean the bearer token was rejected (JobDiva does not always use 401/403).
AUTH_FAILURE_MARKERS = ("full authentication is required", "invalid token", "token expired", "jwt expired")
AUTH_FAILURE_SCAN_CHARS = 500  # how much of an error body is scanned for the markers above
# /api/authenticate body fragments that mean the credentials themselves were rejected.
CREDENTIALS_REJECTED_MARKERS = ("invalid username", "password")
# JobDiva reports bad/missing parameters as HTTP 500 with a message starting with one of these.
VALIDATION_ERROR_PREFIXES = ("error:", "please specify", "invalid")
ERROR_MESSAGE_CHARS = 300  # error-message length kept from a JobDiva error body
BACKOFF_JITTER_S = 0.5  # upper bound of the random jitter added to exponential backoff

# ------------------------------------------------------------ payload mapping
# Interaction notes whose action type contains one of these hints are classified accordingly.
CONVERSATION_HINTS = (
    "call",
    "phone",
    "spoke",
    "conversation",
    "voicemail",
    "left message",
    "screen",
    "meeting",
    "text",
)
CLIENT_FEEDBACK_HINTS = ("client", "feedback", "hiring manager", "customer")
# Search-document string fields longer than this are kept as candidate search text.
SEARCH_TEXT_MIN_CHARS = 40
