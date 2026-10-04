import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.tsx'
import { QUERY_STALE_TIME_MS } from './constants/api'
import { SearchRunsProvider } from './state/SearchRunsProvider'
import './styles/index.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: QUERY_STALE_TIME_MS } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <SearchRunsProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </SearchRunsProvider>
    </QueryClientProvider>
  </StrictMode>,
)
