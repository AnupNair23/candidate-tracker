import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api/client'
import { ApiError } from '../../api/errors'
import { Avatar } from '../../components/Avatar'
import { ErrorState } from '../../components/ErrorState'
import { Skeleton, SkeletonRows } from '../../components/Skeleton'
import { SkillChip } from '../../components/SkillChip'
import { Stars } from '../../components/Stars'
import { SOURCE_LABEL } from '../../constants/sources'
import type { EvidenceRef, Interaction, SearchIntent, ShortlistEntry, SkillMatch } from '../../models'
import { formatDate, locationLine } from '../../utils/format'

type Props = {
  candidateId: string
  /** Job whose submittal history to include. */
  jobId?: string
  nameHint?: string
  /** Shortlist entry for the *current job* only — never another job's. */
  entry?: ShortlistEntry
  intent: SearchIntent | null
  onClose: () => void
}

const mismatch = () => new ApiError('Received data for a different candidate', { code: 'candidate_mismatch', status: 0 })

function Evidence({ items }: { items: EvidenceRef[] }) {
  if (!items.length) return null
  return (
    <>
      {items.map((ev) => (
        <div key={ev.id} className="evidence">
          <div className="src">
            {SOURCE_LABEL[ev.source] ?? ev.source}
            {ev.date ? ` · ${formatDate(ev.date)}` : ''}
          </div>
          “{ev.quote}”
        </div>
      ))}
    </>
  )
}

function MatchDetail({ m }: { m: SkillMatch }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ marginBottom: 6 }}>
      <button className="btn ghost" style={{ padding: 0 }} onClick={() => setOpen((o) => !o)} aria-expanded={open} disabled={!m.evidence.length}>
        <SkillChip m={m} /> {m.must_have && <span className="faint small">must-have</span>} {m.evidence.length > 0 && <span className="faint small">{open ? '▴' : '▾'} evidence</span>}
      </button>
      {open && <Evidence items={m.evidence} />}
    </div>
  )
}

function WhySection({ entry }: { entry: ShortlistEntry }) {
  return (
    <div className="section why">
      <h3>
        <span>✦ Why recommended</span>
        <span className="faint small">#{entry.rank} · fit {entry.fit_score}/100 · {entry.tier}</span>
      </h3>
      <p className="prose" style={{ marginBottom: 10 }}>{entry.reason}</p>
      {entry.injection_suspected && (
        <div className="alert warn small" style={{ marginBottom: 10 }}>
          This profile contained text that looked like instructions to the AI. It was treated as data and ignored.
        </div>
      )}
      <div className="small muted" style={{ marginBottom: 4 }}>What matched</div>
      {entry.matched.length ? entry.matched.map((m) => <MatchDetail key={m.requirement_id} m={m} />) : <div className="small faint">No requirement was evidenced.</div>}
      {entry.gaps.length > 0 && (
        <>
          <div className="small muted" style={{ margin: '8px 0 4px' }}>Unknown or not evidenced (not proof of a gap)</div>
          {entry.gaps.map((m) => <MatchDetail key={m.requirement_id} m={m} />)}
        </>
      )}
      <div className="small muted" style={{ margin: '12px 0 4px' }}>How each source affected this recommendation</div>
      {entry.contributions.length === 0 && <div className="small faint">No source changed the assessment beyond the skills above.</div>}
      {entry.contributions.map((c, i) => (
        <div key={`${c.source}-${i}`} className="contrib">
          <span className={`effect ${c.effect}`} aria-label={c.effect}>{c.effect === 'positive' ? '+' : c.effect === 'negative' ? '−' : '·'}</span>
          <div>
            <div className="small" style={{ fontWeight: 600 }}>{SOURCE_LABEL[c.source] ?? c.source}</div>
            <div className="prose">{c.summary}</div>
            <Evidence items={c.evidence} />
          </div>
        </div>
      ))}
      {entry.concerns.length > 0 && (
        <>
          <div className="small muted" style={{ margin: '12px 0 4px' }}>Confirm with the candidate</div>
          <ul className="prose" style={{ margin: 0, paddingLeft: 18 }}>{entry.concerns.map((c) => <li key={c}>{c}</li>)}</ul>
        </>
      )}
      {entry.sources_unavailable.length > 0 && (
        <div className="small faint" style={{ marginTop: 10 }}>
          Not available from JobDiva for this assessment: {entry.sources_unavailable.map((s) => SOURCE_LABEL[s] ?? s).join(', ')}.
        </div>
      )}
      <div className="small faint" style={{ marginTop: 6 }}>Assessed by {entry.assessed_by}. Decision support only — the hiring manager decides.</div>
    </div>
  )
}

function InteractionItem({ it }: { it: Interaction }) {
  return (
    <div className="note">
      <div className="small faint">
        {[SOURCE_LABEL[it.type] ?? it.type, it.author, formatDate(it.date), it.client].filter(Boolean).join(' · ')}
      </div>
      <div className="prose">{it.content}</div>
    </div>
  )
}

export function CandidateDrawer({ candidateId, jobId, nameHint, entry, intent, onClose }: Props) {
  const [showResume, setShowResume] = useState(false)
  const profile = useQuery({
    queryKey: ['candidate', candidateId],
    queryFn: async ({ signal }) => {
      const data = await api.candidate(candidateId, nameHint ?? entry?.name, signal)
      if (data.candidate_id !== candidateId) throw mismatch()
      return data
    },
    retry: false,
  })
  const history = useQuery({
    queryKey: ['interactions', candidateId, jobId],
    queryFn: async ({ signal }) => {
      const data = await api.interactions(candidateId, jobId, signal)
      if (data.candidate_id !== candidateId) throw mismatch()
      return data
    },
    retry: false,
  })
  const resume = useQuery({
    queryKey: ['resume', candidateId],
    queryFn: async ({ signal }) => {
      const data = await api.resume(candidateId, signal)
      if (data.candidate_id !== candidateId) throw mismatch()
      return data
    },
    enabled: showResume,
    retry: false,
  })

  const p = profile.data
  const name = p?.name ?? entry?.name ?? nameHint ?? `Candidate ${candidateId}`
  const asked = new Set(
    (intent?.requirements ?? []).flatMap((r) => [r.text, ...r.aliases]).map((s) => s.toLowerCase()),
  )

  return (
    <div aria-label={`Candidate ${name}`}>
      <div className="drawer-head">
        <div className="row between" style={{ alignItems: 'flex-start' }}>
          <div className="row" style={{ alignItems: 'flex-start' }}>
            <Avatar name={name} id={candidateId} />
            <div>
              <div style={{ fontWeight: 600, fontSize: 15 }}>{name}</div>
              <div className="small muted">
                {profile.isLoading ? <Skeleton width={160} height={10} /> : [p?.title ?? entry?.title, p?.employer ?? entry?.employer].filter(Boolean).join(' · ') || 'Title unknown'}
              </div>
              <div className="faint small">ID {candidateId}</div>
            </div>
          </div>
          <div className="row">
            <span className="tooltip" data-tip="Coming soon — v1 is read-only"><button className="btn primary" disabled>Add to job</button></span>
            <button className="btn ghost" onClick={onClose} aria-label="Close candidate">✕</button>
          </div>
        </div>
        <div className="row wrap small" style={{ marginTop: 10, gap: 10 }}>
          {entry && <Stars value={entry.stars} label={`Fit ${entry.fit_score}/100`} />}
          {(p?.years_experience ?? entry?.years_experience) != null && <span className="muted">{p?.years_experience ?? entry?.years_experience} yrs</span>}
          {entry?.placed_by_us_year && <span className="chip green">Placed by us · {entry.placed_by_us_year}</span>}
          <button className="btn ghost small" style={{ padding: 0 }} onClick={() => setShowResume((s) => !s)}>📄 {showResume ? 'Hide resume' : 'Full resume'}</button>
        </div>
      </div>

      {showResume && (
        <div className="section">
          <h3>Resume</h3>
          {resume.isLoading ? <SkeletonRows rows={4} /> : resume.isError ? <ErrorState error={resume.error} onRetry={() => resume.refetch()} compact /> : resume.data?.text ? (
            <div className="pre" style={{ maxHeight: 320, overflow: 'auto' }}>{resume.data.text}</div>
          ) : (
            <div className="small muted">
              {resume.data?.available === false ? 'Resume text is not exposed by the JobDiva v1 standard API (BI access required).' : 'No resume on file in JobDiva.'}
            </div>
          )}
        </div>
      )}

      {entry ? (
        <WhySection entry={entry} />
      ) : (
        <div className="section small muted">This candidate is not in the current shortlist for this job. Run a search to see an assessment.</div>
      )}

      <div className="section">
        <h3>Skills</h3>
        {profile.isLoading ? <SkeletonRows rows={2} /> : profile.isError ? <ErrorState error={profile.error} onRetry={() => profile.refetch()} compact /> : p && p.skills.length ? (
          <>
            <div className="chips">
              {p.skills.map((s) => (
                <span key={`${s.name}:${s.value}`} className={`chip${asked.has(s.value.toLowerCase()) ? ' green' : ''}`} title={s.name}>{s.value}</span>
              ))}
            </div>
            {asked.size > 0 && <div className="small faint" style={{ marginTop: 6 }}>Green = asked for in this job</div>}
          </>
        ) : (
          <div className="small muted">No skills recorded in JobDiva.</div>
        )}
      </div>

      <div className="section">
        <h3>Contact</h3>
        {profile.isLoading ? <SkeletonRows rows={2} /> : p ? (
          <div className="contact-list">
            <div>📞 {p.phone ?? <span className="faint">No phone on file</span>}</div>
            <div>✉️ {p.email ?? <span className="faint">No email on file</span>}</div>
            <div>📍 {locationLine({ city: p.city, state: p.state, distance_mi: entry?.distance_mi }) || <span className="faint">Location unknown</span>}</div>
          </div>
        ) : null}
      </div>

      <div className="section">
        <h3>
          <span>Notes</span>
          <span className="faint small">{history.data?.notes.length ?? ''}</span>
        </h3>
        <div className="row tooltip" data-tip="Coming soon — v1 is read-only" style={{ marginBottom: 8 }}>
          <input className="input" placeholder={`Add a note about ${name.split(' ')[0]}…`} disabled />
          <button className="btn" disabled>Add</button>
        </div>
        {history.isLoading ? <SkeletonRows rows={2} /> : history.isError ? <ErrorState error={history.error} onRetry={() => history.refetch()} compact /> : history.data && history.data.notes.length ? (
          history.data.notes.map((n) => <InteractionItem key={n.interaction_id} it={n} />)
        ) : (
          <div className="small muted">
            {history.data?.sources.notes === 'unavailable' ? 'Candidate notes are not exposed by the JobDiva v1 standard API.' : 'No notes in JobDiva.'}
          </div>
        )}
      </div>

      <div className="section">
        <h3>History with us</h3>
        {history.isLoading ? <SkeletonRows rows={3} /> : history.data && history.data.history.length ? (
          history.data.history.map((h) => <InteractionItem key={h.interaction_id} it={h} />)
        ) : (
          !history.isError && <div className="small muted">{history.data?.sources.history === 'unavailable' ? 'Submittal history could not be loaded.' : 'No submittals, interviews or placements in JobDiva.'}</div>
        )}
      </div>

      <div className="section">
        <h3>Jobs</h3>
        {profile.isLoading ? <SkeletonRows rows={2} /> : p && p.work_history.length ? (
          p.work_history.map((w, i) => (
            <div key={i} className="timeline-item">
              <span className="tdot" />
              <div>
                <div className="row between"><strong className="small">{w.title ?? 'Role'}</strong><span className="faint small">{[w.start, w.end ?? 'now'].filter(Boolean).join(' – ')}</span></div>
                <div className="small muted">{[w.company, w.location].filter(Boolean).join(' · ')}</div>
                {w.description && <div className="prose small">{w.description}</div>}
              </div>
            </div>
          ))
        ) : (
          <div className="small muted">
            {p?.work_history_state === 'unavailable' ? 'Work history is not exposed by the JobDiva v1 standard API.' : 'No work history in JobDiva.'}
          </div>
        )}
      </div>
    </div>
  )
}
