import { api } from './client.js'

// 051, docs/data-model-and-api.md §6.1: named factory designs. `createFactory` in projects.js is Create factory's files.
const one = (id) => `/api/factories/${encodeURIComponent(id)}`
const ofProject = (projectId) => `/api/projects/${encodeURIComponent(projectId)}/factories`

export const listFactories = (projectId) => api(ofProject(projectId))

/** 088: `template` is a key from listTemplates; null means Standard. */
export const addFactory = (projectId, name, template) =>
  api(ofProject(projectId), { method: 'POST', body: { name, template } })

/** 088: + New factory's templates, `[{key, name, description}]`, Standard first. */
export const listTemplates = () => api('/api/factory-templates')

export const getFactory = (id) => api(one(id))

/** `{name}`, `{graph}`, or both; the reply is the factory after the update. */
export const saveFactory = (id, fields) => api(one(id), { method: 'PUT', body: fields })

export const deleteFactory = (id) => api(one(id), { method: 'DELETE' })

// 052: the stored graph compiled into Claude Code files; the designer's unsaved state never goes
export const factoryFiles = (id) => api(`${one(id)}/files`)

/** A plain <a download> target: the browser fetches it, so a refusal is its JSON detail, not a zip. */
export const downloadUrl = (id) => `${one(id)}/download`

/** The reply is Create factory's `{written, skipped, commit_hint}`. */
export const writeFactory = (id, overwrite) => api(`${one(id)}/write`, { method: 'POST', body: { overwrite } })
