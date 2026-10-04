import type { UseQueryResult } from '@tanstack/react-query'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { SkeletonRows } from '../../components/Skeleton'
import type { Job } from '../../models'

export function JobDescriptionPanel({ query }: { query: UseQueryResult<Job> }) {
  if (query.isLoading) return <SkeletonRows rows={7} />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => query.refetch()} />
  const job = query.data
  if (!job) return null
  return (
    <>
      <div className="drawer-head">
        <div className="small muted">Job description</div>
        <h3 style={{ fontSize: 15, marginTop: 2 }}>{job.title}</h3>
        <div className="chips" style={{ marginTop: 8 }}>
          {job.status && <span className="chip outline">{job.status}</span>}
          {job.job_type && <span className="chip outline">{job.job_type}</span>}
          {job.onsite_remote && <span className="chip outline">{job.onsite_remote}</span>}
          {job.issue_date && <span className="chip outline">Issued {job.issue_date}</span>}
        </div>
      </div>
      <div className="section">
        {job.description_html ? (
          // Sanitized server-side with bleach (allow-listed tags, no attributes).
          <div className="prose" dangerouslySetInnerHTML={{ __html: job.description_html }} />
        ) : job.description_text ? (
          <div className="pre">{job.description_text}</div>
        ) : (
          <EmptyState title="No description in JobDiva">This job has no description text.</EmptyState>
        )}
      </div>
    </>
  )
}
