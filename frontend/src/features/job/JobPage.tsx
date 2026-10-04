import { useQuery } from '@tanstack/react-query'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../../api/client'
import { ErrorState } from '../../components/ErrorState'
import { Skeleton } from '../../components/Skeleton'
import { useSearchRun } from '../../hooks/useSearchRuns'
import type { Job } from '../../models'
import { CandidatesTab } from '../candidates/CandidatesTab'
import { CandidateDrawer } from '../drawer/CandidateDrawer'
import { SourcingTab } from '../sourcing/SourcingTab'
import { JobDescriptionPanel } from './JobDescriptionPanel'

function subtitle(job: Job) {
  const rate =
    job.rate_min != null || job.rate_max != null
      ? `$${[job.rate_min, job.rate_max].filter((x) => x != null).join('–')}`
      : null
  return [job.company, [job.city, job.state].filter(Boolean).join(', '), job.onsite_remote, job.ref ?? job.job_id, rate]
    .filter(Boolean)
    .join(' · ')
}

export function JobPage() {
  const { jobId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'candidates' ? 'candidates' : 'sourcing'
  const candidateId = params.get('candidate')

  const job = useQuery({ queryKey: ['job', jobId], queryFn: ({ signal }) => api.job(jobId, signal), retry: false })
  const linked = useQuery({
    queryKey: ['linked', jobId],
    queryFn: ({ signal }) => api.linkedCandidates(jobId, signal),
    retry: false,
  })
  const run = useSearchRun(jobId)
  const shortlist = run?.result?.job_id === jobId ? run.result.shortlist : []

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value === null) next.delete(key)
    else next.set(key, value)
    setParams(next)
  }
  const openCandidate = (id: string | null) => setParam('candidate', id)
  const entry = candidateId ? shortlist.find((e) => e.candidate_id === candidateId) : undefined

  return (
    <>
      <div className="crumbs">
        <Link to="/jobs">Jobs</Link> › <strong>{job.data?.title ?? jobId}</strong>
      </div>
      <div className="page-head">
        {job.isLoading ? (
          <div style={{ display: 'grid', gap: 8 }}>
            <Skeleton width={320} height={20} />
            <Skeleton width={420} height={12} />
          </div>
        ) : job.isError ? (
          <ErrorState error={job.error} onRetry={() => job.refetch()} compact />
        ) : (
          job.data && (
            <>
              <h1>{job.data.title}</h1>
              <p className="page-sub">{subtitle(job.data)}</p>
            </>
          )
        )}
        <div className="tabs" role="tablist">
          <button
            role="tab"
            aria-selected={tab === 'candidates'}
            className={`tab${tab === 'candidates' ? ' active' : ''}`}
            onClick={() => setParam('tab', 'candidates')}
          >
            Candidates<span className="count">{linked.data?.items.length ?? ''}</span>
          </button>
          <button
            role="tab"
            aria-selected={tab === 'sourcing'}
            className={`tab${tab === 'sourcing' ? ' active' : ''}`}
            onClick={() => setParam('tab', 'sourcing')}
          >
            Sourcing<span className="count">{run?.result ? run.result.shortlist.length : ''}</span>
          </button>
        </div>
      </div>
      <div className="content">
        <div className="split">
          <div>
            {tab === 'sourcing' ? (
              <SourcingTab key={jobId} jobId={jobId} job={job.data} openCandidateId={candidateId} onOpenCandidate={openCandidate} />
            ) : (
              <CandidatesTab jobId={jobId} query={linked} openCandidateId={candidateId} onOpenCandidate={openCandidate} />
            )}
          </div>
          <div className="card panel">
            {candidateId ? (
              <CandidateDrawer
                key={`${jobId}:${candidateId}`}
                candidateId={candidateId}
                nameHint={entry?.name ?? linked.data?.items.find((i) => i.candidate_id === candidateId)?.name}
                entry={entry}
                intent={run?.result?.intent ?? null}
                onClose={() => openCandidate(null)}
              />
            ) : (
              <JobDescriptionPanel query={job} />
            )}
          </div>
        </div>
      </div>
    </>
  )
}
