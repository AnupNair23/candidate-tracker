import type { ApiError } from '../api/errors'
import type { SearchIntent } from './intent'
import type { SearchBody, SearchResult } from './search'

export type SearchRun = {
  jobId: string
  token: number
  status: 'running' | 'done' | 'error'
  stage: string
  stagesSeen: string[]
  message: string
  progress: { done?: number; total?: number } | null
  /** Last successful result for this job — kept visible when a later run fails. */
  result: SearchResult | null
  error: ApiError | null
  request: SearchBody
  startedAt: number
}

/** Recent searches per job: query + notes + confirmed filters only — never candidate data. */
export type SavedSearch = { query: string; notes: string; intent: SearchIntent; ts: number }
