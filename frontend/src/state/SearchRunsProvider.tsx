import { useMemo, type ReactNode } from 'react'
import { StoreContext } from './searchRunsContext'
import { SearchRunStore } from './searchRunStore'

export function SearchRunsProvider({ children, store }: { children: ReactNode; store?: SearchRunStore }) {
  const value = useMemo(() => store ?? new SearchRunStore(), [store])
  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>
}
