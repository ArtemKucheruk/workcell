import { api } from './client.js'

export const runTask = (id) => api(`/api/tasks/${encodeURIComponent(id)}/run`, { method: 'POST' })

export const runNext = (projectId) => api(`/api/projects/${encodeURIComponent(projectId)}/run-next`, { method: 'POST' })

export const stopRun = (id) => api(`/api/runs/${encodeURIComponent(id)}/stop`, { method: 'POST' })

export const runLog = (id, after) => api(`/api/runs/${encodeURIComponent(id)}/log?${new URLSearchParams({ after })}`)
