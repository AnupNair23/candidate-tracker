import { useState } from 'react'
import type { SearchResult } from '../../models'

export function ShortfallPanel({ result }: { result: SearchResult }) {
  const [open, setOpen] = useState(false)
  const { shortfall, funnel } = result
  return (
    <div className="card" style={{ marginBottom: 14 }}>
      {shortfall && (
        <div className="card-body" style={{ borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>{shortfall.headline}</div>
          <ul className="prose" style={{ margin: '0 0 8px', paddingLeft: 18 }}>
            {shortfall.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          {shortfall.suggestions.length > 0 && (
            <>
              <div className="small muted" style={{ marginBottom: 4 }}>To find more</div>
              <ul className="prose" style={{ margin: 0, paddingLeft: 18 }}>
                {shortfall.suggestions.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
      <div className="card-head" style={{ borderBottom: open ? undefined : 0 }}>
        <span className="small">
          {funnel.pool} found in JobDiva · {funnel.reviewed} reviewed in depth · {funnel.shortlisted} shortlisted
        </span>
        <button className="btn ghost small" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? 'Hide search details' : 'Search details'}
        </button>
      </div>
      {open && (
        <div className="card-body small">
          <table className="table">
            <thead>
              <tr>
                <th>JobDiva search</th>
                <th>Criteria</th>
                <th>Returned</th>
                <th>New</th>
              </tr>
            </thead>
            <tbody>
              {funnel.queries.map((q) => (
                <tr key={q.label + q.criteria}>
                  <td>{q.label}</td>
                  <td className="muted" style={{ fontFamily: 'ui-monospace, monospace', fontSize: 11.5 }}>
                    {q.criteria}
                    {q.error && <div style={{ color: 'var(--red-text)' }}>{q.error}</div>}
                  </td>
                  <td>{q.returned}{q.found != null && q.found !== q.returned ? ` of ${q.found}` : ''}</td>
                  <td>{q.new}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="muted" style={{ marginTop: 10 }}>
            Excluded by required filters: {Object.entries(funnel.excluded_by_filter).map(([k, v]) => `${k} ${v}`).join(', ') || 'none'} ·
            Below review depth: {funnel.prescreened_out} · Contradicted a must-have: {funnel.not_a_fit} · No evidence on file:{' '}
            {funnel.insufficient_evidence} · Not assessed: {funnel.not_assessed} · Assessed by {result.assessed_by}
          </div>
        </div>
      )}
    </div>
  )
}
