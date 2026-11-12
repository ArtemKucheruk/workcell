import { api } from './client.js'

// 096 Q2: the app's settings; max_concurrent_runs caps the runs going at once, across all projects
export const getSettings = () => api('/api/settings')
export const putSettings = (body) => api('/api/settings', { method: 'PUT', body })
