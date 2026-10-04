export function locationLine(parts: { city?: string | null; state?: string | null; distance_mi?: number | null; years?: number | null }) {
  const bits = [
    [parts.city, parts.state].filter(Boolean).join(', '),
    parts.distance_mi != null ? `${Math.round(parts.distance_mi)} mi` : null,
    parts.years != null ? `${parts.years % 1 === 0 ? parts.years : parts.years.toFixed(1)} yrs` : null,
  ].filter(Boolean)
  return bits.join(' · ')
}

export function formatDate(value?: string | null) {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString(undefined, { month: 'short', year: 'numeric' })
}
