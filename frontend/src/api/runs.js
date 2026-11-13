import { api } from './client.js'

/** 097 AC29: `{account_id}` only when an account was chosen; none is Auto. */
export const runTask = (id, accountId) =>
  api(`/api/tasks/${encodeURIComponent(id)}/run`, {
    method: 'POST',
    ...(accountId == null ? {} : { body: { account_id: accountId } }),
  })

export const runNext = (projectId) => api(`/api/projects/${encodeURIComponent(projectId)}/run-next`, { method: 'POST' })

export const stopRun = (id) => api(`/api/runs/${encodeURIComponent(id)}/stop`, { method: 'POST' })

export const runLog = (id, after) => api(`/api/runs/${encodeURIComponent(id)}/log?${new URLSearchParams({ after })}`)
