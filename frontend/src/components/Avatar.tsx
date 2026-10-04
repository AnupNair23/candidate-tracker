import { INK, PALETTE } from '../constants/avatar'

export function Avatar({ name, id }: { name: string; id: string }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join('')
  const i = [...id].reduce((a, c) => a + c.charCodeAt(0), 0) % PALETTE.length
  return (
    <span className="avatar" style={{ background: PALETTE[i], color: INK[i] }} aria-hidden>
      {initials || '?'}
    </span>
  )
}
