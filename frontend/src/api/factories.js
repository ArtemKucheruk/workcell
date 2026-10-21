import { api } from './client.js'

// 051, docs/data-model-and-api.md §6.1: named factory designs. `createFactory` in projects.js is Create factory's files.
const one = (id) => `/api/factories/${encodeURIComponent(id)}`
const ofProject = (projectId) => `/api/projects/${encodeURIComponent(projectId)}/factories`

export const listFactories = (projectId) => api(ofProject(projectId))

export const addFactory = (projectId, name) => api(ofProject(projectId), { method: 'POST', body: { name } })

export const getFactory = (id) => api(one(id))

/** `{name}`, `{graph}`, or both; the reply is the factory after the update. */
export const saveFactory = (id, fields) => api(one(id), { method: 'PUT', body: fields })

export const deleteFactory = (id) => api(one(id), { method: 'DELETE' })
