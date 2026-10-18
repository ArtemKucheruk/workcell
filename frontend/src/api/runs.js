import { api } from './client.js'

export const runTask = (id) => api(`/api/tasks/${encodeURIComponent(id)}/run`, { method: 'POST' })

export const runNext = (projectId) => api(`/api/projects/${encodeURIComponent(projectId)}/run-next`, { method: 'POST' })
