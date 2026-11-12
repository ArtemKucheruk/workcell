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

const blockedBy = (id, blocker) => `/api/tasks/${encodeURIComponent(id)}/blocked-by/${encodeURIComponent(blocker)}`

/** 094: task `id` waits on task `blocker` from now on; resolves to <Deps>. */
export const blockTask = (id, blocker) => api(blockedBy(id, blocker), { method: 'PUT' })

/** 094: task `id` stops waiting on task `blocker`; resolves to <Deps>. */
export const unblockTask = (id, blocker) => api(blockedBy(id, blocker), { method: 'DELETE' })
