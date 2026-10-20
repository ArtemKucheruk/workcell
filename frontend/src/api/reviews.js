import { api } from './client.js'

// The backend's controllers/reviews.py: my comments, Approve, and Request changes.
const task = (id, action) => `/api/tasks/${encodeURIComponent(id)}/${action}`

export const addComment = (id, body) => api(task(id, 'comments'), { method: 'POST', body })

/** 047 Q4: the web UI's summary goes with Approve too, blank as ""; `fctl approve` still sends none (009 Q12). */
export const approveTask = (id, body_md = '') => api(task(id, 'approve'), { method: 'POST', body: { body_md } })

export const requestChanges = (id, body_md) => api(task(id, 'request-changes'), { method: 'POST', body: { body_md } })
