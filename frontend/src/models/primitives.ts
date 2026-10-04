import { z } from 'zod'

/** Shared zod primitives for API payloads. */
export const str = z.string()
export const optStr = z.string().nullable().optional()
export const optNum = z.number().nullable().optional()
