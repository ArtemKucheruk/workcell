import { api } from './client.js'

export const createTask = (projectId, { title, description_md }) =>
  api(`/api/projects/${encodeURIComponent(projectId)}/tasks`, { method: 'POST', body: { title, description_md } })

/** 032: the task bundle's download URL; transcripts only when asked. */
export const exportUrl = (id, transcripts) =>
  `/api/tasks/${encodeURIComponent(id)}/export${transcripts ? '?transcripts=1' : ''}`

export const moveTask = (id, status, position) =>
  api(`/api/tasks/${encodeURIComponent(id)}`, { method: 'PATCH', body: { status, position } })

/** 048: the board's Edit sends both fields, as typed. */
export const editTask = (id, { title, description_md }) =>
  api(`/api/tasks/${encodeURIComponent(id)}`, { method: 'PATCH', body: { title, description_md } })

/** 048: resolves to null on the 204. */
export const deleteTask = (id) => api(`/api/tasks/${encodeURIComponent(id)}`, { method: 'DELETE' })
