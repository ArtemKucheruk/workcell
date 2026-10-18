import { api } from './client.js'

export const createTask = (projectId, { title, description_md }) =>
  api(`/api/projects/${encodeURIComponent(projectId)}/tasks`, { method: 'POST', body: { title, description_md } })

export const moveTask = (id, status, position) =>
  api(`/api/tasks/${encodeURIComponent(id)}`, { method: 'PATCH', body: { status, position } })
