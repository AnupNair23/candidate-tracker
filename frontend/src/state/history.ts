import { MAX_SAVED_SEARCHES, SEARCH_HISTORY_KEY_PREFIX } from '../constants/storage'
import type { SavedSearch } from '../models'

/** Recent searches per job: query + notes + confirmed filters only — never candidate data. */
const key = (jobId: string) => `${SEARCH_HISTORY_KEY_PREFIX}${jobId}`

export function loadSearches(jobId: string): SavedSearch[] {
  try {
    const raw = window.localStorage.getItem(key(jobId))
    const parsed = raw ? (JSON.parse(raw) as SavedSearch[]) : []
    return Array.isArray(parsed) ? parsed.filter((s) => s && typeof s.query === 'string' && s.intent) : []
  } catch {
    return []
  }
}

export function saveSearch(jobId: string, entry: SavedSearch): void {
  try {
    const existing = loadSearches(jobId).filter((s) => !(s.query === entry.query && s.notes === entry.notes))
    window.localStorage.setItem(key(jobId), JSON.stringify([entry, ...existing].slice(0, MAX_SAVED_SEARCHES)))
  } catch {
    /* storage unavailable — history is a convenience only */
  }
}
