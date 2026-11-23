import { api } from './client.js'

// 104, docs/data-model-and-api.md §6.1: an automation's schedule. Each reply is a <Schedule>; DELETE's is empty.
const one = (id) => `/api/schedules/${encodeURIComponent(id)}`
const ofProject = (projectId) => `/api/projects/${encodeURIComponent(projectId)}/schedules`

export const listSchedules = (projectId) => api(ofProject(projectId))

/** No `accountId` (null) is Auto and sends no account_id. */
export const createSchedule = (projectId, factoryId, cron, accountId) =>
  api(ofProject(projectId), {
    method: 'POST',
    body: { factory_id: factoryId, cron, ...(accountId == null ? {} : { account_id: accountId }) },
  })

/** Any of `{cron, enabled, account_id}`; a null account_id is Auto. */
export const patchSchedule = (id, fields) => api(one(id), { method: 'PATCH', body: fields })

export const deleteSchedule = (id) => api(one(id), { method: 'DELETE' })
