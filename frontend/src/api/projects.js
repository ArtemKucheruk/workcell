import { api } from './client.js'

/**
 * 049: any of workspace_id, name, (119) path, test_cmd, (108) github_label, and (109) the plane_* settings, sent as
 * given; the reply is the project after the update, with plane_key_set but never the key.
 */
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

/** 058: `{}` syncs factory/board.json and factory/backlog.md onto the board; the reply has `imported` and `skipped`. */
export const syncFactory = (id) =>
  api(`/api/projects/${encodeURIComponent(id)}/import-factory`, { method: 'POST', body: {} })

/** 108 Q1, Q10: the repo's open issues (the saved label's) as Backlog tasks; the reply is `{new, updated, skipped}`. */
export const syncGithubIssues = (id) =>
  api(`/api/projects/${encodeURIComponent(id)}/github-issues/sync`, { method: 'POST', body: {} })

/** 109 AC19: the Plane project's backlog and unstarted work items as Backlog tasks; the reply is `{new, updated, skipped}`. */
export const syncPlane = (id) => api(`/api/projects/${encodeURIComponent(id)}/plane/sync`, { method: 'POST', body: {} })
