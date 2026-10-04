import { createContext } from 'react'
import type { SearchRunStore } from './searchRunStore'

export const StoreContext = createContext<SearchRunStore | null>(null)
