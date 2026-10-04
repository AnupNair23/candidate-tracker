import { z } from 'zod'
import { optNum, optStr, str } from './primitives'

export const InteractionSchema = z.object({
  interaction_id: str,
  type: z.enum(['notes', 'recorded_conversations', 'submissions', 'interviews', 'placements', 'client_feedback']),
  date: optStr,
  author: optStr,
  client: optStr,
  job_id: optStr,
  job_title: optStr,
  status: optStr,
  content: str,
})
export type Interaction = z.infer<typeof InteractionSchema>

export const WorkHistorySchema = z.object({
  title: optStr,
  company: optStr,
  location: optStr,
  start: optStr,
  end: optStr,
  description: optStr,
})

export const CandidateProfileSchema = z.object({
  candidate_id: str,
  name: str,
  title: optStr,
  employer: optStr,
  city: optStr,
  state: optStr,
  zipcode: optStr,
  email: optStr,
  phone: optStr,
  years_experience: optNum,
  available: z.boolean().nullable().optional(),
  updated_on: optStr,
  skills: z.array(z.object({ name: str, value: str })),
  work_history: z.array(WorkHistorySchema),
  work_history_state: z.enum(['ok', 'none', 'unavailable']),
})
export type CandidateProfile = z.infer<typeof CandidateProfileSchema>

const SourceState = z.enum(['ok', 'none', 'unavailable'])
export const CandidateInteractionsSchema = z.object({
  candidate_id: str,
  notes: z.array(InteractionSchema),
  history: z.array(InteractionSchema),
  sources: z.object({ notes: SourceState, history: SourceState }),
})
export type CandidateInteractions = z.infer<typeof CandidateInteractionsSchema>

export const CandidateResumeSchema = z.object({ candidate_id: str, text: z.string().nullable(), available: z.boolean() })

export const LinkedCandidatesSchema = z.object({
  job_id: str,
  warnings: z.array(str).default([]),
  items: z.array(
    z.object({
      candidate_id: str,
      name: str,
      title: optStr,
      city: optStr,
      state: optStr,
      status: optStr,
      date: optStr,
      source: str,
    }),
  ),
})
export type LinkedCandidate = z.infer<typeof LinkedCandidatesSchema>['items'][number]
