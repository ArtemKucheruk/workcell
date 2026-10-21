// docs/MVP.md §4.5: mutating requests carry X-Requested-By, which the frontend server passes through.
const MUTATING = new Set(['POST', 'PATCH', 'PUT', 'DELETE'])

/**
 * 051 round-1 review-ux: where a 422 item points, as `nodes.1.rounds_below.data.n: `. The request part (`body`, `query`,
 * `path`) goes, and so does the designer's `graph` wrapper when something follows it; nothing is left for a whole body.
 */
function where(loc = []) {
  const path = loc.slice(['body', 'query', 'path'].includes(loc[0]) ? 1 : 0)
  if (path[0] === 'graph' && path.length > 1) path.shift()
  return path.length ? `${path.join('.')}: ` : ''
}

/** Q4: the error's message from the API's `detail`: a string, or FastAPI's 422 list of `{loc, msg}`. */
function message(body, status) {
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map((d) => `${where(d.loc)}${d.msg}`).join('; ')
  return `HTTP ${status}`
}

/**
 * fetch `path`, sending `body` as JSON, or `raw` (a Blob or File, 032) unchanged so the browser sets its type.
 * Resolves to the reply's JSON; rejects with an Error carrying `status` on a non-2xx.
 */
export async function api(path, { method = 'GET', body, raw } = {}) {
  const json = raw === undefined && { 'Content-Type': 'application/json' }
  const headers = MUTATING.has(method) ? { 'X-Requested-By': 'fctl', ...json } : {}
  const sent = raw ?? (body === undefined ? undefined : JSON.stringify(body))
  const res = await fetch(path, { method, headers, body: sent })
  const data = await res.json().catch(() => null)
  if (!res.ok) throw Object.assign(new Error(message(data, res.status)), { status: res.status })
  return data
}
