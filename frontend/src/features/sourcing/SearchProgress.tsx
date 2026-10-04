import { useEffect, useState } from 'react'
import { STEPS } from '../../constants/search'
import type { SearchRun } from '../../models'

export function SearchProgress({ run }: { run: SearchRun }) {
  const currentIndex = STEPS.findIndex((s) => s.stage === run.stage)
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [])
  const elapsed = Math.max(0, Math.round((now - run.startedAt) / 1000))
  return (
    <div className="card" role="status" aria-live="polite">
      <div className="card-head">
        <strong>Searching…</strong>
        <span className="faint small">{elapsed}s</span>
      </div>
      <div className="card-body progress-steps">
        {STEPS.map((step, i) => {
          const state = i < currentIndex || (currentIndex === -1 && run.stagesSeen.includes(step.stage)) ? 'done' : i === currentIndex ? 'active' : ''
          return (
            <div key={step.stage} className={`step ${state}`}>
              <span className="dot" />
              <span>
                {step.label}
                {i === currentIndex && run.progress?.total ? ` (${run.progress.done}/${run.progress.total})` : ''}
                {i === currentIndex && run.message && step.stage === 'retrieve' ? <span className="faint"> — {run.message}</span> : null}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
