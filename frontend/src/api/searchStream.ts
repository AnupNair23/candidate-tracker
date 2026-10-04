import { API_BASE } from '../constants/api'
import { ApiErrorSchema, SearchResultSchema, type SearchBody, type SearchResult, type StreamEvent } from '../models'
import { ApiError, errorFromResponse } from './errors'

type Handlers = {
  onEvent: (event: StreamEvent) => void
  signal: AbortSignal
}

/** Parse `text/event-stream` frames from a fetch body (EventSource cannot POST). */
export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<{ event: string; data: string }> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
    let sep: number
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      let event = 'message'
      const data: string[] = []
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
      }
      if (data.length) yield { event, data: data.join('\n') }
    }
  }
}

/**
 * Run a search for `jobId`. Resolves with the validated result, or throws ApiError.
 * Events whose job_id / search_id don't match this run are ignored.
 * A stream that ends without a `result` event is an error (no auto-reconnect: it would re-run the search).
 */
export async function runSearch(jobId: string, body: SearchBody, { onEvent, signal }: Handlers): Promise<SearchResult> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/jobs/${encodeURIComponent(jobId)}/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(body),
      signal,
    })
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err
    throw new ApiError('Could not reach the sourcing service', { code: 'network_error', status: 0 })
  }
  if (!res.ok) throw await errorFromResponse(res)
  if (!res.body) throw new ApiError('Search stream was empty', { code: 'stream_error', status: res.status })

  let searchId: string | null = null
  for await (const { event, data } of readSse(res.body)) {
    let payload: Record<string, unknown>
    try {
      payload = JSON.parse(data)
    } catch {
      continue
    }
    if (payload.job_id !== jobId) continue // never attach events to the wrong job
    if (typeof payload.search_id === 'string') {
      if (searchId === null) searchId = payload.search_id
      else if (payload.search_id !== searchId) continue
    }
    if (event === 'result') {
      const parsed = SearchResultSchema.safeParse(payload)
      if (!parsed.success) {
        throw new ApiError('The search result failed validation in the browser', { code: 'invalid_response', status: 200 })
      }
      return parsed.data
    }
    if (event === 'error') {
      const err = ApiErrorSchema.safeParse(payload)
      throw new ApiError(err.success ? err.data.message : 'Search failed', {
        code: err.success ? err.data.code : 'search_failed',
        status: err.success && err.data.code === 'rate_limited' ? 429 : 502,
        source: err.success ? err.data.source : 'server',
        retryAfter: err.success ? (err.data.retry_after ?? null) : null,
      })
    }
    if (event === 'heartbeat') onEvent({ type: 'heartbeat' })
    else if (event === 'stage')
      onEvent({ type: 'stage', stage: String(payload.stage ?? ''), message: String(payload.message ?? '') })
    else if (event === 'progress')
      onEvent({
        type: 'progress',
        stage: String(payload.stage ?? ''),
        message: typeof payload.message === 'string' ? payload.message : undefined,
        done: typeof payload.done === 'number' ? payload.done : undefined,
        total: typeof payload.total === 'number' ? payload.total : undefined,
      })
  }
  throw new ApiError('The search stream ended before a result arrived', { code: 'stream_incomplete', status: 0 })
}
