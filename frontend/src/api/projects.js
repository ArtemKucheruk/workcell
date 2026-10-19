import { api } from './client.js'

export const moveProject = (id, workspaceId) =>
  api(`/api/projects/${encodeURIComponent(id)}`, { method: 'PATCH', body: { workspace_id: workspaceId } })

export const createFactory = (id, overwrite) =>
  api(`/api/projects/${encodeURIComponent(id)}/factory`, { method: 'POST', body: { overwrite } })

/** 032: a task bundle, the File itself as the body. */
export const importBundle = (id, file) =>
  api(`/api/projects/${encodeURIComponent(id)}/import`, { method: 'POST', raw: file })

export const projectContext = (id) => api(`/api/projects/${encodeURIComponent(id)}/context`)

export const saveProjectContext = (id, contextMd) =>
  api(`/api/projects/${encodeURIComponent(id)}/context`, { method: 'PUT', body: { context_md: contextMd } })
