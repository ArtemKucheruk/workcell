import { api } from './client.js'

export const createWorkspace = (name) => api('/api/workspaces', { method: 'POST', body: { name } })
