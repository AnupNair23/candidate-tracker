import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { EmptyState } from './components/EmptyState'
import { JobPage } from './features/job/JobPage'
import { JobsPage } from './features/jobs/JobsPage'

function CandidatesIndex() {
  return (
    <>
      <div className="crumbs">
        <strong>Candidates</strong>
      </div>
      <div className="content">
        <div className="card">
          <EmptyState title="Candidates are sourced per job">
            Open a job from the Jobs list to see the candidates already on it and to source new ones.
          </EmptyState>
        </div>
      </div>
    </>
  )
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Navigate to="/jobs" replace />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/jobs/:jobId" element={<JobPage />} />
        <Route path="/candidates" element={<CandidatesIndex />} />
        <Route path="*" element={<Navigate to="/jobs" replace />} />
      </Route>
    </Routes>
  )
}
