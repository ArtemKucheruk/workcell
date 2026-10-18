import { api } from './client.js'

export const dashboardPage = (show) =>
  api(`/api/pages/dashboard${show ? `?${new URLSearchParams({ show })}` : ''}`)

export const workspacePage = (id) => api(`/api/pages/workspaces/${encodeURIComponent(id)}`)

export const boardPage = (id) => api(`/api/pages/projects/${encodeURIComponent(id)}`)

export const taskPage = (id) => api(`/api/pages/tasks/${encodeURIComponent(id)}`)

/** 024 Q2: `?round=` only when the URL has one; without it the backend picks the latest round. */
export const reviewPage = (id, round) =>
  api(`/api/pages/tasks/${encodeURIComponent(id)}/review${round ? `?${new URLSearchParams({ round })}` : ''}`)
