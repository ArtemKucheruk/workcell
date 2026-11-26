import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { fetched, mockFetch, renderAt } from '../../test/render.jsx'

const BOARD = '/api/pages/projects/3'
const LIST = '/api/projects/3/modules'
const PROJECT = { id: 3, name: 'api-server', workspace_id: 2, workspace: 'personal' }
const board = () => ({
  project: PROJECT, factory: 'ready', hint: null, can_run: true, workspaces: [],
  columns: { backlog: [], in_progress: [], review: [], done: [] },
  runs_enabled: true, runs_active: 0, max_concurrent_runs: 2, accounts: [], auto: null,
})
const counts = (backlog = 0, in_progress = 0, review = 0, done = 0) => ({ backlog, in_progress, review, done })
const BACKEND = { id: 5, name: 'backend', description_md: 'The API', counts: counts(2, 1, 0, 7) }
const FRONTEND = { id: 7, name: 'frontend', description_md: '', counts: counts(1) }
const LISTED = { modules: [BACKEND, FRONTEND], no_module: counts(3, 0, 1, 0) }

afterEach(() => vi.restoreAllMocks())

async function open(list = LISTED, more = {}) {
  const responses = { [`GET ${BOARD}`]: [200, board()], [`GET ${LIST}`]: [200, list], ...more }
  const fetch = mockFetch(responses)
  const view = renderAt('/projects/3/modules')
  await screen.findByRole('button', { name: '+ New module' })
  return { fetch, responses, ...view }
}

const calls = (fetch, method, url) => fetch.mock.calls.filter(([u, init]) => u === url && (init?.method ?? 'GET') === method)
const sent = (fetch, method, url) => JSON.parse(calls(fetch, method, url).at(-1)[1].body)
const items = () => within(screen.getByRole('region', { name: 'Modules' })).getAllByRole('listitem')
const newModule = () => document.getElementById('new-module')

test('AC16: each module with its name, description, and counts, then a No module row; the title names the page', async () => {
  await open()
  const [backend, frontend, none] = items()
  expect(within(backend).getByRole('heading', { level: 3 }).textContent).toBe('backend')
  expect(within(backend).getByText('The API')).toBeTruthy()
  expect(within(backend).getByText('2 backlog · 1 in progress · 0 review · 7 done')).toBeTruthy()
  expect(within(frontend).getByText('1 backlog · 0 in progress · 0 review · 0 done')).toBeTruthy()
  expect(within(none).getByRole('heading', { level: 3 }).textContent).toBe('No module')
  expect(within(none).getByText('3 backlog · 0 in progress · 1 review · 0 done')).toBeTruthy()
  expect(document.title).toBe('api-server · Modules · Claude Factories')
})

test('AC16: with no modules, an empty note and the No module row', async () => {
  await open({ modules: [], no_module: counts(4) })
  expect(screen.getByText('No modules yet.')).toBeTruthy()
  expect(items().map((li) => within(li).getByRole('heading').textContent)).toEqual(['No module'])
})

test('AC16: an unknown project shows the not-found page', async () => {
  mockFetch({ [`GET ${BOARD}`]: [404, { detail: 'Not Found' }], [`GET ${LIST}`]: [404, { detail: 'Project #3 not found' }] })
  renderAt('/projects/3/modules')
  expect(await screen.findByRole('heading', { level: 1, name: /Not Found|Project #3 not found/ })).toBeTruthy()
})

test('AC17: + New module posts name and description, then the list reloads with it', async () => {
  const { fetch, responses } = await open(LISTED, { [`POST ${LIST}`]: [201, { id: 9, name: 'docs', description_md: 'Guides', counts: counts() }] })
  const pop = newModule()
  responses[`GET ${LIST}`] = [200, { ...LISTED, modules: [BACKEND, { id: 9, name: 'docs', description_md: 'Guides', counts: counts() }, FRONTEND] }]
  fireEvent.change(within(pop).getByRole('textbox', { name: 'Name', hidden: true }), { target: { value: 'docs' } })
  fireEvent.change(within(pop).getByRole('textbox', { name: 'Description', hidden: true }), { target: { value: 'Guides' } })
  fireEvent.click(within(pop).getByRole('button', { name: 'Create', hidden: true }))
  await waitFor(() => expect(items()).toHaveLength(4))
  expect(sent(fetch, 'POST', LIST)).toEqual({ name: 'docs', description_md: 'Guides' })
  expect(within(items()[1]).getByRole('heading').textContent).toBe('docs')
})

test('AC17: a refusal shows its detail in the form, which keeps the input', async () => {
  await open(LISTED, { [`POST ${LIST}`]: [409, { detail: 'module backend already exists' }] })
  const pop = newModule()
  const nameBox = within(pop).getByRole('textbox', { name: 'Name', hidden: true })
  fireEvent.change(nameBox, { target: { value: 'Backend' } })
  fireEvent.click(within(pop).getByRole('button', { name: 'Create', hidden: true }))
  const alert = await within(pop).findByRole('alert', { hidden: true })
  expect(alert.textContent).toBe('module backend already exists')
  expect(nameBox.value).toBe('Backend')
})

test('AC18: Edit changes name and description and saves with PATCH; a refusal shows inline', async () => {
  const { fetch, responses } = await open(LISTED, { 'PATCH /api/modules/5': [422, { detail: 'a module name is 1 to 40 ASCII letters, digits, - or _, e.g. frontend or api_v2' }] })
  fireEvent.click(screen.getByRole('button', { name: 'Edit backend' }))
  const form = screen.getByRole('listitem', { name: 'Edit backend' })
  const nameBox = within(form).getByRole('textbox', { name: 'Name' })
  expect(nameBox.value).toBe('backend')
  expect(document.activeElement).toBe(nameBox)
  fireEvent.change(nameBox, { target: { value: 'back end' } })
  fireEvent.click(within(form).getByRole('button', { name: 'Save' }))
  expect((await within(form).findByRole('alert')).textContent).toMatch(/ASCII letters/)
  expect(nameBox.value).toBe('back end')

  responses['PATCH /api/modules/5'] = [200, { ...BACKEND, name: 'api', description_md: 'HTTP' }]
  responses[`GET ${LIST}`] = [200, { ...LISTED, modules: [{ ...BACKEND, name: 'api', description_md: 'HTTP' }, FRONTEND] }]
  fireEvent.change(nameBox, { target: { value: 'api' } })
  fireEvent.change(within(form).getByRole('textbox', { name: 'Description' }), { target: { value: 'HTTP' } })
  fireEvent.click(within(form).getByRole('button', { name: 'Save' }))
  await screen.findByRole('button', { name: 'Edit api' })
  expect(sent(fetch, 'PATCH', '/api/modules/5')).toEqual({ name: 'api', description_md: 'HTTP' })
})

test('AC18: Cancel leaves the module unchanged, with no request', async () => {
  const { fetch } = await open()
  fireEvent.click(screen.getByRole('button', { name: 'Edit backend' }))
  fireEvent.click(within(screen.getByRole('listitem', { name: 'Edit backend' })).getByRole('button', { name: 'Cancel' }))
  expect(screen.getByRole('button', { name: 'Edit backend' })).toBe(document.activeElement)
  expect(calls(fetch, 'PATCH', '/api/modules/5')).toEqual([])
})

test('AC19: Delete opens the delete dialog saying its tasks stay; confirming removes the row and reloads the counts', async () => {
  const { fetch, responses } = await open(LISTED, { 'DELETE /api/modules/5': [204] })
  fireEvent.click(screen.getByRole('button', { name: 'Delete backend' }))
  const dialog = screen.getByRole('dialog', { name: 'Delete module backend?' })
  expect(dialog.textContent).toMatch('Its tasks stay, without a module.')
  responses[`GET ${LIST}`] = [200, { modules: [FRONTEND], no_module: counts(5, 1, 1, 7) }]
  fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
  await waitFor(() => expect(items()).toHaveLength(2))
  expect(calls(fetch, 'DELETE', '/api/modules/5')).toHaveLength(1)
  expect(within(items()[1]).getByText('5 backlog · 1 in progress · 1 review · 7 done')).toBeTruthy()
  expect(fetched(fetch).filter((u) => u === LIST)).toHaveLength(2)
})
