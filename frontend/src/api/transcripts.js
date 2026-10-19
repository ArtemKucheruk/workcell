import { api } from './client.js'

/** 030 Q9: `full` asks for every tool result uncut. */
export const transcript = (id, full) => api(`/api/transcripts/${encodeURIComponent(id)}${full ? '?full=1' : ''}`)

/** The copied .jsonl, served as an attachment. */
export const rawUrl = (id) => `/api/transcripts/${encodeURIComponent(id)}/raw`
