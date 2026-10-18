// docs/MVP.md §4.1, §4.5: serves the built SPA from dist/ and proxies /api/* to the backend. node:http only.
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ALLOWED_HOSTS = new Set(['127.0.0.1', 'localhost'])
const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.json': 'application/json',
  '.woff2': 'font/woff2',
  '.map': 'application/json',
}

function json(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json' })
  res.end(JSON.stringify(body))
}

/** The file under `root` that `url` names, or null. Realpath, so `..` and symlinks can't leave `root`. */
function resolve(root, url) {
  try {
    const file = fs.realpathSync(path.join(root, decodeURIComponent(new URL(url, 'http://x').pathname)))
    return file.startsWith(root + path.sep) && fs.statSync(file).isFile() ? file : null
  } catch {
    return null // Q2: malformed escapes, NUL bytes, and missing files all get index.html
  }
}

function serve(req, res, root) {
  const file = resolve(root, req.url) ?? path.join(root, 'index.html')
  fs.readFile(file, (err, body) => {
    if (err) return json(res, 404, { detail: 'Not Found' })
    res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] ?? 'application/octet-stream' })
    res.end(body)
  })
}

function proxy(req, res, api, apiUrl) {
  // §4.5: the browser's headers, X-Requested-By included, pass through as is; only Host changes
  const upstream = http.request(
    { host: api.hostname, port: api.port, method: req.method, path: req.url, headers: { ...req.headers, host: '127.0.0.1' } },
    (up) => {
      res.writeHead(up.statusCode, up.headers)
      up.pipe(res)
    },
  )
  upstream.on('error', () => {
    if (res.headersSent) return res.destroy()
    json(res, 502, { detail: `Backend unreachable at ${apiUrl}` })
  })
  req.on('error', () => upstream.destroy())
  req.pipe(upstream)
}

export function createServer(dist, apiUrl) {
  const root = fs.realpathSync(dist)
  const api = new URL(apiUrl)
  // requireHostHeader off, so a request with no Host gets our 403 rather than Node's 400
  return http.createServer({ requireHostHeader: false }, (req, res) => {
    const hostname = (req.headers.host ?? '').split(':')[0].toLowerCase()
    if (!ALLOWED_HOSTS.has(hostname)) return json(res, 403, { detail: 'Host must be 127.0.0.1 or localhost' })
    const pathname = req.url.split('?')[0]
    if (pathname === '/api' || pathname.startsWith('/api/')) return proxy(req, res, api, apiUrl)
    serve(req, res, root)
  })
}

// realpath: Node resolves symlinks (macOS /var → /private/var) in import.meta.url but not in argv
if (process.argv[1] && fs.realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const host = process.env.HOST || '127.0.0.1'
  const port = Number(process.env.PORT || 3000)
  const apiUrl = process.env.FCTL_API_URL || 'http://127.0.0.1:4545'
  const dist = path.join(path.dirname(fileURLToPath(import.meta.url)), 'dist')
  if (!fs.existsSync(path.join(dist, 'index.html'))) {
    console.error(`No build at ${dist}. Run: npm --prefix frontend run build`)
    process.exit(1)
  }
  const server = createServer(dist, apiUrl)
  server.listen(port, host, () => {
    console.log(`Claude Factories frontend on http://${host}:${server.address().port} → ${apiUrl}`)
  })
}
