export function Stars({ value, label }: { value: number; label?: string }) {
  const v = Math.max(0, Math.min(5, Math.round(value)))
  return (
    <span className="stars" aria-label={label ?? `${v} of 5`} title={label}>
      {'★'.repeat(v)}
      <span className="off">{'★'.repeat(5 - v)}</span>
    </span>
  )
}
