import { useContext, useSyncExternalStore } from 'react'
import type { SearchRun } from '../models'
import { StoreContext } from '../state/searchRunsContext'
import type { SearchRunStore } from '../state/searchRunStore'

export function useSearchStore(): SearchRunStore {
  const store = useContext(StoreContext)
  if (!store) throw new Error('SearchRunsProvider missing')
  return store
}

export function useSearchRun(jobId: string): SearchRun | undefined {
  const store = useSearchStore()
  return useSyncExternalStore(store.subscribe, () => store.get(jobId))
}
