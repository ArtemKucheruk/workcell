import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { cls, expectSkeleton, fetched, mockFetch, renderAt } from '../../test/render.jsx'

const BOARD = '/api/pages/projects/3'
const LIST = '/api/projects/3/factories'
const PROJECT = { id: 3, name: 'api-server', workspace_id: 2, workspace: 'personal' }
const board = () => ({
  project: PROJECT, factory: 'ready', hint: null, can_run: true, workspaces: [],
  columns: { backlog: [], in_progress: [], review: [], done: [] },
})
const item = (id, name, nodes, updated_at = '2026-10-21T09:30:00Z') => ({
  id, name, nodes, created_at: '2026-10-21T08:00:00Z', updated_at,
})
const DEFAULT = item(7, 'default', 10)
const NIGHTLY = item(8, 'nightly', 1, '2026-10-20T09:30:00Z')

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

/** Renders /projects/3/factories with `list` as the list's reply; waits for the header. */
async function open(list = [200, [DEFAULT, NIGHTLY]], more = {}) {
  const responses = { [`GET ${BOARD}`]: [200, board()], [`GET ${LIST}`]: list, ...more }
  const fetch = mockFetch(responses)
  const view = renderAt('/projects/3/factories')
  await screen.findByRole('button', { name: '+ New factory' })
  return { fetch, responses, ...view }
}

const count = (fetch, url) => fetched(fetch).filter((u) => u === url).length
const calls = (fetch, method, url) => fetch.mock.calls.filter(([u, init]) => u === url && (init?.method ?? 'GET') === method)
const rows = () => screen.getAllByRole('row').slice(1) // the header row first
const names = () => rows().map((tr) => within(tr).queryAllByRole('cell')[0].textContent)
const advance = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))

test('FE1: the board view-model and the list load once each, never polled; a skeleton first; the header holds + New factory', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
  const pending = renderAt('/projects/3/factories')
  expectSkeleton(screen.getByRole('status'))
  pending.unmount()

  const fetch = mockFetch({ [`GET ${BOARD}`]: [200, board()], [`GET ${LIST}`]: [200, [DEFAULT]] })
  const view = renderAt('/projects/3/factories')
  await advance(0)
  expect([count(fetch, BOARD), count(fetch, LIST)]).toEqual([1, 1])
  await advance(10_000)
  expect([count(fetch, BOARD), count(fetch, LIST)]).toEqual([1, 1])
  const h1 = screen.getAllByRole('heading', { level: 1 }).find((h) => h.textContent === 'api-server · personal')
  const header = h1.closest('header')
  expect(within(header).getByText('Factory: ready ✓')).toBeTruthy()
  expect(within(header).getByRole('button', { name: '+ New factory' })).toBeTruthy()
  expect(document.title).toBe('api-server · Factories · Claude Factories')
  // 042 FE37's kind: a list, so main keeps its max width
  expect(view.container.querySelector('main').className.split(/\s+/)).toEqual(expect.arrayContaining(['mx-auto', 'max-w-6xl']))
})

test('FE1: a 404 from either request is the not-found page; any other failed first load is the red alert', async () => {
  for (const [key, reply, heading] of [
    [`GET ${BOARD}`, [404, { detail: 'Project #3 not found' }], 'Project #3 not found'],
    [`GET ${LIST}`, [404, { detail: 'Project #3 not found' }], 'Project #3 not found'],
  ]) {
    mockFetch({ [`GET ${BOARD}`]: [200, board()], [`GET ${LIST}`]: [200, []], [key]: reply })
    const { unmount } = renderAt('/projects/3/factories')
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeTruthy()
    unmount()
  }
  for (const key of [`GET ${BOARD}`, `GET ${LIST}`]) {
    mockFetch({ [`GET ${BOARD}`]: [200, board()], [`GET ${LIST}`]: [200, []], [key]: [500, { detail: 'boom' }] })
    const { unmount } = renderAt('/projects/3/factories')
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe('boom')
    expect(alert.className).toMatch(cls('text-danger'))
    unmount()
  }
})

test('FE2: one row per factory in the order returned: the name links to the designer, the node count, and a relative Updated', async () => {
  await open([200, [NIGHTLY, DEFAULT]])
  expect(names()).toEqual(['nightly', 'default'])
  const [first, second] = rows()
  expect(within(second).getByRole('link', { name: 'default' }).getAttribute('href')).toBe('/projects/3/factories/7')
  expect(within(first).getByRole('link', { name: 'nightly' }).getAttribute('href')).toBe('/projects/3/factories/8')
  expect(within(second).getByText('10 nodes')).toBeTruthy()
  expect(within(first).getByText('1 node')).toBeTruthy()
  const time = second.querySelector('time')
  expect(time.getAttribute('dateTime')).toBe(DEFAULT.updated_at)
  expect(time.getAttribute('title')).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)
  expect(time.textContent).toMatch(/ago$|^just now$|^yesterday$|^\d{4}-\d{2}-\d{2}$/)
})

test('FE2: with no factories it says No factories yet., and + New factory stays', async () => {
  await open([200, []])
  expect(screen.getByText('No factories yet.')).toBeTruthy()
  expect(screen.queryByRole('table')).toBeNull()
  expect(screen.getByRole('button', { name: '+ New factory' })).toBeTruthy()
})

// jsdom's UA sheet hides a closed popover (board tests), so its contents are queried with hidden: true
test('FE3: + New factory opens a popover with Name and Create; a 201 opens the designer', async () => {
  const made = { id: 9, project_id: 3, name: 'nightly' }
  const { fetch, router } = await open(undefined, { [`POST ${LIST}`]: [201, made] })
  const opener = screen.getByRole('button', { name: '+ New factory' })
  const pop = document.getElementById(opener.getAttribute('popovertarget'))
  expect(pop.getAttribute('popover')).toBe('auto')
  const name = within(pop).getByRole('textbox', { name: 'Name', hidden: true })
  expect(name.value).toBe('')
  fireEvent.change(name, { target: { value: 'nightly' } })
  fireEvent.click(within(pop).getByRole('button', { name: 'Create', hidden: true }))
  await waitFor(() => expect(router.state.location.pathname).toBe('/projects/3/factories/9'))
  const [[, init]] = calls(fetch, 'POST', LIST)
  expect(init.headers['X-Requested-By']).toBe('fctl')
  expect(JSON.parse(init.body)).toEqual({ name: 'nightly' })
})

test('FE3: a 409 or 422 shows its detail inside the popover, which keeps the typed name', async () => {
  for (const [reply, detail, typed] of [
    [[409, { detail: 'factory default already exists' }], 'factory default already exists', 'default'],
    [[422, { detail: 'name must not be blank' }], 'name must not be blank', '   '],
  ]) {
    const { router, unmount } = await open(undefined, { [`POST ${LIST}`]: reply })
    const pop = document.getElementById(screen.getByRole('button', { name: '+ New factory' }).getAttribute('popovertarget'))
    const name = within(pop).getByRole('textbox', { name: 'Name', hidden: true })
    fireEvent.change(name, { target: { value: typed } })
    fireEvent.click(within(pop).getByRole('button', { name: 'Create', hidden: true }))
    expect((await within(pop).findByRole('alert', { hidden: true })).textContent).toBe(detail)
    expect(name.value).toBe(typed)
    expect(router.state.location.pathname).toBe('/projects/3/factories')
    unmount()
  }
})

test('FE4: Rename swaps the name for a focused, selected field; Enter PUTs the name and the list reloads with it', async () => {
  const { fetch, responses } = await open(undefined, { 'PUT /api/factories/7': [200, { id: 7, name: 'nightly-2' }] })
  fireEvent.click(screen.getByRole('button', { name: 'Rename default' }))
  const input = screen.getByRole('textbox', { name: 'Rename default' })
  expect(input.value).toBe('default')
  expect(document.activeElement).toBe(input)
  expect([input.selectionStart, input.selectionEnd]).toEqual([0, 7])
  expect(screen.queryByRole('link', { name: 'default' })).toBeNull()
  responses[`GET ${LIST}`] = [200, [{ ...DEFAULT, name: 'nightly-2' }, NIGHTLY]]
  fireEvent.change(input, { target: { value: 'nightly-2' } })
  fireEvent.submit(input.form)
  expect(await screen.findByRole('link', { name: 'nightly-2' })).toBeTruthy()
  const [[, init]] = calls(fetch, 'PUT', '/api/factories/7')
  expect(init.headers['X-Requested-By']).toBe('fctl')
  expect(JSON.parse(init.body)).toEqual({ name: 'nightly-2' })
  expect(count(fetch, LIST)).toBe(2)
  expect(screen.queryByRole('textbox', { name: /^Rename/ })).toBeNull()
})

test('FE4: Esc or blur removes the field with no request; a refusal shows beside it, and it stays', async () => {
  const { fetch } = await open(undefined, { 'PUT /api/factories/7': [409, { detail: 'factory nightly already exists' }] })
  const rename = screen.getByRole('button', { name: 'Rename default' })
  fireEvent.click(rename)
  fireEvent.keyDown(screen.getByRole('textbox', { name: 'Rename default' }), { key: 'Escape' })
  expect(screen.queryByRole('textbox', { name: 'Rename default' })).toBeNull()
  expect(document.activeElement).toBe(rename)
  fireEvent.click(rename)
  fireEvent.blur(screen.getByRole('textbox', { name: 'Rename default' }))
  expect(screen.queryByRole('textbox', { name: 'Rename default' })).toBeNull()
  expect(calls(fetch, 'PUT', '/api/factories/7')).toEqual([])

  fireEvent.click(rename)
  const input = screen.getByRole('textbox', { name: 'Rename default' })
  fireEvent.change(input, { target: { value: 'nightly' } })
  fireEvent.submit(input.form)
  const alert = await within(input.form).findByRole('alert')
  expect(alert.textContent).toBe('factory nightly already exists')
  expect(screen.getByRole('textbox', { name: 'Rename default' }).value).toBe('nightly')
})

test('FE5: Delete opens the dialog with Q16\'s text, Cancel first; Delete sends DELETE and the list reloads without the row', async () => {
  const { fetch, responses } = await open(undefined, { 'DELETE /api/factories/7': [204] })
  fireEvent.click(screen.getByRole('button', { name: 'Delete default' }))
  const dialog = screen.getByRole('dialog', { name: 'Delete factory default?' })
  expect(dialog.open).toBe(true)
  expect(within(dialog).getByText(
    "This removes the factory's design from the app. Files in the repo, such as the ones Create factory wrote, stay.",
  )).toBeTruthy()
  const buttons = within(dialog).getAllByRole('button')
  expect(buttons.map((b) => b.textContent)).toEqual(['Cancel', 'Delete'])
  expect(buttons[1].className).toMatch(cls('bg-danger'))
  responses[`GET ${LIST}`] = [200, [NIGHTLY]]
  fireEvent.click(buttons[1])
  await waitFor(() => expect(names()).toEqual(['nightly']))
  expect(screen.queryByRole('dialog')).toBeNull()
  const [[, init]] = calls(fetch, 'DELETE', '/api/factories/7')
  expect(init.headers['X-Requested-By']).toBe('fctl')
})

test('FE5: Cancel or Esc sends nothing; a refusal shows inside the dialog, which stays open', async () => {
  const { fetch } = await open(undefined, { 'DELETE /api/factories/7': [409, { detail: 'factory default is in use' }] })
  const del = screen.getByRole('button', { name: 'Delete default' })
  fireEvent.click(del)
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(del)
  fireEvent.click(del)
  act(() => screen.getByRole('dialog').close()) // what Esc does after its cancel event
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(calls(fetch, 'DELETE', '/api/factories/7')).toEqual([])

  fireEvent.click(del)
  const dialog = screen.getByRole('dialog')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
  expect((await within(dialog).findByRole('alert')).textContent).toBe('factory default is in use')
  expect(dialog.open).toBe(true)
  expect(names()).toEqual(['default', 'nightly'])
})
