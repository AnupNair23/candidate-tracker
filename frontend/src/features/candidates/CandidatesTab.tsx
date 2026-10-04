import type { UseQueryResult } from '@tanstack/react-query'
import { Avatar } from '../../components/Avatar'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { SkeletonRows } from '../../components/Skeleton'
import type { LinkedCandidate } from '../../models'
import { formatDate } from '../../utils/format'

type Props = {
  jobId: string
  query: UseQueryResult<{ job_id: string; items: LinkedCandidate[]; warnings: string[] }>
  openCandidateId: string | null
  onOpenCandidate: (id: string) => void
}

export function CandidatesTab({ jobId, query, openCandidateId, onOpenCandidate }: Props) {
  if (query.isLoading) return <div className="card"><SkeletonRows rows={6} /></div>
  if (query.isError) return <div className="card"><ErrorState error={query.error} onRetry={() => query.refetch()} /></div>
  const items = query.data?.job_id === jobId ? query.data.items : []
  const warnings = query.data?.job_id === jobId ? query.data.warnings : []
  const notice = warnings.map((w) => (
    <div key={w} className="alert warn" style={{ margin: 12 }}>{w}</div>
  ))
  if (items.length === 0) {
    return (
      <div className="card">
        {notice}
        <EmptyState title="No candidates linked to this job yet">Submittals and starts recorded in JobDiva for this job appear here.</EmptyState>
      </div>
    )
  }
  return (
    <div className="card">
      {notice}
      <div className="card-head">
        <span><strong>{items.length} candidates</strong> on this job in JobDiva</span>
      </div>
      {items.map((c) => (
        <div
          key={c.candidate_id}
          className={`cand-row${openCandidateId === c.candidate_id ? ' open' : ''}`}
          role="button"
          tabIndex={0}
          onClick={() => onOpenCandidate(c.candidate_id)}
          onKeyDown={(e) => e.key === 'Enter' && onOpenCandidate(c.candidate_id)}
        >
          <div className="row" style={{ alignItems: 'flex-start', gap: 10 }}>
            <Avatar name={c.name} id={c.candidate_id} />
            <div style={{ flex: 1 }}>
              <div className="row between">
                <span>
                  <span className="cand-name">{c.name}</span> <span className="faint small">ID {c.candidate_id}</span>
                </span>
                {c.status && <span className="chip outline">{c.status}</span>}
              </div>
              <div className="cand-meta">
                {[c.title, [c.city, c.state].filter(Boolean).join(', '), formatDate(c.date)].filter(Boolean).join(' · ')}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
