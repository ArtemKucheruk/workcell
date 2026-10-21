import { api } from './client.js'

export const createWorkspace = (name) => api('/api/workspaces', { method: 'POST', body: { name } })

export const renameWorkspace = (id, name) =>
  api(`/api/workspaces/${encodeURIComponent(id)}`, { method: 'PATCH', body: { name } })

export const deleteWorkspace = (id) => api(`/api/workspaces/${encodeURIComponent(id)}`, { method: 'DELETE' })
