import type { z } from 'zod'
import { API_BASE } from '../constants/api'
import {
  CandidateInteractionsSchema,
  CandidateProfileSchema,
  CandidateResumeSchema,
  HealthSchema,
  IntentResponseSchema,
  JobSchema,
  JobsPageSchema,
  LinkedCandidatesSchema,
} from '../models'
import { ApiError, errorFromResponse } from './errors'

async function request<S extends z.ZodType>(
  schema: S,
  url: string,
  init?: RequestInit,
): Promise<z.infer<S>> {
  let res: Response
  try {
    res = await fetch(url, init)
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err
    throw new ApiError('Could not reach the sourcing service', { code: 'network_error', status: 0 })
  }
  if (!res.ok) throw await errorFromResponse(res)
  const json = await res.json()
  const parsed = schema.safeParse(json)
  if (!parsed.success) {
    throw new ApiError('The server returned data in an unexpected shape', { code: 'invalid_response', status: res.status })
  }
  return parsed.data
}

const post = (body: unknown, signal?: AbortSignal): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
  signal,
})

export const api = {
  health: () => request(HealthSchema, `${API_BASE}/health`),
  jobs: (page: number, pageSize: number, signal?: AbortSignal) =>
    request(JobsPageSchema, `${API_BASE}/jobs?page=${page}&page_size=${pageSize}`, { signal }),
  job: (jobId: string, signal?: AbortSignal) =>
    request(JobSchema, `${API_BASE}/jobs/${encodeURIComponent(jobId)}`, { signal }),
  linkedCandidates: (jobId: string, signal?: AbortSignal) =>
    request(LinkedCandidatesSchema, `${API_BASE}/jobs/${encodeURIComponent(jobId)}/candidates`, { signal }),
  intent: (jobId: string, query: string, notes: string, signal?: AbortSignal) =>
    request(IntentResponseSchema, `${API_BASE}/jobs/${encodeURIComponent(jobId)}/intent`, post({ query, notes }, signal)),
  candidate: (candidateId: string, nameHint?: string, signal?: AbortSignal) =>
    request(
      CandidateProfileSchema,
      `${API_BASE}/candidates/${encodeURIComponent(candidateId)}${nameHint ? `?name=${encodeURIComponent(nameHint)}` : ''}`,
      { signal },
    ),
  interactions: (candidateId: string, signal?: AbortSignal) =>
    request(CandidateInteractionsSchema, `${API_BASE}/candidates/${encodeURIComponent(candidateId)}/interactions`, { signal }),
  resume: (candidateId: string, signal?: AbortSignal) =>
    request(CandidateResumeSchema, `${API_BASE}/candidates/${encodeURIComponent(candidateId)}/resume`, { signal }),
}
