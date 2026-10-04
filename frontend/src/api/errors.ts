import { ApiErrorSchema } from '../models'

export class ApiError extends Error {
  readonly code: string
  readonly status: number
  readonly source: string
  readonly retryAfter: number | null

  constructor(message: string, opts: { code: string; status: number; source?: string; retryAfter?: number | null }) {
    super(message)
    this.code = opts.code
    this.status = opts.status
    this.source = opts.source ?? 'server'
    this.retryAfter = opts.retryAfter ?? null
  }

  get isRateLimited(): boolean {
    return this.code === 'rate_limited' || this.status === 429
  }
}

export async function errorFromResponse(res: Response): Promise<ApiError> {
  let body: unknown = null
  try {
    body = await res.json()
  } catch {
    /* non-JSON error body */
  }
  const parsed = ApiErrorSchema.safeParse((body as { error?: unknown } | null)?.error)
  const header = Number(res.headers.get('Retry-After'))
  if (parsed.success) {
    return new ApiError(parsed.data.message, {
      code: parsed.data.code,
      status: res.status,
      source: parsed.data.source,
      retryAfter: parsed.data.retry_after ?? (Number.isFinite(header) && header > 0 ? header : null),
    })
  }
  return new ApiError(`Request failed (HTTP ${res.status})`, {
    code: res.status === 429 ? 'rate_limited' : 'http_error',
    status: res.status,
    retryAfter: Number.isFinite(header) && header > 0 ? header : null,
  })
}
