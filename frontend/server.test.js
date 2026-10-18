// @vitest-environment node
// Q1: server.js and a fake backend both run in this process on 127.0.0.1 port 0. No real backend, no network.
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import http from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { afterAll, beforeAll, beforeEach, expect, test } from 'vitest'
import { createServer } from './server.js'

const INDEX = '<!doctype html><div id="root"></div>'
const APP_JS = 'console.log("app")'
const SECRET = 'top secret'
let tmp, dist, backend, backendUrl, received

const listen = (server) =>
  new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server.address().port)))

/** A raw request: `path` goes out unnormalized, and `host: null` sends no Host header at all. */
function request(port, path, { method = 'GET', headers = {}, body, host } = {}) {
  return new Promise((resolve, reject) => {
    const options = { host: '127.0.0.1', port, path, method, headers: { ...headers } }
    if (host === null) options.setHost = false
    else if (host) options.headers.host = host
    const req = http.request(options, (res) => {
      const chunks = []
      res.on('data', (c) => chunks.push(c))
      res.on('end', () => resolve({ status: res.statusCode, headers: res.headers, body: Buffer.concat(chunks).toString() }))
    })
    req.on('error', reject)
    req.end(body)
  })
}

async function frontend(apiUrl = backendUrl) {
  const server = createServer(dist, apiUrl)
  const port = await listen(server)
  return { port, close: () => new Promise((r) => server.close(r)) }
}

beforeAll(async () => {
  tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'fctl-frontend-'))
  dist = path.join(tmp, 'dist')
  fs.mkdirSync(path.join(dist, 'assets'), { recursive: true })
  fs.writeFileSync(path.join(dist, 'index.html'), INDEX)
  fs.writeFileSync(path.join(dist, 'assets', 'app.js'), APP_JS)
  fs.writeFileSync(path.join(tmp, 'secret.txt'), SECRET)
  fs.symlinkSync('../secret.txt', path.join(dist, 'link.txt'))
  backend = http.createServer((req, res) => {
    const chunks = []
    req.on('data', (c) => chunks.push(c))
    req.on('end', () => {
      received.push({ method: req.method, url: req.url, headers: req.headers, body: Buffer.concat(chunks).toString() })
      res.writeHead(409, { 'Content-Type': 'application/json' })
      res.end('{"detail":"run #41 active"}')
    })
  })
  backendUrl = `http://127.0.0.1:${await listen(backend)}`
})

afterAll(() => {
  backend.close()
  fs.rmSync(tmp, { recursive: true, force: true })
})

beforeEach(() => {
  received = []
})

test('AC1: run as main with PORT=0 and no HOST, it listens on 127.0.0.1 and prints its URL', async () => {
  // a copy beside its own dist/, which also shows it resolves dist/ next to itself
  fs.copyFileSync(new URL('./server.js', import.meta.url), path.join(tmp, 'server.js'))
  const { HOST, ...env } = process.env
  const child = spawn(process.execPath, [path.join(tmp, 'server.js')], {
    cwd: os.tmpdir(),
    env: { ...env, PORT: '0', FCTL_API_URL: backendUrl },
  })
  try {
    const line = await new Promise((resolve, reject) => {
      child.stdout.once('data', (d) => resolve(d.toString()))
      child.once('exit', (code) => reject(new Error(`exited ${code}`)))
    })
    expect(line.trim().split('\n')).toHaveLength(1)
    const port = Number(line.match(/http:\/\/127\.0\.0\.1:(\d+)/)[1])
    expect(line).toContain(`→ ${backendUrl}`)
    const res = await request(port, '/')
    expect([res.status, res.body]).toEqual([200, INDEX])
  } finally {
    child.kill()
  }
})

test('AC2: / and a deep link get dist/index.html as text/html', async () => {
  const { port, close } = await frontend()
  for (const url of ['/', '/workspaces/2']) {
    const res = await request(port, url)
    expect(res.status).toBe(200)
    expect(res.headers['content-type']).toMatch(/^text\/html/)
    expect(res.body).toBe(INDEX)
  }
  await close()
})

test('AC3: a file in dist/ comes back with its bytes and a JavaScript type', async () => {
  const { port, close } = await frontend()
  const res = await request(port, '/assets/app.js')
  expect(res.status).toBe(200)
  expect(res.headers['content-type']).toMatch(/^text\/javascript/)
  expect(res.body).toBe(APP_JS)
  await close()
})

test('AC4: traversal, encoded traversal, NUL, and an outward symlink all get index.html', async () => {
  const { port, close } = await frontend()
  for (const url of ['/../secret.txt', '/%2e%2e/secret.txt', '/assets/..%2f..%2fsecret.txt', '/%00', '/link.txt']) {
    const res = await request(port, url)
    expect(res.body).not.toContain(SECRET)
    expect([url, res.status, res.body]).toEqual([url, 200, INDEX])
  }
  expect((await request(port, '/assets/app.js')).body).toBe(APP_JS)
  await close()
})

test('AC5: a foreign or missing Host is 403 for pages and the API, and never reaches the backend', async () => {
  const { port, close } = await frontend()
  for (const host of ['evil.example', '127.0.0.1.evil.example', null]) {
    for (const url of ['/', '/api/workspaces']) {
      const res = await request(port, url, { host })
      expect([host, url, res.status, JSON.parse(res.body)]).toEqual(
        [host, url, 403, { detail: 'Host must be 127.0.0.1 or localhost' }],
      )
    }
  }
  expect(received).toEqual([])
  for (const host of ['localhost:3000', '127.0.0.1:3000']) {
    expect((await request(port, '/', { host })).status).toBe(200)
  }
  await close()
})

test('AC6: /api/* reaches the backend as sent, with Host 127.0.0.1, and its answer comes back unchanged', async () => {
  const { port, close } = await frontend()
  const body = '{"name":"work"}'
  const res = await request(port, '/api/workspaces?x=1', {
    method: 'POST',
    host: 'localhost:3000',
    headers: { 'Content-Type': 'application/json', 'X-Requested-By': 'fctl' },
    body,
  })
  expect(received).toHaveLength(1)
  const [got] = received
  expect([got.method, got.url, got.body]).toEqual(['POST', '/api/workspaces?x=1', body])
  expect(got.headers['x-requested-by']).toBe('fctl')
  expect(got.headers.host).toBe('127.0.0.1')
  expect(res.status).toBe(409)
  expect(res.headers['content-type']).toBe('application/json')
  expect(res.body).toBe('{"detail":"run #41 active"}')
  await close()
})

test('AC7: without X-Requested-By, the proxied request has none', async () => {
  const { port, close } = await frontend()
  await request(port, '/api/workspaces', { method: 'POST', body: '{}' })
  expect(received).toHaveLength(1)
  expect(received[0].headers).not.toHaveProperty('x-requested-by')
  await close()
})

test('AC8: a backend on a closed port is a 502 naming FCTL_API_URL, and the server keeps answering', async () => {
  const closed = http.createServer()
  const deadPort = await listen(closed)
  await new Promise((r) => closed.close(r))
  const deadUrl = `http://127.0.0.1:${deadPort}`
  const { port, close } = await frontend(deadUrl)
  const res = await request(port, '/api/auth')
  expect(res.status).toBe(502)
  expect(JSON.parse(res.body)).toEqual({ detail: `Backend unreachable at ${deadUrl}` })
  expect((await request(port, '/')).status).toBe(200)
  expect((await request(port, '/api/auth')).status).toBe(502)
  await close()
})
