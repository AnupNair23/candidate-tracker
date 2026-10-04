import { z } from 'zod'
import { str } from './primitives'

export const ApiErrorSchema = z.object({
  code: str,
  message: str,
  source: str,
  retry_after: z.number().nullable().optional(),
})
export type ApiErrorPayload = z.infer<typeof ApiErrorSchema>
