import { ApiError } from '../api/errors'
import { runSearch } from '../api/searchStream'
import type { SearchBody, SearchRun, StreamEvent } from '../models'

type Runner = typeof runSearch

/**
 * Shortlists keyed by jobId. Switching jobs never aborts a run — its result lands in its own slot.
 * A new search on the same job supersedes (aborts) the previous one; late events from a superseded
 * run are dropped by token comparison.
 */
export class SearchRunStore {
  private runs = new Map<string, SearchRun>()
  private controllers = new Map<string, AbortController>()
  private listeners = new Set<() => void>()
  private nextToken = 1
  private readonly runner: Runner

  constructor(runner: Runner = runSearch) {
    this.runner = runner
  }

  subscribe = (listener: () => void) => {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  get = (jobId: string): SearchRun | undefined => this.runs.get(jobId)

  private set(jobId: string, run: SearchRun) {
    this.runs.set(jobId, run)
    this.listeners.forEach((l) => l())
  }

  private update(jobId: string, token: number, patch: Partial<SearchRun>) {
    const current = this.runs.get(jobId)
    if (!current || current.token !== token) return // superseded run — drop
    this.set(jobId, { ...current, ...patch })
  }

  start(jobId: string, request: SearchBody): Promise<void> {
    this.controllers.get(jobId)?.abort()
    const controller = new AbortController()
    this.controllers.set(jobId, controller)
    const token = this.nextToken++
    const previous = this.runs.get(jobId)
    this.set(jobId, {
      jobId,
      token,
      status: 'running',
      stage: 'start',
      stagesSeen: ['start'],
      message: 'Starting search',
      progress: null,
      result: previous?.result ?? null,
      error: null,
      request,
      startedAt: Date.now(),
    })

    const onEvent = (event: StreamEvent) => {
      const current = this.runs.get(jobId)
      if (!current || current.token !== token) return
      if (event.type === 'stage') {
        this.update(jobId, token, {
          stage: event.stage,
          message: event.message,
          progress: null,
          stagesSeen: current.stagesSeen.includes(event.stage) ? current.stagesSeen : [...current.stagesSeen, event.stage],
        })
      } else if (event.type === 'progress') {
        this.update(jobId, token, {
          message: event.message ?? current.message,
          progress: event.done !== undefined ? { done: event.done, total: event.total } : current.progress,
        })
      }
    }

    return this.runner(jobId, request, { onEvent, signal: controller.signal }).then(
      (result) => {
        if (result.job_id !== jobId) {
          this.update(jobId, token, {
            status: 'error',
            error: new ApiError('Received a result for a different job', { code: 'job_mismatch', status: 0 }),
          })
          return
        }
        this.update(jobId, token, { status: 'done', result, error: null, progress: null })
      },
      (err: unknown) => {
        if ((err as Error)?.name === 'AbortError') return
        const error =
          err instanceof ApiError ? err : new ApiError((err as Error)?.message ?? 'Search failed', { code: 'unknown', status: 0 })
        this.update(jobId, token, { status: 'error', error })
      },
    ).finally(() => {
      if (this.controllers.get(jobId) === controller) this.controllers.delete(jobId)
    })
  }

  retry(jobId: string): Promise<void> | undefined {
    const run = this.runs.get(jobId)
    return run ? this.start(jobId, run.request) : undefined
  }
}
