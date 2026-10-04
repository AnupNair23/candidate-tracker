import { z } from 'zod'
import { optNum, optStr, str } from './primitives'

export const JobSummarySchema = z.object({
  job_id: str,
  ref: optStr,
  title: str,
  company: optStr,
  city: optStr,
  state: optStr,
  zipcode: optStr,
  status: optStr,
  job_type: optStr,
  onsite_remote: optStr,
  rate_min: optNum,
  rate_max: optNum,
  issue_date: optStr,
})
export type JobSummary = z.infer<typeof JobSummarySchema>

export const JobsPageSchema = z.object({
  items: z.array(JobSummarySchema),
  page: z.number(),
  page_size: z.number(),
  has_next: z.boolean(),
})
export type JobsPage = z.infer<typeof JobsPageSchema>

export const JobSchema = JobSummarySchema.extend({
  description_html: optStr,
  description_text: optStr,
})
export type Job = z.infer<typeof JobSchema>
