// docs/MVP.md §4.5: mutating requests carry X-Requested-By, which the frontend server passes through.
const MUTATING = new Set(['POST', 'PATCH', 'PUT', 'DELETE'])

/** Q4: the error's message from the API's `detail`: a string, or FastAPI's 422 list of `{msg}`. */
function message(body, status) {
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join('; ')
  return `HTTP ${status}`
}

/** fetch `path` as JSON. Rejects with an Error carrying `status` on a non-2xx. */
export async function api(path, { method = 'GET', body } = {}) {
  const headers = MUTATING.has(method) ? { 'X-Requested-By': 'fctl', 'Content-Type': 'application/json' } : {}
  const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) })
  const data = await res.json().catch(() => null)
  if (!res.ok) throw Object.assign(new Error(message(data, res.status)), { status: res.status })
  return data
}
