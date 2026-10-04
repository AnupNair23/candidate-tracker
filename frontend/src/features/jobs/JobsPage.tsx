import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../../api/client'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { SkeletonRows } from '../../components/Skeleton'
import { DEFAULT_PAGE_SIZE, PAGE_SIZES } from '../../constants/jobs'

export function JobsPage() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const page = Math.max(1, Number(params.get('page')) || 1)
  const sizeParam = Number(params.get('size'))
  const pageSize = PAGE_SIZES.includes(sizeParam) ? sizeParam : DEFAULT_PAGE_SIZE

  const jobs = useQuery({
    queryKey: ['jobs', page, pageSize],
    queryFn: ({ signal }) => api.jobs(page, pageSize, signal),
    placeholderData: keepPreviousData,
    retry: false,
  })

  const go = (nextPage: number, nextSize = pageSize) => setParams({ page: String(nextPage), size: String(nextSize) })

  return (
    <>
      <div className="crumbs">
        <strong>Jobs</strong>
      </div>
      <div className="page-head" style={{ paddingBottom: 16 }}>
        <h1>Jobs</h1>
        <p className="page-sub">Open jobs from JobDiva. Select a job to see its description and source candidates.</p>
      </div>
      <div className="content">
        <div className="card">
          <div className="card-head">
            <span>
              <strong>Open jobs</strong> {jobs.isFetching && !jobs.isLoading && <span className="faint">· refreshing…</span>}
            </span>
            <label className="row small">
              Show
              <select
                className="select"
                style={{ width: 80, padding: '4px 8px' }}
                value={pageSize}
                onChange={(e) => go(1, Number(e.target.value))}
                aria-label="Jobs per page"
              >
                {PAGE_SIZES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              per page
            </label>
          </div>

          {jobs.isLoading ? (
            <SkeletonRows rows={8} />
          ) : jobs.isError ? (
            <ErrorState error={jobs.error} onRetry={() => jobs.refetch()} />
          ) : !jobs.data || jobs.data.items.length === 0 ? (
            <EmptyState title={page > 1 ? 'No more jobs' : 'No open jobs'}>
              {page > 1 ? 'You are past the last page.' : 'JobDiva returned no open jobs for this account.'}
            </EmptyState>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 120 }}>Job ID</th>
                  <th>Title</th>
                  <th>Client</th>
                  <th>Location</th>
                  <th style={{ width: 110 }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {jobs.data.items.map((job) => (
                  <tr
                    key={job.job_id}
                    className="clickable"
                    tabIndex={0}
                    onClick={() => navigate(`/jobs/${encodeURIComponent(job.job_id)}`)}
                    onKeyDown={(e) => e.key === 'Enter' && navigate(`/jobs/${encodeURIComponent(job.job_id)}`)}
                  >
                    <td>
                      <div>{job.job_id}</div>
                      {job.ref && <div className="faint small">{job.ref}</div>}
                    </td>
                    <td style={{ fontWeight: 500 }}>{job.title}</td>
                    <td className="muted">{job.company ?? '—'}</td>
                    <td className="muted">{[job.city, job.state].filter(Boolean).join(', ') || '—'}</td>
                    <td>{job.status ? <span className="chip outline">{job.status}</span> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <div className="pagination">
            <span>
              Page {page}
              {jobs.data && ` · showing ${jobs.data.items.length} jobs`}
            </span>
            <span className="row">
              <button className="btn" disabled={page <= 1 || jobs.isFetching} onClick={() => go(page - 1)}>
                ← Previous
              </button>
              <button className="btn" disabled={!jobs.data?.has_next || jobs.isFetching} onClick={() => go(page + 1)}>
                Next →
              </button>
            </span>
          </div>
        </div>
      </div>
    </>
  )
}
