import { api } from './client.js'

export const createTask = (projectId, { title, description_md }) =>
  api(`/api/projects/${encodeURIComponent(projectId)}/tasks`, { method: 'POST', body: { title, description_md } })

/** 032: the task bundle's download URL; transcripts only when asked. */
export const exportUrl = (id, transcripts) =>
  `/api/tasks/${encodeURIComponent(id)}/export${transcripts ? '?transcripts=1' : ''}`

export const moveTask = (id, status, position) =>
  api(`/api/tasks/${encodeURIComponent(id)}`, { method: 'PATCH', body: { status, position } })
