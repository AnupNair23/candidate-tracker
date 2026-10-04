import { useState } from 'react'
import { Avatar } from '../../components/Avatar'
import { SkillChip } from '../../components/SkillChip'
import { Stars } from '../../components/Stars'
import { MAX_GAP_CHIPS, RESULTS_INITIAL } from '../../constants/search'
import type { ShortlistEntry } from '../../models'
import { locationLine } from '../../utils/format'

export function ResultsList({
  entries,
  openCandidateId,
  onOpen,
}: {
  entries: ShortlistEntry[]
  openCandidateId: string | null
  onOpen: (id: string) => void
}) {
  const [showAll, setShowAll] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const visible = showAll ? entries : entries.slice(0, RESULTS_INITIAL)
  const allSelected = entries.length > 0 && selected.size === entries.length

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  return (
    <>
      <div className="card">
        <div className="cand-head cand-grid">
          <input
            type="checkbox"
            className="checkbox"
            aria-label="Select all"
            checked={allSelected}
            onChange={() => setSelected(allSelected ? new Set() : new Set(entries.map((e) => e.candidate_id)))}
          />
          <span>
            <strong style={{ color: 'var(--text)' }}>{entries.length} match</strong> · sorted by fit
          </span>
          <span>Fit</span>
          <span>Matched skills</span>
        </div>
        {visible.map((e) => (
          <div
            key={e.candidate_id}
            className={`cand-row cand-grid${selected.has(e.candidate_id) ? ' selected' : ''}${openCandidateId === e.candidate_id ? ' open' : ''}`}
            onClick={() => onOpen(e.candidate_id)}
            role="button"
            tabIndex={0}
            onKeyDown={(ev) => ev.key === 'Enter' && onOpen(e.candidate_id)}
            aria-label={`Open ${e.name}`}
          >
            <input
              type="checkbox"
              className="checkbox"
              aria-label={`Select ${e.name}`}
              checked={selected.has(e.candidate_id)}
              onClick={(ev) => ev.stopPropagation()}
              onChange={() => toggle(e.candidate_id)}
            />
            <div className="row" style={{ alignItems: 'flex-start', gap: 10, minWidth: 0 }}>
              <Avatar name={e.name} id={e.candidate_id} />
              <div style={{ minWidth: 0 }}>
                <div className="row" style={{ gap: 6 }}>
                  <span className="rank" title="Rank">#{e.rank}</span>
                  <span className="cand-name">{e.name}</span>
                  <span className="faint small">ID {e.candidate_id}</span>
                </div>
                <div className="cand-meta">{[e.title, e.employer].filter(Boolean).join(' · ') || 'Title unknown'}</div>
                <div className="cand-meta">{locationLine({ city: e.city, state: e.state, distance_mi: e.distance_mi, years: e.years_experience }) || 'Location unknown'}</div>
                <div className="cand-reason">{e.reason}</div>
                <div className="chips" style={{ marginTop: 6 }}>
                  {e.job_linked && <span className="chip outline">On this job · {e.job_link_status}</span>}
                  {e.placed_by_us_year && <span className="chip green">Placed by us · {e.placed_by_us_year}</span>}
                  {e.injection_suspected && <span className="chip yellow" title="The profile contained text that looked like instructions to the AI; it was ignored.">⚠ Instructions in profile ignored</span>}
                </div>
              </div>
            </div>
            <div>
              <Stars value={e.stars} label={`Fit ${e.fit_score}/100`} />
              <div className="faint small">{e.fit_score}/100 · {e.tier}</div>
            </div>
            <div className="chips">
              {e.matched.filter((m) => m.kind !== 'other').map((m) => (
                <SkillChip key={m.requirement_id} m={m} />
              ))}
              {e.gaps.filter((g) => g.kind !== 'other').slice(0, MAX_GAP_CHIPS).map((g) => (
                <SkillChip key={g.requirement_id} m={g} />
              ))}
            </div>
          </div>
        ))}
        <div className="pagination">
          <span>
            Showing {visible.length} of {entries.length}
          </span>
          {entries.length > RESULTS_INITIAL && (
            <button className="btn ghost" onClick={() => setShowAll((s) => !s)}>
              {showAll ? 'Show fewer' : `Show ${entries.length - RESULTS_INITIAL} more`}
            </button>
          )}
        </div>
      </div>

      {selected.size > 0 && (
        <div className="bulkbar" role="toolbar" aria-label="Bulk actions">
          <span>{selected.size} selected</span>
          <span className="tooltip" data-tip="Coming soon — v1 is read-only">
            <button className="btn primary" disabled>Add to job</button>
          </span>
          <span className="tooltip" data-tip="Coming soon — v1 is read-only">
            <button className="btn" disabled>✕ Dismiss ▾</button>
          </span>
          <button className="btn ghost" aria-label="Clear selection" onClick={() => setSelected(new Set())}>✕</button>
        </div>
      )}
    </>
  )
}
