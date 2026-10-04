/** Backend base path (proxied to FastAPI by Vite in dev). */
export const API_BASE = '/api'

/** TanStack Query defaults. */
export const QUERY_STALE_TIME_MS = 30_000
export const HEALTH_STALE_TIME_MS = 60_000

/** Max length of the recruiter query / notes (matches the backend's request limit). */
export const MAX_TEXT_CHARS = 4000
