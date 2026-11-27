import { api } from './client.js'

/** 097 AC29: `{account_id}` only when an account was chosen; none is Auto. */
export const runTask = (id, accountId) =>
  api(`/api/tasks/${encodeURIComponent(id)}/run`, {
    method: 'POST',
    ...(accountId == null ? {} : { body: { account_id: accountId } }),
  })

/** 113 AC11: `{module_id}` only when a module was given; none is the whole project's Backlog. */
export const runNext = (projectId, moduleId) =>
  api(`/api/projects/${encodeURIComponent(projectId)}/run-next`, {
    method: 'POST',
    ...(moduleId == null ? {} : { body: { module_id: moduleId } }),
  })

export const stopRun = (id) => api(`/api/runs/${encodeURIComponent(id)}/stop`, { method: 'POST' })

export const runLog = (id, after) => api(`/api/runs/${encodeURIComponent(id)}/log?${new URLSearchParams({ after })}`)
