import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { fetched, mockFetch, renderAt } from '../../test/render.jsx'

const PROJECT = {
  id: 3, name: 'api', path: '/Users/me/api', default_branch: 'main', workspace_id: 2, workspace: 'personal',
  remote_url: null, test_cmd: 'pytest -q',
}
const BOARD = '/api/pages/projects/3'
const CONTEXT = '/api/projects/3/context'
const board = (project = PROJECT) => ({
  project, factory: 'ready', hint: null, can_run: true, workspaces: [{ id: 2, name: 'personal', projects: 1 }],
  columns: { backlog: [], in_progress: [], review: [], done: [] },
})
/** GET or PUT /api/projects/{id}/context's body; `bytes` counts `context_md` unless given. */
const context = (context_md, extra = {}) => ({
  context_md, context_html: '', bytes: new TextEncoder().encode(context_md).length, max_bytes: 16384, ...extra,
})

afterEach(() => {
  vi.useRealTimers()
})

/** Renders /projects/3/context with the board view-model and `ctx` as GET's reply; waits for the textarea. */
async function open(ctx, more = {}) {
  const responses = { [`GET ${BOARD}`]: [200, board()], [`GET ${CONTEXT}`]: ctx, ...more }
  const fetch = mockFetch(responses)
  const view = renderAt('/projects/3/context')
  await screen.findByRole('textbox', { name: 'Project context' })
  return { fetch, responses, ...view }
}

const box = () => screen.getByRole('textbox', { name: 'Project context' })
const type = (value) => fireEvent.change(box(), { target: { value } })
const save = () => screen.getByRole('button', { name: 'Save' })
const preview = () => screen.getByRole('region', { name: 'Preview' })
const count = (fetch, url) => fetched(fetch).filter((u) => u === url).length
const advance = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))

test('FE16: the page fetches the context and the board view-model once each; 10 s fetch neither again', async () => {
  vi.useFakeTimers()
  const fetch = mockFetch({ [`GET ${BOARD}`]: [200, board()], [`GET ${CONTEXT}`]: [200, context('# Stack\n')] })
  renderAt('/projects/3/context')
  await advance(0)
  expect(box().value).toBe('# Stack\n')
  expect([count(fetch, BOARD), count(fetch, CONTEXT)]).toEqual([1, 1])
  await advance(10_000)
  expect([count(fetch, BOARD), count(fetch, CONTEXT)]).toEqual([1, 1])
})

test('FE17: with no click, a Project context textarea holds context_md, with its size and Save, and no <details>', async () => {
  await open([200, context('# Stack\n- Python 3.12\n')])
  expect(box().tagName).toBe('TEXTAREA')
  expect(box().value).toBe('# Stack\n- Python 3.12\n')
  expect(screen.getByText('22 / 16384 bytes')).toBeTruthy()
  expect(save().disabled).toBe(false)
  const main = screen.getByRole('main')
  expect(main.querySelector('details, summary')).toBeNull()
})

test('FE18: the Preview region holds context_html as HTML; a blank context says Nothing saved yet.', async () => {
  const { unmount } = await open([200, context('# Stack', { context_html: '<h1>Stack</h1>\n' })])
  expect(within(preview()).getByRole('heading', { level: 1, name: 'Stack' })).toBeTruthy()
  unmount()
  await open([200, context('  \n')])
  const empty = within(preview()).getByText('Nothing saved yet.')
  expect(empty.className).toMatch(/(^|\s)text-muted(\s|$)/)
  expect(preview().querySelector('.markdown')).toBeNull()
})

test('FE19: typing updates the size live in UTF-8 bytes against max_bytes; the Preview stays', async () => {
  await open([200, context('# Old', { context_html: '<h1>Old</h1>\n', max_bytes: 10 })])
  expect(screen.getByText('5 / 10 bytes')).toBeTruthy()
  type('é')
  expect(screen.getByText('2 / 10 bytes')).toBeTruthy()
  type('aé')
  expect(screen.getByText('3 / 10 bytes')).toBeTruthy()
  expect(within(preview()).getByRole('heading', { name: 'Old' })).toBeTruthy()
})

test('FE20: over max_bytes the size says over the limit in text-danger and Save is disabled', async () => {
  await open([200, context('', { max_bytes: 4 })])
  type('ééé')
  const size = screen.getByText('6 / 4 bytes · over the limit')
  expect(size.className).toMatch(/(^|\s)text-danger(\s|$)/)
  expect(save().disabled).toBe(true)
  type('éé')
  expect(screen.getByText('4 / 4 bytes').className).not.toMatch(/(^|\s)text-danger(\s|$)/)
  expect(save().disabled).toBe(false)
})

test('FE21: Save puts the draft once; on 200 the size is the reply bytes, the draft stays, and the Preview updates', async () => {
  const { fetch } = await open([200, context('')], {
    [`PUT ${CONTEXT}`]: [200, context('# Stack\n', { bytes: 99, context_html: '<h1>Stack</h1>\n' })],
  })
  type('# Stack\n')
  fireEvent.click(save())
  expect(await screen.findByText('99 / 16384 bytes')).toBeTruthy()
  const puts = fetch.mock.calls.filter(([u, init]) => u === CONTEXT && init?.method === 'PUT')
  expect(puts).toHaveLength(1)
  expect(JSON.parse(puts[0][1].body)).toEqual({ context_md: '# Stack\n' })
  expect(puts[0][1].headers['X-Requested-By']).toBe('fctl')
  expect(box().value).toBe('# Stack\n')
  expect(within(preview()).getByRole('heading', { name: 'Stack' })).toBeTruthy()
  expect(screen.queryByRole('alert')).toBeNull()
})

test('FE22: a refused Save shows its detail and keeps the draft and the old Preview', async () => {
  await open([200, context('old', { context_html: '<p>old</p>\n' })], {
    [`PUT ${CONTEXT}`]: [413, { detail: 'context over 16 KB' }],
  })
  type('draft é')
  fireEvent.click(save())
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe('context over 16 KB')
  expect(box().value).toBe('draft é')
  expect(screen.getByText('8 / 16384 bytes')).toBeTruthy()
  expect(within(preview()).getByText('old')).toBeTruthy()
})

test('FE23: a failed context load shows its detail and no textarea; a 404 from either is not-found; the title', async () => {
  mockFetch({ [`GET ${BOARD}`]: [200, board()], [`GET ${CONTEXT}`]: [500, { detail: 'boom' }] })
  const failed = renderAt('/projects/3/context')
  expect((await screen.findByRole('alert')).textContent).toBe('boom')
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('api · personal')
  expect(screen.queryByRole('textbox', { name: 'Project context' })).toBeNull()
  await waitFor(() => expect(document.title).toBe('api · Context · Claude Factories'))
  failed.unmount()

  for (const responses of [
    { [`GET ${BOARD}`]: [200, board()], [`GET ${CONTEXT}`]: [404, { detail: 'Project #3 not found' }] },
    { [`GET ${BOARD}`]: [404, { detail: 'Project #3 not found' }], [`GET ${CONTEXT}`]: [200, context('')] },
  ]) {
    mockFetch(responses)
    const { unmount } = renderAt('/projects/3/context')
    expect(await screen.findByRole('heading', { level: 1, name: 'Project #3 not found' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Go to the dashboard' })).toBeTruthy()
    expect(screen.queryByRole('textbox')).toBeNull()
    unmount()
  }
})

test("FE24: going from /projects/3/context with a draft to /projects/4/context shows project 4's context", async () => {
  const { router } = await open([200, context('three')], {
    'GET /api/pages/projects/4': [200, board({ ...PROJECT, id: 4, name: 'billing' })],
    'GET /api/projects/4/context': [200, context('four', { context_html: '<p>four</p>\n' })],
  })
  type('unsaved draft of three')
  await act(() => router.navigate('/projects/4/context'))
  await screen.findByRole('heading', { level: 1, name: 'billing · personal' })
  await waitFor(() => expect(box().value).toBe('four'))
  expect(screen.getByText('4 / 16384 bytes')).toBeTruthy()
  expect(within(preview()).getByText('four')).toBeTruthy()
})
