import { useEffect, useState } from 'react'

/** Counts down from `seconds`, restarting whenever `resetKey` changes. */
export function useCountdown(seconds: number, resetKey: unknown): number {
  const [state, setState] = useState({ key: resetKey, remaining: seconds })
  if (state.key !== resetKey) setState({ key: resetKey, remaining: seconds }) // reset during render, not in an effect
  useEffect(() => {
    if (state.remaining <= 0) return
    const id = window.setTimeout(() => setState((s) => ({ ...s, remaining: s.remaining - 1 })), 1000)
    return () => window.clearTimeout(id)
  }, [state])
  return state.key === resetKey ? state.remaining : seconds
}
