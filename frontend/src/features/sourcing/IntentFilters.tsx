import { useEffect, useRef, useState, type ReactNode } from 'react'
import { DEFAULT_RADIUS_MI, SKILLS_LABEL_PREVIEW } from '../../constants/search'
import type { Requirement, SearchIntent } from '../../models'

type Props = {
  intent: SearchIntent
  onChange: (next: SearchIntent) => void
  onReset: () => void
  disabled?: boolean
}

function Filter({ label, value, required, children, disabled }: { label: string; value: string; required?: boolean; children: ReactNode; disabled?: boolean }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])
  return (
    <div className={`filter${required ? ' required' : ''}`} ref={ref}>
      <button className="btn ghost" style={{ padding: 0 }} onClick={() => setOpen((o) => !o)} disabled={disabled} aria-expanded={open}>
        <span className="k">{label}</span> <span className="v">{value}</span> <span className="faint">▾</span>
      </button>
      {open && <div className="popover">{children}</div>}
    </div>
  )
}

const numOrNull = (v: string) => (v.trim() === '' || Number.isNaN(Number(v)) ? null : Number(v))

export function IntentFilters({ intent, onChange, onReset, disabled }: Props) {
  const loc = intent.location
  const yrs = intent.years
  const skills = intent.requirements.filter((r) => r.kind !== 'authorization')
  const auth = intent.requirements.filter((r) => r.kind === 'authorization')
  const [newSkill, setNewSkill] = useState('')

  const setReq = (id: string, patch: Partial<Requirement>) =>
    onChange({ ...intent, requirements: intent.requirements.map((r) => (r.id === id ? { ...r, ...patch } : r)) })
  const removeReq = (id: string) => onChange({ ...intent, requirements: intent.requirements.filter((r) => r.id !== id) })
  const addReq = () => {
    const text = newSkill.trim()
    if (!text) return
    const id = `r${intent.requirements.length + 1}_${Date.now() % 10000}`
    onChange({
      ...intent,
      requirements: [...intent.requirements, { id, text, kind: 'skill', must_have: false, aliases: [], source: 'query' }],
    })
    setNewSkill('')
  }

  const locLabel = loc
    ? [[loc.city, loc.state].filter(Boolean).join(', ') || loc.zipcode, loc.radius_mi ? `within ${loc.radius_mi} mi` : null, loc.remote_ok ? 'remote ok' : null]
        .filter(Boolean)
        .join(' · ')
    : 'Any'
  const yrsLabel = yrs && (yrs.min != null || yrs.max != null) ? (yrs.max != null ? `${yrs.min ?? 0}–${yrs.max} years` : `${yrs.min}+ years`) : 'Any'
  const must = skills.filter((s) => s.must_have)
  const skillsLabel = skills.length ? (must.length ? must : skills).slice(0, SKILLS_LABEL_PREVIEW).map((s) => s.text).join(', ') + (skills.length > SKILLS_LABEL_PREVIEW ? ` +${skills.length - SKILLS_LABEL_PREVIEW}` : '') : 'None'

  return (
    <div className="filters" aria-label="Search filters">
      <Filter label="Location" value={locLabel} required={loc?.required} disabled={disabled}>
        <div className="stack">
          <div className="row">
            <div style={{ flex: 2 }}>
              <label className="field-label">City</label>
              <input className="input" value={loc?.city ?? ''} onChange={(e) => onChange({ ...intent, location: { ...(loc ?? emptyLoc()), city: e.target.value || null } })} />
            </div>
            <div style={{ flex: 1 }}>
              <label className="field-label">State</label>
              <input className="input" value={loc?.state ?? ''} onChange={(e) => onChange({ ...intent, location: { ...(loc ?? emptyLoc()), state: e.target.value || null } })} />
            </div>
          </div>
          <div className="row">
            <div style={{ flex: 1 }}>
              <label className="field-label">Zip</label>
              <input className="input" value={loc?.zipcode ?? ''} onChange={(e) => onChange({ ...intent, location: { ...(loc ?? emptyLoc()), zipcode: e.target.value || null } })} />
            </div>
            <div style={{ flex: 1 }}>
              <label className="field-label">Radius (mi)</label>
              <input className="input" inputMode="numeric" value={loc?.radius_mi ?? ''} onChange={(e) => onChange({ ...intent, location: { ...(loc ?? emptyLoc()), radius_mi: numOrNull(e.target.value) } })} />
            </div>
          </div>
          <label className="row small"><input type="checkbox" checked={!!loc?.remote_ok} onChange={(e) => onChange({ ...intent, location: { ...(loc ?? emptyLoc()), remote_ok: e.target.checked } })} /> Remote OK</label>
          <label className="row small"><input type="checkbox" checked={!!loc?.required} onChange={(e) => onChange({ ...intent, location: { ...(loc ?? emptyLoc()), required: e.target.checked } })} /> Required — exclude candidates with a known location outside the radius (unknown locations stay in)</label>
          {loc && <button className="btn" onClick={() => onChange({ ...intent, location: null })}>Clear location</button>}
        </div>
      </Filter>

      <Filter label="Experience" value={yrsLabel} required={yrs?.required} disabled={disabled}>
        <div className="stack">
          <div className="row">
            <div style={{ flex: 1 }}>
              <label className="field-label">Min years</label>
              <input className="input" inputMode="numeric" value={yrs?.min ?? ''} onChange={(e) => onChange({ ...intent, years: { ...(yrs ?? emptyYears()), min: numOrNull(e.target.value) } })} />
            </div>
            <div style={{ flex: 1 }}>
              <label className="field-label">Max years</label>
              <input className="input" inputMode="numeric" value={yrs?.max ?? ''} onChange={(e) => onChange({ ...intent, years: { ...(yrs ?? emptyYears()), max: numOrNull(e.target.value) } })} />
            </div>
          </div>
          <label className="row small"><input type="checkbox" checked={!!yrs?.required} onChange={(e) => onChange({ ...intent, years: { ...(yrs ?? emptyYears()), required: e.target.checked } })} /> Required — exclude only when the profile shows fewer years (unknown stays in)</label>
        </div>
      </Filter>

      <Filter label="Skills" value={skillsLabel} disabled={disabled}>
        <div className="stack" style={{ minWidth: 360 }}>
          {skills.length === 0 && <div className="muted small">No skills yet — add one below.</div>}
          {skills.map((r) => (
            <div key={r.id} className="row between">
              <span>
                {r.text} <span className="faint small">· {r.source}</span>
                {r.aliases.length > 0 && <div className="faint small">also: {r.aliases.join(', ')}</div>}
              </span>
              <span className="row">
                <label className="row small"><input type="checkbox" checked={r.must_have} onChange={(e) => setReq(r.id, { must_have: e.target.checked })} /> Must-have</label>
                <button className="btn ghost" aria-label={`Remove ${r.text}`} onClick={() => removeReq(r.id)}>✕</button>
              </span>
            </div>
          ))}
          <div className="row">
            <input className="input" placeholder="Add a skill or keyword" value={newSkill} onChange={(e) => setNewSkill(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addReq()} />
            <button className="btn" onClick={addReq}>Add</button>
          </div>
        </div>
      </Filter>

      {auth.length > 0 && (
        <Filter label="Work authorization" value={auth.map((a) => a.text).join(', ')} disabled={disabled}>
          <div className="stack" style={{ minWidth: 320 }}>
            <div className="small muted">Included because the job states it. Unknown status is shown as unknown — confirm with the candidate.</div>
            {auth.map((r) => (
              <div key={r.id} className="row between">
                <span>{r.text}</span>
                <span className="row">
                  <label className="row small"><input type="checkbox" checked={r.must_have} onChange={(e) => setReq(r.id, { must_have: e.target.checked })} /> Must-have</label>
                  <button className="btn ghost" aria-label={`Remove ${r.text}`} onClick={() => removeReq(r.id)}>✕</button>
                </span>
              </div>
            ))}
          </div>
        </Filter>
      )}

      <button className="btn" onClick={onReset} disabled={disabled}>↺ Reset</button>
    </div>
  )
}

function emptyLoc(): NonNullable<SearchIntent['location']> {
  return { city: null, state: null, zipcode: null, radius_mi: DEFAULT_RADIUS_MI, remote_ok: null, required: false, source: 'query' }
}
function emptyYears(): NonNullable<SearchIntent['years']> {
  return { min: null, max: null, required: false, source: 'query' }
}
