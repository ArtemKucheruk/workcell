import { api } from './client.js'

export const dashboardPage = (show) =>
  api(`/api/pages/dashboard${show ? `?${new URLSearchParams({ show })}` : ''}`)

export const workspacePage = (id) => api(`/api/pages/workspaces/${encodeURIComponent(id)}`)

export const boardPage = (id) => api(`/api/pages/projects/${encodeURIComponent(id)}`)

export const taskPage = (id) => api(`/api/pages/tasks/${encodeURIComponent(id)}`)

/** 024 Q2: `?round=` only when the URL has one; without it the backend picks the latest round. */
export const reviewPage = (id, round) =>
  api(`/api/pages/tasks/${encodeURIComponent(id)}/review${round ? `?${new URLSearchParams({ round })}` : ''}`)

/**
 * 025 Q2: `?path=` only when the URL has one; without it the backend shows the README landing.
 * 054: then `?branch=`, also only when non-empty; without it the backend shows the working tree.
 */
export const codePage = (id, path, branch) => {
  const query = String(new URLSearchParams(Object.entries({ path, branch }).filter(([, value]) => value)))
  return api(`/api/pages/projects/${encodeURIComponent(id)}/code${query ? `?${query}` : ''}`)
}

/** 029: the fctl reference, pre-rendered with heading ids, and its headings for the Contents nav. */
export const fctlDoc = () => api('/api/docs/fctl')

/** 041 Q3: `?task=` or `?transcript=` only when the route has an all-digit id; otherwise no query. */
export const sidebarPage = (query) => api(`/api/pages/sidebar${query ? `?${new URLSearchParams(query)}` : ''}`)

/** 053: every running run with its agents, and the last 20 ended runs. */
export const agentsPage = () => api('/api/pages/agents')
