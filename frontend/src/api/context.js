import { api } from './client.js'

// 057, docs/data-model-and-api.md §6.1: the Context page's cards and groups. The pinned card stays in projects.js.
const ofProject = (projectId) => `/api/projects/${encodeURIComponent(projectId)}/context/items`
const one = (id) => `/api/context/items/${encodeURIComponent(id)}`

export const contextItems = (projectId) => api(ofProject(projectId))

/** `{kind, title, description, content_md, parent_id}`, each as given; the reply is the new card or group. */
export const createContextItem = (projectId, fields) => api(ofProject(projectId), { method: 'POST', body: fields })

/** Any of title, description, content_md, parent_id, and position; the reply is the item after the update. */
export const patchContextItem = (id, fields) => api(one(id), { method: 'PATCH', body: fields })

export const deleteContextItem = (id) => api(one(id), { method: 'DELETE' })

/** 032's raw body: the File itself; `parent_id` only inside a group. */
export const uploadContextItem = (projectId, file, parentId) => {
  const query = new URLSearchParams({ name: file.name })
  if (parentId != null) query.set('parent_id', parentId)
  return api(`${ofProject(projectId)}/upload?${query}`, { method: 'POST', raw: file })
}

/** A path on the backend's machine; the reply is every row it made, a folder's group first. */
export const contextFromPath = (projectId, path, parentId) =>
  api(`${ofProject(projectId)}/from-path`, { method: 'POST', body: parentId == null ? { path } : { path, parent_id: parentId } })

export const reloadContextItem = (id) => api(`${one(id)}/reload`, { method: 'POST' })
