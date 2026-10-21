import { api } from './client.js'

export const getAuth = () => api('/api/auth')
// 039: a claude.ai login from the Settings page, its sign-in URL, then the pasted code
export const startLogin = () => api('/api/auth/login', { method: 'POST' })
export const sendLoginCode = (code) => api('/api/auth/login/code', { method: 'POST', body: { code } })
// 055: claude auth logout; answers GET /api/auth's body, checked afresh
export const logout = () => api('/api/auth/logout', { method: 'POST' })

/** 014 Q2: the plan capitalized, as the header badge words it; `subscription` when claude reports none. */
export const planName = (plan) => (plan ? plan[0].toUpperCase() + plan.slice(1).toLowerCase() : 'subscription')
