import type { SkillMatch } from '../models'

/** Matched = green; partial / unknown / unverified / not-met = grey with a clear label. */
export function SkillChip({ m }: { m: SkillMatch }) {
  const title = m.evidence[0]?.quote
  switch (m.status) {
    case 'met':
      return <span className="chip green" title={title}>{m.label}</span>
    case 'partial':
      return <span className="chip" title={title}>{m.label} (partial)</span>
    case 'not_met':
      return <span className="chip red" title={title}>{m.label}: contradicted</span>
    case 'unverified':
      return <span className="chip" title="Claimed by the model but not supported by the cited evidence">{m.label}: unverified</span>
    default:
      return <span className="chip" title="Not found in JobDiva records — unknown, not ruled out">No {m.label} on file</span>
  }
}
