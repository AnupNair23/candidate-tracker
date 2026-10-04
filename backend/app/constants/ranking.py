"""Ranking parameters: pre-score weights and rules, fit-score weights, and star / tier thresholds.

README "Ranking parameters" documents these values; keep the two in sync.
"""

# ------------------------------------------------------------------ pre-score
# Weights of the pre-score signals (they sum to 1.0).
W_SKILLS, W_TITLE, W_LOCATION, W_YEARS, W_RECENCY = 0.45, 0.20, 0.15, 0.10, 0.10
UNKNOWN_SIGNAL = 0.5  # value of an unknown signal: neutral, never a penalty
PRESCORE_TERM_KINDS = ("skill", "keyword", "title")  # requirement kinds matched against the candidate's text

# Requirement weights, shared by the pre-score skill coverage and the fit score.
MUST_HAVE_WEIGHT = 2.0
NICE_TO_HAVE_WEIGHT = 1.0

# Location: full fit within the radius, falling linearly to 0 at radius + LOCATION_FALLOFF_RADII × radius.
DEFAULT_RADIUS_MI = 50
LOCATION_FALLOFF_RADII = 2
SAME_STATE_LOCATION_FIT = 0.7  # no known distance, same state
OTHER_STATE_LOCATION_FIT = 0.2  # no known distance, different state

# Years: in range = 1, below the minimum = 1 - gap/min, above the maximum = this.
ABOVE_MAX_YEARS_FIT = 0.8

# Recency of the profile's last update.
RECENT_PROFILE_DAYS = 365
RECENT_PROFILE_FIT = 1.0
AGING_PROFILE_DAYS = 3 * 365
AGING_PROFILE_FIT = 0.6
STALE_PROFILE_FIT = 0.3

# ------------------------------------------------------------------ fit score
STATUS_SCORE = {"met": 1.0, "partial": 0.5}  # unknown, unverified and not_met score 0
NO_REQUIREMENTS_FIT = 0.5  # fit when there are no requirements to score
# Each positive / negative validated interaction contribution moves the fit by this much, capped in total.
INTERACTION_ADJUSTMENT = 0.03
INTERACTION_ADJUSTMENT_CAP = 0.06

# Minimum fit score (0-100) for each star count; anything lower gets 1 star.
STAR_THRESHOLDS = {5: 85, 4: 70, 3: 55, 2: 35}
# Minimum fit score (0-100) for each tier; anything lower is "possible".
TIER_THRESHOLDS = {"strong": 75, "good": 55}
