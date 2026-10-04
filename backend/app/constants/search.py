"""Search pipeline: stage names, stream settings, retrieval limits and funnel labels."""

# ------------------------------------------------------------------ stages
# Stage names sent in `stage` / `progress` events. The frontend's search-progress steps use the same names.
STAGE_START = "start"
STAGE_JOB = "job"
STAGE_RETRIEVE = "retrieve"
STAGE_PRESCREEN = "prescreen"
STAGE_HYDRATE = "hydrate"
STAGE_ASSESS = "assess"
STAGE_VALIDATE = "validate"

# ------------------------------------------------------------- search stream (SSE)
HEARTBEAT_S = 15.0  # idle interval after which a heartbeat event is sent
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Content-Encoding": "identity"}

# ------------------------------------------------------------------ retrieval
# Funnel query labels that the shortfall explanation and the keyword-search warning single out.
LINKED_QUERY_LABEL = "Already linked to this job"
LOCATION_QUERY_LABEL = "Profiles in job location"
# Status shown for a job-linked candidate when JobDiva gives none.
LINKED_SUBMITTAL_STATUS = "Submitted"
LINKED_START_STATUS = "Started"

LINKED_STARTS_PAGES = 2  # searchStart pages fetched for candidates already linked to the job
LOCATION_SEARCH_PAGES = 2  # searchCandidateProfile pages fetched by the location search
# The location search runs only while the pool is below pool_target // LOCATION_SEARCH_TARGET_DIVISOR.
LOCATION_SEARCH_TARGET_DIVISOR = 2

# Keyword query building (strict → broad).
MAX_QUERY_TITLES = 6  # distinct titles + synonyms used in queries
MAX_QUERY_MUST_SKILLS = 4  # must-have skills ANDed together
MAX_QUERY_ANY_SKILLS = 6  # key skills ORed in "Title + any key skill"
MAX_PLAIN_TITLE_QUERY_SKILLS = 3  # must-have skills in the non-boolean "Title + must-have skills" query
MAX_SINGLE_SKILL_QUERIES = 3  # one broad query per key skill, for the first N key skills
MAX_QUERY_KEYWORDS = 5  # keywords used when no other query could be built

# ------------------------------------------------------------------ hydration
MAX_INTERACTIONS = 25  # newest interactions kept per candidate (same-client ones beyond this are also kept)
HYDRATE_PROGRESS_EVERY = 5  # emit a hydrate progress event every N candidates
# searchStart rows are numbered from this offset so their synthetic interaction ids never collide with
# searchSubmittal rows.
START_ROW_INDEX_OFFSET = 1000

# ------------------------------------------------------------------ funnel
NOT_ASSESSED_LABELS = {
    "deadline": "the search time limit was reached",
    "model_error": "the model request failed",
    "model_declined": "the model declined",
    "invalid_model_output": "the model output failed validation twice",
    "missing_from_model_output": "the model skipped them twice",
    "model_output_too_long": "the model output was too long",
}
