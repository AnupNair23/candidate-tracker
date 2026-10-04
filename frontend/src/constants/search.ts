/** Pipeline stages shown while a search runs; `stage` names match the backend's stage events. */
export const STEPS: { stage: string; label: string }[] = [
  { stage: 'job', label: 'Loading the job from JobDiva' },
  { stage: 'retrieve', label: 'Searching JobDiva' },
  { stage: 'prescreen', label: 'Pre-screening candidates' },
  { stage: 'hydrate', label: 'Loading candidate history' },
  { stage: 'assess', label: 'Reviewing profiles with Claude' },
  { stage: 'validate', label: 'Validating evidence and ranking' },
]

/** Shortlist rows shown before "Show N more". */
export const RESULTS_INITIAL = 8
/** Gap chips shown per shortlist row, and skills named in the Skills filter label. */
export const MAX_GAP_CHIPS = 3
export const SKILLS_LABEL_PREVIEW = 3
/** Characters of a recent search shown on its chip. */
export const RECENT_LABEL_CHARS = 48
/** Radius given to a location filter the recruiter creates from scratch. */
export const DEFAULT_RADIUS_MI = 50
/** Countdown used for a 429 that carries no Retry-After. */
export const DEFAULT_RETRY_AFTER_S = 10
