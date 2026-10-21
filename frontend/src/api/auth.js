import { api } from './client.js'

export const getAuth = () => api('/api/auth')
// 039: a claude.ai login from the Settings page, its sign-in URL, then the pasted code.
// 056 Q3: with no id it is a new account; the answer's account_id names the account either way
export const startLogin = (accountId) =>
  api('/api/auth/login', { method: 'POST', body: accountId == null ? undefined : { account_id: accountId } })
// 056 Q5: account_id guards against a code meant for another account's login
export const sendLoginCode = (code, accountId) =>
  api('/api/auth/login/code', { method: 'POST', body: { code, account_id: accountId } })
// 056: every Claude login the app holds, each checked afresh; activate answers GET /api/auth's body, delete a 204
export const getAccounts = () => api('/api/auth/accounts')
export const activateAccount = (id) => api(`/api/auth/accounts/${id}/activate`, { method: 'POST' })
export const deleteAccount = (id) => api(`/api/auth/accounts/${id}`, { method: 'DELETE' })

/** 014 Q2: the plan capitalized, as the header badge words it; `subscription` when claude reports none. */
export const planName = (plan) => (plan ? plan[0].toUpperCase() + plan.slice(1).toLowerCase() : 'subscription')
