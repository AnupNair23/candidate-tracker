import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { Skeleton } from '../../components/Skeleton'
import { MAX_TEXT_CHARS } from '../../constants/api'
import { RECENT_LABEL_CHARS } from '../../constants/search'
import { useSearchRun, useSearchStore } from '../../hooks/useSearchRuns'
import type { Job, SavedSearch, SearchIntent } from '../../models'
import { loadSearches, saveSearch } from '../../state/history'
import { IntentFilters } from './IntentFilters'
import { ResultsList } from './ResultsList'
import { SearchProgress } from './SearchProgress'
import { ShortfallPanel } from './ShortfallPanel'

type Props = {
  jobId: string
  job: Job | undefined
  openCandidateId: string | null
  onOpenCandidate: (id: string | null) => void
}

export function SourcingTab({ jobId, job, openCandidateId, onOpenCandidate }: Props) {
  const store = useSearchStore()
  const run = useSearchRun(jobId)
  const [query, setQuery] = useState(run?.request.query ?? '')
  const [notes, setNotes] = useState(run?.request.notes ?? '')
  const [intent, setIntent] = useState<SearchIntent | null>(run?.request.intent ?? null)
  const [analyzed, setAnalyzed] = useState<SearchIntent | null>(run?.request.intent ?? null)
  const recent = loadSearches(jobId) // cheap localStorage read; refreshed on every render after a run

  const analyze = useMutation({
    mutationFn: () => api.intent(jobId, query, notes),
    onSuccess: (data) => {
      if (data.job_id !== jobId) return // never attach another job's intent
      setIntent(data.intent)
      setAnalyzed(data.intent)
    },
  })

  const startSearch = (body: { intent: SearchIntent; query: string; notes: string }) => {
    saveSearch(jobId, { ...body, ts: Date.now() })
    void store.start(jobId, body)
  }
  const runRecent = (s: SavedSearch) => {
    setQuery(s.query)
    setNotes(s.notes)
    setIntent(s.intent)
    setAnalyzed(s.intent)
    startSearch({ intent: s.intent, query: s.query, notes: s.notes })
  }

  const running = run?.status === 'running'
  const result = run?.result?.job_id === jobId ? run.result : null

  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="card">
        <div className="card-body stack">
          <div>
            <label className="field-label" htmlFor="query">What are you looking for?</label>
            <textarea
              id="query"
              className="textarea"
              placeholder={`e.g. ${job?.title ?? 'Mechanical design engineer'} with CATIA V5 and GD&T, aerospace structures, 3+ years, near ${job?.city ?? 'Huntsville'}`}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              maxLength={MAX_TEXT_CHARS}
            />
          </div>
          <div>
            <label className="field-label" htmlFor="notes">Recruiter notes (optional)</label>
            <textarea
              id="notes"
              className="textarea"
              style={{ minHeight: 48 }}
              placeholder="Preferences or context — e.g. prefer people we've placed before; client wants hands-on CATIA, not management"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              maxLength={MAX_TEXT_CHARS}
            />
          </div>
          <div className="row between wrap">
            <div className="chips">
              {recent.length > 0 && <span className="small muted">Recent:</span>}
              {recent.map((s) => (
                <button key={s.ts} className="chip outline" style={{ cursor: 'pointer' }} onClick={() => runRecent(s)} disabled={running} title="Run this search again with fresh JobDiva data">
                  {s.query.slice(0, RECENT_LABEL_CHARS) || s.intent.summary.slice(0, RECENT_LABEL_CHARS)}
                  {(s.query || s.intent.summary).length > RECENT_LABEL_CHARS ? '…' : ''}
                </button>
              ))}
            </div>
            <div className="row">
              <button className={`btn${intent ? '' : ' primary'}`} onClick={() => analyze.mutate()} disabled={analyze.isPending || running || (!query.trim() && !notes.trim() && !job)}>
                {analyze.isPending ? 'Analyzing…' : intent ? 'Re-analyze' : 'Analyze'}
              </button>
              <button className="btn primary" disabled={!intent || running} onClick={() => intent && startSearch({ intent, query, notes })}>
                {running ? 'Searching…' : 'Search'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {analyze.isPending && (
        <div className="card card-body" role="status" aria-label="Analyzing request">
          <div className="small muted" style={{ marginBottom: 8 }}>Understanding your request and the job description…</div>
          <div className="row"><Skeleton width={140} height={28} /><Skeleton width={120} height={28} /><Skeleton width={220} height={28} /></div>
        </div>
      )}
      {analyze.isError && <ErrorState error={analyze.error} onRetry={() => analyze.mutate()} compact />}

      {intent && !analyze.isPending && (
        <div>
          {intent.summary && <div className="small muted" style={{ marginBottom: 8 }}>{intent.summary}</div>}
          {intent.ambiguities.length > 0 && (
            <div className="alert info" style={{ marginBottom: 10 }}>
              <strong>Please confirm:</strong>
              <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>
                {intent.ambiguities.map((a) => <li key={a}>{a}</li>)}
              </ul>
            </div>
          )}
          <IntentFilters intent={intent} onChange={setIntent} onReset={() => analyzed && setIntent(analyzed)} disabled={running} />
        </div>
      )}

      {run?.status === 'running' && <SearchProgress run={run} />}
      {run?.status === 'error' && run.error && (
        <ErrorState error={run.error} onRetry={() => void store.retry(jobId)} retryLabel="Retry search" compact />
      )}

      {result && (
        <div style={running ? { opacity: 0.55 } : undefined}>
          {running && <div className="small muted" style={{ marginBottom: 6 }}>Previous results — a new search is running.</div>}
          {result.warnings.map((w) => (
            <div key={w} className="alert warn" style={{ marginBottom: 8 }}>{w}</div>
          ))}
          {result.partial && !result.warnings.length && (
            <div className="alert warn" style={{ marginBottom: 8 }}>Some candidates could not be fully reviewed; see search details.</div>
          )}
          <ShortfallPanel result={result} />
          {result.shortlist.length === 0 ? (
            <div className="card"><EmptyState title="No candidates met the bar for this search">See the explanation above for why, and what to relax.</EmptyState></div>
          ) : (
            <ResultsList entries={result.shortlist} openCandidateId={openCandidateId} onOpen={(id) => onOpenCandidate(id)} />
          )}
        </div>
      )}

      {!intent && !run && !analyze.isPending && (
        <div className="card">
          <EmptyState title="No search yet for this job">
            Describe the candidate you want (or just press Analyze to start from the job description). Claude turns it into
            filters you can edit, then ranks up to 30 JobDiva candidates with the evidence behind each recommendation.
          </EmptyState>
        </div>
      )}
    </div>
  )
}
