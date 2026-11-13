import { api } from './client.js'

/** 095 AC14, AC27: each account's latest limits, plus the token and run stats over the last `days` (7 or 30). */
export const usagePage = (days) => api(`/api/usage?${new URLSearchParams({ days })}`)
