import type { SearchIntent, SearchResult } from '../models'

export const intent: SearchIntent = {
  summary: 'Mechanical design engineer',
  titles: [{ title: 'Mechanical Design Engineer', synonyms: [], source: 'job' }],
  location: null,
  years: null,
  requirements: [{ id: 'r1', text: 'CATIA V5', kind: 'skill', must_have: true, aliases: [], source: 'query' }],
  keywords: [],
  exclusions: [],
  preferences_from_notes: [],
  ambiguities: [],
}

export function result(jobId: string, searchId = `s-${jobId}`, names: string[] = ['Ada Lovelace']): SearchResult {
  return {
    job_id: jobId,
    search_id: searchId,
    generated_at: '2026-10-04T00:00:00Z',
    intent,
    shortlist: names.map((name, i) => ({
      rank: i + 1,
      candidate_id: `${jobId}-c${i}`,
      name,
      title: 'Engineer',
      employer: null,
      city: 'Huntsville',
      state: 'AL',
      distance_mi: 5,
      years_experience: 6,
      fit_score: 80,
      stars: 4,
      tier: 'strong',
      reason: 'Daily CATIA V5 use.',
      matched: [],
      gaps: [],
      contributions: [],
      concerns: [],
      injection_suspected: false,
      job_linked: false,
      job_link_status: null,
      placed_by_us_year: null,
      sources_unavailable: [],
      assessed_by: 'claude-opus-5-5',
    })),
    funnel: {
      queries: [],
      pool: names.length,
      linked: 0,
      excluded_by_filter: {},
      prescreened_out: 0,
      reviewed: names.length,
      assessed: names.length,
      not_assessed: 0,
      not_assessed_reasons: {},
      not_a_fit: 0,
      failing_requirements: [],
      insufficient_evidence: 0,
      shortlisted: names.length,
      retrieval_partial: false,
    },
    shortfall: null,
    partial: false,
    warnings: [],
    assessed_by: 'claude-opus-5-5',
    replayed: false,
  }
}

export function sseBody(frames: { event: string; data: unknown }[], { close = true } = {}): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const f of frames) controller.enqueue(encoder.encode(`event: ${f.event}\ndata: ${JSON.stringify(f.data)}\n\n`))
      if (close) controller.close()
    },
  })
}

export function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}
