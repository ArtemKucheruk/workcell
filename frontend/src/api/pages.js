import { api } from './client.js'

export const dashboardPage = (show) =>
  api(`/api/pages/dashboard${show ? `?${new URLSearchParams({ show })}` : ''}`)

export const workspacePage = (id) => api(`/api/pages/workspaces/${encodeURIComponent(id)}`)

export const boardPage = (id) => api(`/api/pages/projects/${encodeURIComponent(id)}`)

export const taskPage = (id) => api(`/api/pages/tasks/${encodeURIComponent(id)}`)
