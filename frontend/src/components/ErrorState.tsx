import { ApiError } from '../api/errors'
import { DEFAULT_RETRY_AFTER_S } from '../constants/search'
import { useCountdown } from '../hooks/useCountdown'

function describe(error: unknown): { title: string; detail: string } {
  if (!(error instanceof ApiError)) return { title: 'Something went wrong', detail: String((error as Error)?.message ?? error) }
  switch (error.code) {
    case 'rate_limited':
      return {
        title: error.source === 'claude' ? 'Claude is rate-limiting requests' : 'JobDiva is rate-limiting requests',
        detail: 'Too many requests in a short time. Wait a moment, then retry.',
      }
    case 'jobdiva_auth_failed':
      return { title: 'JobDiva rejected the credentials', detail: error.message }
    case 'jobdiva_not_configured':
      return { title: 'JobDiva is not configured', detail: 'Add JOBDIVA_CLIENT_ID, JOBDIVA_USERNAME and JOBDIVA_PASSWORD to .env and restart the backend.' }
    case 'jobdiva_unavailable':
      return { title: 'JobDiva is unavailable', detail: error.message }
    case 'claude_not_configured':
      return { title: 'Claude is not configured', detail: 'Add ANTHROPIC_API_KEY to .env (or set LLM_MODE=stub for UI development) and restart the backend.' }
    case 'claude_auth_failed':
    case 'claude_unavailable':
    case 'claude_error':
    case 'claude_refusal':
      return { title: 'The AI assessment failed', detail: error.message }
    case 'not_found':
      return { title: 'Not found in JobDiva', detail: error.message }
    case 'network_error':
      return { title: 'Cannot reach the sourcing service', detail: 'Is the backend running on port 8000?' }
    default:
      return { title: 'Something went wrong', detail: error.message }
  }
}

/** Error with retry. For 429s, shows a countdown and enables Retry when it reaches zero. */
export function ErrorState({ error, onRetry, retryLabel = 'Retry', compact }: { error: unknown; onRetry?: () => void; retryLabel?: string; compact?: boolean }) {
  const { title, detail } = describe(error)
  const wait = error instanceof ApiError && error.isRateLimited ? Math.ceil(error.retryAfter ?? DEFAULT_RETRY_AFTER_S) : 0
  const remaining = useCountdown(wait, error)

  const button = onRetry && (
    <button className="btn" onClick={onRetry} disabled={remaining > 0}>
      {remaining > 0 ? `${retryLabel} in ${remaining}s` : retryLabel}
    </button>
  )
  if (compact) {
    return (
      <div className="alert error row between" role="alert">
        <span>
          <strong>{title}.</strong> {detail}
        </span>
        {button}
      </div>
    )
  }
  return (
    <div className="state" role="alert">
      <h4>{title}</h4>
      <div>{detail}</div>
      {button}
    </div>
  )
}
