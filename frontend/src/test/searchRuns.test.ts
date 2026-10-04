import { ApiError } from '../api/errors'
import type { SearchResult } from '../models'
import { SearchRunStore } from '../state/searchRunStore'
import { deferred, intent, result } from './fixtures'

type Runner = ConstructorParameters<typeof SearchRunStore>[0]

function controllableRunner() {
  const pending = new Map<string, ReturnType<typeof deferred<SearchResult>>[]>()
  const runner: Runner = (jobId, _body, { signal }) => {
    const d = deferred<SearchResult>()
    signal.addEventListener('abort', () => d.reject(Object.assign(new Error('aborted'), { name: 'AbortError' })))
    pending.set(jobId, [...(pending.get(jobId) ?? []), d])
    return d.promise
  }
  return { runner, pending }
}

const body = { intent, query: 'q', notes: '' }

describe('SearchRunStore', () => {
  it('keeps each shortlist attached to its own job, whatever order results arrive in', async () => {
    const { runner, pending } = controllableRunner()
    const store = new SearchRunStore(runner)
    const a = store.start('A', body) // slow
    const b = store.start('B', body) // fast
    pending.get('B')![0].resolve(result('B', 'sb', ['Bea']))
    await b
    pending.get('A')![0].resolve(result('A', 'sa', ['Al']))
    await a
    expect(store.get('A')!.result!.shortlist[0].name).toBe('Al')
    expect(store.get('B')!.result!.shortlist[0].name).toBe('Bea')
  })

  it('drops a superseded run on the same job', async () => {
    const { runner, pending } = controllableRunner()
    const store = new SearchRunStore(runner)
    const first = store.start('A', body)
    const second = store.start('A', body) // aborts the first
    pending.get('A')![1].resolve(result('A', 's2', ['Second']))
    await Promise.all([first, second])
    expect(store.get('A')!.status).toBe('done')
    expect(store.get('A')!.result!.search_id).toBe('s2')
  })

  it('rejects a result that belongs to a different job', async () => {
    const { runner, pending } = controllableRunner()
    const store = new SearchRunStore(runner)
    const run = store.start('A', body)
    pending.get('A')![0].resolve(result('B'))
    await run
    expect(store.get('A')!.status).toBe('error')
    expect(store.get('A')!.result).toBeNull()
  })

  it('keeps the previous shortlist visible when a retry fails with a rate limit', async () => {
    const { runner, pending } = controllableRunner()
    const store = new SearchRunStore(runner)
    const ok = store.start('A', body)
    pending.get('A')![0].resolve(result('A', 's1', ['Kept']))
    await ok
    const retry = store.retry('A')!
    pending.get('A')![1].reject(new ApiError('slow down', { code: 'rate_limited', status: 429, retryAfter: 5 }))
    await retry
    const run = store.get('A')!
    expect(run.status).toBe('error')
    expect(run.error!.isRateLimited).toBe(true)
    expect(run.result!.shortlist[0].name).toBe('Kept')
  })
})
