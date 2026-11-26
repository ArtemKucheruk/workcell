import { api } from './client.js'

// 112, docs/data-model-and-api.md §6.1: a project's modules, its units of work
const one = (id) => `/api/modules/${encodeURIComponent(id)}`

/** Resolves to `{modules: [{id, name, description_md, counts}], no_module: counts}`, modules by name. */
export const listModules = (projectId) => api(`/api/projects/${encodeURIComponent(projectId)}/modules`)

export const addModule = (projectId, { name, description_md }) =>
  api(`/api/projects/${encodeURIComponent(projectId)}/modules`, { method: 'POST', body: { name, description_md } })

/** `{name}`, `{description_md}`, or both; resolves to the module after the update. */
export const saveModule = (id, fields) => api(one(id), { method: 'PATCH', body: fields })

/** Its tasks stay, with no module; resolves to null on the 204. */
export const deleteModule = (id) => api(one(id), { method: 'DELETE' })
