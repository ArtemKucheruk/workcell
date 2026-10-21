import { api } from './client.js'

/** 049: any of workspace_id, name, and test_cmd, sent as given; the reply is the project after the update. */
export const patchProject = (id, fields) =>
  api(`/api/projects/${encodeURIComponent(id)}`, { method: 'PATCH', body: fields })

export const deleteProject = (id) => api(`/api/projects/${encodeURIComponent(id)}`, { method: 'DELETE' })

export const createFactory = (id, overwrite) =>
  api(`/api/projects/${encodeURIComponent(id)}/factory`, { method: 'POST', body: { overwrite } })

/** 032: a task bundle, the File itself as the body. */
export const importBundle = (id, file) =>
  api(`/api/projects/${encodeURIComponent(id)}/import`, { method: 'POST', raw: file })

export const projectContext = (id) => api(`/api/projects/${encodeURIComponent(id)}/context`)

export const saveProjectContext = (id, contextMd) =>
  api(`/api/projects/${encodeURIComponent(id)}/context`, { method: 'PUT', body: { context_md: contextMd } })
