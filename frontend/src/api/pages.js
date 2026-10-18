import { api } from './client.js'

export const dashboardPage = (show) =>
  api(`/api/pages/dashboard${show ? `?${new URLSearchParams({ show })}` : ''}`)

export const workspacePage = (id) => api(`/api/pages/workspaces/${encodeURIComponent(id)}`)
