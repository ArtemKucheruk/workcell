import { api } from './client.js'

// The backend's controllers/reviews.py: my comments, Approve, and Request changes.
const task = (id, action) => `/api/tasks/${encodeURIComponent(id)}/${action}`

export const addComment = (id, body) => api(task(id, 'comments'), { method: 'POST', body })

/** 024 Q8: no summary on Approve, as `fctl approve` (009 Q12). */
export const approveTask = (id) => api(task(id, 'approve'), { method: 'POST', body: { body_md: '' } })

export const requestChanges = (id, body_md) => api(task(id, 'request-changes'), { method: 'POST', body: { body_md } })
