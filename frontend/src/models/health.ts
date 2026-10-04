import { z } from 'zod'
import { str } from './primitives'

export const HealthSchema = z.object({
  ok: z.boolean(),
  jobdiva_configured: z.boolean(),
  jobdiva_mock: z.boolean(),
  llm_mode: z.string(),
  claude_configured: z.boolean(),
  claude_model: str,
  snapshot_replay: z.boolean(),
  jobdiva_use_bi: z.boolean(),
})
export type Health = z.infer<typeof HealthSchema>
