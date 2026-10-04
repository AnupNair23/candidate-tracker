import { useQuery } from '@tanstack/react-query'
import { NavLink, Outlet } from 'react-router-dom'
import { api } from '../api/client'
import { HEALTH_STALE_TIME_MS } from '../constants/api'
import { INERT_BOTTOM, INERT_MAIN } from '../constants/navigation'

export function Layout() {
  const health = useQuery({ queryKey: ['health'], queryFn: () => api.health(), staleTime: HEALTH_STALE_TIME_MS, retry: false })
  const modeNotes = [
    health.data?.jobdiva_mock && 'JobDiva mock data',
    health.data?.llm_mode === 'stub' && 'Stub assessor (not Claude)',
    health.data?.snapshot_replay && 'Snapshot replay',
  ].filter(Boolean)

  return (
    <div className="app">
      <aside className="sidebar" aria-label="Main navigation">
        <div className="brand">
          <span className="brand-mark">A</span> Asendia AI
        </div>
        <div className="side-search tooltip" data-tip="Coming soon">
          <span>Search</span>
          <span className="kbd">⌘F</span>
        </div>
        <div className="side-label">Main menu</div>
        {INERT_MAIN.map((label) => (
          <span key={label} className="side-link inert" title="Coming soon">
            {label}
          </span>
        ))}
        <NavLink to="/jobs" className={({ isActive }) => `side-link${isActive ? ' active' : ''}`}>
          Jobs
        </NavLink>
        <NavLink to="/candidates" className={({ isActive }) => `side-link${isActive ? ' active' : ''}`}>
          Candidates
        </NavLink>
        <div className="side-label">Folders · by client</div>
        <span className="side-link inert small">Coming soon</span>
        <div className="side-spacer" />
        {modeNotes.length > 0 && (
          <div className="alert warn small" style={{ marginBottom: 8 }}>
            Dev mode: {modeNotes.join(' · ')}
          </div>
        )}
        {INERT_BOTTOM.map((label) => (
          <span key={label} className="side-link inert" title="Coming soon">
            {label}
          </span>
        ))}
      </aside>
      <main className="main">
        <Outlet />
        <div className="footer-note">
          Recommendations are decision support based on job-related evidence. Missing information is shown as unknown,
          not as a lack of skill. The hiring manager makes the final decision.
        </div>
      </main>
    </div>
  )
}
