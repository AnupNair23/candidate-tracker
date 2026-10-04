import { ApiError } from '../api/errors'
import { runSearch } from '../api/searchStream'
import { intent, result, sseBody } from './fixtures'

const body = { intent, query: '', notes: '' }

function mockFetch(stream: ReadableStream<Uint8Array>) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })))
}

afterEach(() => vi.unstubAllGlobals())

describe('runSearch', () => {
  it('ignores events for another job or search and returns the validated result', async () => {
    const events: string[] = []
    mockFetch(
      sseBody([
        { event: 'stage', data: { stage: 'retrieve', message: 'm', job_id: 'J1', search_id: 's1' } },
        { event: 'stage', data: { stage: 'assess', message: 'foreign', job_id: 'J2', search_id: 's9' } },
        { event: 'result', data: result('J2', 's9') },
        { event: 'result', data: result('J1', 's1') },
      ]),
    )
    const res = await runSearch('J1', body, {
      onEvent: (e) => e.type === 'stage' && events.push(e.message),
      signal: new AbortController().signal,
    })
    expect(res.job_id).toBe('J1')
    expect(events).toEqual(['m'])
  })

  it('treats a stream that ends without a result as an error', async () => {
    mockFetch(sseBody([{ event: 'stage', data: { stage: 'retrieve', message: 'm', job_id: 'J1', search_id: 's1' } }]))
    await expect(runSearch('J1', body, { onEvent: () => {}, signal: new AbortController().signal })).rejects.toMatchObject({
      code: 'stream_incomplete',
    })
  })

  it('surfaces a rate_limited error event with retry-after', async () => {
    mockFetch(
      sseBody([
        { event: 'error', data: { code: 'rate_limited', message: 'JobDiva is rate-limiting requests', source: 'jobdiva', retry_after: 12, job_id: 'J1', search_id: 's1' } },
      ]),
    )
    const err = await runSearch('J1', body, { onEvent: () => {}, signal: new AbortController().signal }).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).isRateLimited).toBe(true)
    expect((err as ApiError).retryAfter).toBe(12)
  })
})
