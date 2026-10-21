import { expect, test, vi } from 'vitest'
import { api } from './client.js'

function ok(body) {
  const fetch = vi.fn(async () => new Response(JSON.stringify(body), { status: 200 }))
  vi.stubGlobal('fetch', fetch)
  return fetch
}

test('AC10: mutating methods send X-Requested-By and JSON; GET sends no X-Requested-By', async () => {
  for (const method of ['POST', 'PATCH', 'PUT', 'DELETE']) {
    const fetch = ok({ id: 1 })
    expect(await api('/api/x', { method, body: { name: 'work' } })).toEqual({ id: 1 })
    const [url, init] = fetch.mock.calls[0]
    expect([url, init.method, init.body]).toEqual(['/api/x', method, '{"name":"work"}'])
    expect(init.headers).toEqual({ 'X-Requested-By': 'fctl', 'Content-Type': 'application/json' })
  }
  const fetch = ok([1, 2])
  expect(await api('/api/y')).toEqual([1, 2])
  expect(fetch.mock.calls[0][1].headers).not.toHaveProperty('X-Requested-By')
})

test('AC11: errors carry the detail as message and the status', async () => {
  const fail = (status, body) =>
    vi.stubGlobal('fetch', vi.fn(async () => new Response(body, { status })))
  fail(409, '{"detail":"run #41 active"}')
  const error = await api('/api/x', { method: 'POST' }).catch((e) => e)
  expect(error).toBeInstanceOf(Error)
  expect([error.message, error.status]).toEqual(['run #41 active', 409])

  fail(422, JSON.stringify({ detail: [{ loc: ['body', 'name'], msg: 'Field required' }, { msg: 'too short' }] }))
  await expect(api('/api/x', { method: 'POST' })).rejects.toThrow(/^name: Field required; too short$/)

  fail(500, 'Internal Server Error')
  const plain = await api('/api/x').catch((e) => e)
  expect([plain.message, plain.status]).toEqual(['HTTP 500', 500])
})

test('032 AC47: raw sends a Blob or File unchanged, with X-Requested-By and no JSON Content-Type', async () => {
  const fetch = ok({ task_id: 12 })
  const file = new File(['PK'], 'task-12.zip', { type: 'application/zip' })
  expect(await api('/api/projects/3/import', { method: 'POST', raw: file })).toEqual({ task_id: 12 })
  const [url, init] = fetch.mock.calls[0]
  expect([url, init.method, init.body]).toEqual(['/api/projects/3/import', 'POST', file])
  expect(init.headers).toEqual({ 'X-Requested-By': 'fctl' })
})

test('051 round-1 review-ux: a 422 list item names where it points, without body, query, path, or the graph wrapper', async () => {
  const detail = [
    { loc: ['body', 'graph', 'nodes', 1, 'rounds_below', 'data', 'n'], msg: 'Input should be a valid integer' },
    { loc: ['body', 'graph'], msg: 'Input should be a valid dictionary' },
    { loc: ['path', 'id'], msg: 'Input should be a valid integer' },
    { loc: ['query', 'round'], msg: 'Field required' },
    { loc: ['body'], msg: 'JSON decode error' },
  ]
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail }), { status: 422 })))
  const error = await api('/api/factories/1', { method: 'PUT', body: {} }).catch((e) => e)
  expect(error.message.split('; ')).toEqual([
    'nodes.1.rounds_below.data.n: Input should be a valid integer',
    'graph: Input should be a valid dictionary',
    'id: Input should be a valid integer',
    'round: Field required',
    'JSON decode error',
  ])
})
