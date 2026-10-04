import { z } from 'zod'
import { str } from './primitives'

const SourceSchema = z.enum(['query', 'job', 'notes'])
export const RequirementSchema = z.object({
  id: str,
  text: str,
  kind: z.enum(['skill', 'title', 'keyword', 'authorization', 'other']),
  must_have: z.boolean(),
  aliases: z.array(str),
  source: SourceSchema,
})
export type Requirement = z.infer<typeof RequirementSchema>

export const SearchIntentSchema = z.object({
  summary: str,
  titles: z.array(z.object({ title: str, synonyms: z.array(str), source: SourceSchema })),
  location: z
    .object({
      city: z.string().nullable(),
      state: z.string().nullable(),
      zipcode: z.string().nullable(),
      radius_mi: z.number().nullable(),
      remote_ok: z.boolean().nullable(),
      required: z.boolean(),
      source: SourceSchema,
    })
    .nullable(),
  years: z
    .object({
      min: z.number().nullable(),
      max: z.number().nullable(),
      required: z.boolean(),
      source: SourceSchema,
    })
    .nullable(),
  requirements: z.array(RequirementSchema),
  keywords: z.array(str),
  exclusions: z.array(str),
  preferences_from_notes: z.array(str),
  ambiguities: z.array(str),
})
export type SearchIntent = z.infer<typeof SearchIntentSchema>

export const IntentResponseSchema = z.object({ job_id: str, intent: SearchIntentSchema })
