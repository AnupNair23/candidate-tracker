import { z } from 'zod'
import { optNum, optStr, str } from './primitives'
import { RequirementSchema, SearchIntentSchema, type SearchIntent } from './intent'

const EvidenceSourceSchema = z.enum([
  'profile',
  'resume',
  'notes',
  'recorded_conversations',
  'submissions',
  'interviews',
  'placements',
  'client_feedback',
])
export type EvidenceSource = z.infer<typeof EvidenceSourceSchema>

export const EvidenceRefSchema = z.object({
  id: str,
  source: EvidenceSourceSchema,
  label: str,
  quote: str,
  date: optStr,
})
export type EvidenceRef = z.infer<typeof EvidenceRefSchema>

export const SkillMatchSchema = z.object({
  requirement_id: str,
  label: str,
  kind: RequirementSchema.shape.kind,
  must_have: z.boolean(),
  status: z.enum(['met', 'partial', 'not_met', 'unknown', 'unverified']),
  evidence: z.array(EvidenceRefSchema),
})
export type SkillMatch = z.infer<typeof SkillMatchSchema>

export const ContributionSchema = z.object({
  source: EvidenceSourceSchema,
  effect: z.enum(['positive', 'negative', 'neutral']),
  summary: str,
  evidence: z.array(EvidenceRefSchema),
})
export type Contribution = z.infer<typeof ContributionSchema>

export const ShortlistEntrySchema = z.object({
  rank: z.number(),
  candidate_id: str,
  name: str,
  title: optStr,
  employer: optStr,
  city: optStr,
  state: optStr,
  distance_mi: optNum,
  years_experience: optNum,
  fit_score: z.number(),
  stars: z.number(),
  tier: z.enum(['strong', 'good', 'possible']),
  reason: str,
  matched: z.array(SkillMatchSchema),
  gaps: z.array(SkillMatchSchema),
  contributions: z.array(ContributionSchema),
  concerns: z.array(str),
  injection_suspected: z.boolean(),
  job_linked: z.boolean(),
  job_link_status: optStr,
  placed_by_us_year: optNum,
  sources_unavailable: z.array(str),
  assessed_by: str,
})
export type ShortlistEntry = z.infer<typeof ShortlistEntrySchema>

export const FunnelSchema = z.object({
  queries: z.array(
    z.object({
      label: str,
      criteria: str,
      found: optNum,
      returned: z.number(),
      new: z.number(),
      error: optStr,
    }),
  ),
  pool: z.number(),
  linked: z.number(),
  excluded_by_filter: z.record(z.string(), z.number()),
  prescreened_out: z.number(),
  reviewed: z.number(),
  assessed: z.number(),
  not_assessed: z.number(),
  not_assessed_reasons: z.record(z.string(), z.number()),
  not_a_fit: z.number(),
  failing_requirements: z.array(
    z.object({ requirement_id: str, label: str, count: z.number(), sole_blocker: z.number() }),
  ),
  insufficient_evidence: z.number(),
  shortlisted: z.number(),
  retrieval_partial: z.boolean(),
})
export type Funnel = z.infer<typeof FunnelSchema>

export const SearchResultSchema = z.object({
  job_id: str,
  search_id: str,
  generated_at: str,
  intent: SearchIntentSchema,
  shortlist: z.array(ShortlistEntrySchema),
  funnel: FunnelSchema,
  shortfall: z.object({ headline: str, reasons: z.array(str), suggestions: z.array(str) }).nullable(),
  partial: z.boolean(),
  warnings: z.array(str),
  assessed_by: str,
  replayed: z.boolean(),
})
export type SearchResult = z.infer<typeof SearchResultSchema>

/** Body of POST /api/jobs/{id}/search. */
export type SearchBody = { intent: SearchIntent; query: string; notes: string }

/** Progress events parsed from the search stream. */
export type StreamEvent =
  | { type: 'stage'; stage: string; message: string }
  | { type: 'progress'; stage: string; message?: string; done?: number; total?: number }
  | { type: 'heartbeat' }
