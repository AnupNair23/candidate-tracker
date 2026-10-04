import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { ApiError } from '../api/errors'
import { ErrorState } from '../components/ErrorState'
import { CandidateDrawer } from '../features/drawer/CandidateDrawer'
import { JobsPage } from '../features/jobs/JobsPage'
import { deferred } from './fixtures'

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

const json = (data: unknown, status = 200, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json', ...headers } })

const profile = (id: string, name: string) => ({
  candidate_id: id, name, title: 'Engineer', employer: null, city: 'Huntsville', state: 'AL', zipcode: null,
  email: null, phone: null, years_experience: null, available: null, updated_on: null, skills: [], work_history: [],
  work_history_state: 'unavailable',
})
const interactions = (id: string) => ({ candidate_id: id, notes: [], history: [], sources: { notes: 'unavailable', history: 'none' } })

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('ErrorState', () => {
  it('counts down before allowing a retry after a 429', () => {
    vi.useFakeTimers()
    const onRetry = vi.fn()
    render(<ErrorState error={new ApiError('x', { code: 'rate_limited', status: 429, source: 'jobdiva', retryAfter: 2 })} onRetry={onRetry} retryLabel="Retry search" />)
    expect(screen.getByText('JobDiva is rate-limiting requests')).toBeInTheDocument()
    const button = screen.getByRole('button')
    expect(button).toBeDisabled()
    expect(button).toHaveTextContent('Retry search in 2s')
    act(() => vi.advanceTimersByTime(1000))
    act(() => vi.advanceTimersByTime(1000))
    expect(screen.getByRole('button')).toBeEnabled()
    fireEvent.click(screen.getByRole('button'))
    expect(onRetry).toHaveBeenCalled()
  })
})

describe('CandidateDrawer', () => {
  it('never shows a stale response for a previously opened candidate', async () => {
    const slowX = deferred<Response>()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.startsWith('/api/candidates/X/interactions')) return json(interactions('X'))
        if (url.startsWith('/api/candidates/Y/interactions')) return json(interactions('Y'))
        if (url.startsWith('/api/candidates/X')) return slowX.promise
        if (url.startsWith('/api/candidates/Y')) return json(profile('Y', 'Yara Young'))
        return json({}, 404)
      }),
    )
    const { rerender } = wrap(<CandidateDrawer key="X" candidateId="X" intent={null} onClose={() => {}} />)
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <CandidateDrawer key="Y" candidateId="Y" intent={null} onClose={() => {}} />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    await screen.findByText('Yara Young')
    slowX.resolve(json(profile('X', 'Xavier Stale')))
    await new Promise((r) => setTimeout(r, 20))
    expect(screen.queryByText('Xavier Stale')).not.toBeInTheDocument()
  })

  it('refuses data whose candidate_id does not match the opened candidate', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        url.includes('/interactions') ? json(interactions('Y')) : json(profile('Z', 'Wrong Person')),
      ),
    )
    wrap(<CandidateDrawer candidateId="Y" intent={null} onClose={() => {}} />)
    expect(await screen.findByText(/Received data for a different candidate/)).toBeInTheDocument()
    expect(screen.queryByText('Wrong Person')).not.toBeInTheDocument()
  })
})

describe('JobsPage', () => {
  it('shows loading, then jobs, and requests the chosen page size', async () => {
    const fetchMock = vi.fn(async (_url: string) =>
      json({ items: [{ job_id: '21000', title: 'Mechanical Design Engineer', company: 'Aerodyne' }], page: 1, page_size: 30, has_next: false }),
    )
    vi.stubGlobal('fetch', fetchMock)
    wrap(<JobsPage />)
    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument()
    expect(await screen.findByText('Mechanical Design Engineer')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Jobs per page'), { target: { value: '50' } })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/jobs?page=1&page_size=50', expect.anything()))
  })

  it('shows an empty state', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ items: [], page: 1, page_size: 30, has_next: false })))
    wrap(<JobsPage />)
    expect(await screen.findByText('No open jobs')).toBeInTheDocument()
  })

  it('shows a typed error with retry', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({ error: { code: 'jobdiva_auth_failed', message: 'JobDiva credentials rejected', source: 'jobdiva', retry_after: null } }, 502)),
    )
    wrap(<JobsPage />)
    expect(await screen.findByText('JobDiva rejected the credentials')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})
