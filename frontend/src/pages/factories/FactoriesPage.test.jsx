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
const item = (id, name, nodes, updated_at = '2026-10-21T09:30:00Z', kind = 'workflow') => ({
  id, name, kind, nodes, created_at: '2026-10-21T08:00:00Z', updated_at,
})
const DEFAULT = item(7, 'default', 10)
const NIGHTLY = item(8, 'nightly', 1, '2026-10-20T09:30:00Z')
const AUDIT = item(9, 'audit', 7, '2026-10-19T09:30:00Z', 'automation')
const TEMPLATES = '/api/factory-templates'
const TEMPLATE_LIST = [
  { key: 'standard', name: 'Standard', description: 'Spec, build, four reviews, the approver decides.', kind: 'workflow' },
  { key: 'bug-fix', name: 'Bug fix', description: 'Reproduce the bug as a failing test, then fix it.', kind: 'workflow' },
  { key: 'security-audit', name: 'Security audit', description: 'Audit the repo.', kind: 'automation' },
  { key: 'test-coverage', name: 'Test coverage', description: 'Pin risky untested code with tests.', kind: 'automation' },
]
const NEW_WORKFLOW = '+ New workflow'
const NEW_AUTOMATION = '+ New automation'

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

// jsdom's UA sheet hides a closed popover (board tests), so its contents are queried with hidden: true
const popOf = (label) => document.getElementById(screen.getByRole('button', { name: label }).getAttribute('popovertarget'))
const templateGroup = (label = NEW_WORKFLOW) => within(popOf(label)).getByRole('group', { name: 'Template', hidden: true })
const radios = (label) => within(templateGroup(label)).queryAllByRole('radio', { hidden: true })
const section = (name) => within(screen.getByRole('region', { name }))

/** Renders /projects/3/factories with `list` as the list's reply; waits for both + New and the templates (088). */
async function open(list = [200, [DEFAULT, NIGHTLY, AUDIT]], more = {}) {
  const responses = { [`GET ${BOARD}`]: [200, board()], [`GET ${LIST}`]: list, [`GET ${TEMPLATES}`]: [200, TEMPLATE_LIST], ...more }
  const fetch = mockFetch(responses)
  const view = renderAt('/projects/3/factories')
  await screen.findByRole('button', { name: NEW_WORKFLOW })
  // the legend, then the radios or the templates' alert
  await waitFor(() => expect(templateGroup().children.length).toBeGreaterThan(1))
  return { fetch, responses, ...view }
}

/** Types `name` into a + New popover and presses Create. */
function create(label, name) {
  const pop = popOf(label)
  fireEvent.change(within(pop).getByRole('textbox', { name: 'Name', hidden: true }), { target: { value: name } })
  fireEvent.click(within(pop).getByRole('button', { name: 'Create', hidden: true }))
  return pop
}

const count = (fetch, url) => fetched(fetch).filter((u) => u === url).length
const calls = (fetch, method, url) => fetch.mock.calls.filter(([u, init]) => u === url && (init?.method ?? 'GET') === method)
const rows = (name = 'Workflows') => section(name).getAllByRole('row').slice(1) // the header row first
const names = (name = 'Workflows') => rows(name).map((tr) => within(tr).queryAllByRole('cell')[0].textContent)
const advance = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))

test('FE1: the board view-model and the list load once each, never polled; a skeleton first; the header, then the sections', async () => {
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
  expect(section('Workflows').getByRole('button', { name: NEW_WORKFLOW })).toBeTruthy()
  expect(section('Automations').getByRole('button', { name: NEW_AUTOMATION })).toBeTruthy()
  // 042 FE37's kind: a list, so main keeps its max width
  expect(view.container.querySelector('main').className.split(/\s+/)).toEqual(expect.arrayContaining(['mx-auto', 'max-w-6xl']))
})

test('101 AC17: the title is {project} · Workflows · Claude Factories', async () => {
  await open()
  expect(document.title).toBe('api-server · Workflows · Claude Factories')
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

test('101 AC11: a Workflows section lists only workflows and an Automations section only automations, each under an h2 with the table and row actions', async () => {
  await open([200, [AUDIT, DEFAULT]])
  expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual(['Workflows', 'Automations'])
  for (const [name, row] of [['Workflows', 'default'], ['Automations', 'audit']]) {
    const region = section(name)
    expect(region.getAllByRole('columnheader').map((th) => th.textContent)).toEqual(['Name', 'Nodes', 'Updated', 'Actions'])
    expect(names(name)).toEqual([row])
    expect(region.getByRole('button', { name: `Rename ${row}` })).toBeTruthy()
    expect(region.getByRole('button', { name: `Delete ${row}` })).toBeTruthy()
  }
  expect(section('Automations').getByRole('link', { name: 'audit' }).getAttribute('href')).toBe('/projects/3/factories/9')
})

test('FE2: one row per workflow in the order returned: the name links to the designer, the node count, and a relative Updated', async () => {
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

test('101 AC12: each section has its own empty text, and its + New stays', async () => {
  await open([200, [DEFAULT]])
  expect(section('Automations').getByText('No automations yet.')).toBeTruthy()
  expect(section('Automations').queryByRole('table')).toBeNull()
  expect(names()).toEqual(['default'])
  expect(section('Automations').getByRole('button', { name: NEW_AUTOMATION })).toBeTruthy()
})

test('101 AC12: with no workflows, the Workflows section says No workflows yet.', async () => {
  await open([200, [AUDIT]])
  expect(section('Workflows').getByText('No workflows yet.')).toBeTruthy()
  expect(section('Workflows').queryByRole('table')).toBeNull()
  expect(names('Automations')).toEqual(['audit'])
  expect(section('Workflows').getByRole('button', { name: NEW_WORKFLOW })).toBeTruthy()
})

test('FE3, 101 AC13: + New workflow opens a popover with Name, only the workflow templates (Standard checked), and Create; it POSTs kind workflow and a 201 opens the designer', async () => {
  const made = { id: 9, project_id: 3, name: 'nightly' }
  const { fetch, router } = await open(undefined, { [`POST ${LIST}`]: [201, made] })
  const pop = popOf(NEW_WORKFLOW)
  expect(pop.getAttribute('popover')).toBe('auto')
  expect(within(pop).getByRole('textbox', { name: 'Name', hidden: true }).value).toBe('')
  expect(radios(NEW_WORKFLOW).map((r) => [r.value, r.checked])).toEqual([['standard', true], ['bug-fix', false]])
  create(NEW_WORKFLOW, 'nightly')
  await waitFor(() => expect(router.state.location.pathname).toBe('/projects/3/factories/9'))
  const [[, init]] = calls(fetch, 'POST', LIST)
  expect(init.headers['X-Requested-By']).toBe('fctl')
  expect(JSON.parse(init.body)).toEqual({ name: 'nightly', template: 'standard', kind: 'workflow' })
})

test('101 AC14: + New automation offers only the automation templates, the first checked; it POSTs kind automation and opens the designer', async () => {
  const { fetch, router } = await open(undefined, { [`POST ${LIST}`]: [201, { id: 10, project_id: 3, name: 'weekly' }] })
  const list = radios(NEW_AUTOMATION)
  expect(list.map((r) => r.labels[0].textContent)).toEqual(['Security audit', 'Test coverage'])
  expect(list.map((r) => r.checked)).toEqual([true, false])
  create(NEW_AUTOMATION, 'weekly')
  await waitFor(() => expect(router.state.location.pathname).toBe('/projects/3/factories/10'))
  const [[, init]] = calls(fetch, 'POST', LIST)
  expect(JSON.parse(init.body)).toEqual({ name: 'weekly', template: 'security-audit', kind: 'automation' })
})

test('101 AC15: the two popovers have distinct ids, anchors, and radio ids', async () => {
  await open()
  const [workflow, automation] = [NEW_WORKFLOW, NEW_AUTOMATION].map(popOf)
  expect(workflow.id).not.toBe(automation.id)
  const anchors = [NEW_WORKFLOW, NEW_AUTOMATION].map((label) =>
    screen.getByRole('button', { name: label }).className.match(/\[anchor-name:(--[\w-]+)\]/)[1])
  expect(anchors[0]).not.toBe(anchors[1])
  expect(workflow.className).toContain(`[position-anchor:${anchors[0]}]`)
  expect(automation.className).toContain(`[position-anchor:${anchors[1]}]`)
  const ids = [...document.querySelectorAll('[id]')].map((el) => el.id)
  expect(new Set(ids).size).toBe(ids.length)
})

test('FE3, 101 AC15: a 409 or 422 shows its detail inside the popover that sent it, which keeps the typed name', async () => {
  for (const label of [NEW_WORKFLOW, NEW_AUTOMATION]) {
    for (const [reply, detail, typed] of [
      [[409, { detail: 'factory default already exists' }], 'factory default already exists', 'default'],
      [[422, { detail: 'name must not be blank' }], 'name must not be blank', '   '],
    ]) {
      const { router, unmount } = await open(undefined, { [`POST ${LIST}`]: reply })
      const pop = create(label, typed)
      expect((await within(pop).findByRole('alert', { hidden: true })).textContent).toBe(detail)
      expect(within(pop).getByRole('textbox', { name: 'Name', hidden: true }).value).toBe(typed)
      const other = popOf(label === NEW_WORKFLOW ? NEW_AUTOMATION : NEW_WORKFLOW)
      expect(within(other).queryByRole('alert', { hidden: true })).toBeNull()
      expect(router.state.location.pathname).toBe('/projects/3/factories')
      unmount()
    }
  }
})

test('088 AC14: the templates load once beside the board and the list, never polled', async () => {
  vi.useFakeTimers()
  const fetch = mockFetch({ [`GET ${BOARD}`]: [200, board()], [`GET ${LIST}`]: [200, []], [`GET ${TEMPLATES}`]: [200, TEMPLATE_LIST] })
  renderAt('/projects/3/factories')
  await advance(0)
  expect([count(fetch, BOARD), count(fetch, LIST), count(fetch, TEMPLATES)]).toEqual([1, 1, 1])
  await advance(10_000)
  expect([count(fetch, BOARD), count(fetch, LIST), count(fetch, TEMPLATES)]).toEqual([1, 1, 1])
})

test('088 AC15: a Template fieldset, one radio per template of the kind in the API order, each described by its muted description', async () => {
  await open()
  for (const [label, kind] of [[NEW_WORKFLOW, 'workflow'], [NEW_AUTOMATION, 'automation']]) {
    const expected = TEMPLATE_LIST.filter((t) => t.kind === kind)
    const list = radios(label)
    expect(list.map((r) => r.labels[0].textContent)).toEqual(expected.map((t) => t.name))
    expect(list.map((r) => r.value)).toEqual(expected.map((t) => t.key))
    list.forEach((radio, i) => {
      const note = document.getElementById(radio.getAttribute('aria-describedby'))
      expect(note.textContent).toBe(expected[i].description)
      expect(note.className).toMatch(cls('text-muted'))
    })
  }
})

test('088 AC16: pick Bug fix, type a name, and Create → the POST carries the key; a 201 opens the designer', async () => {
  const { fetch, router } = await open(undefined, { [`POST ${LIST}`]: [201, { id: 9, project_id: 3, name: 'nightly' }] })
  fireEvent.click(within(templateGroup()).getByRole('radio', { name: 'Bug fix', hidden: true }))
  create(NEW_WORKFLOW, 'nightly')
  await waitFor(() => expect(router.state.location.pathname).toBe('/projects/3/factories/9'))
  const [[, init]] = calls(fetch, 'POST', LIST)
  expect(JSON.parse(init.body)).toEqual({ name: 'nightly', template: 'bug-fix', kind: 'workflow' })
})

test('088 AC17, 101 Q8: a failed templates request shows its detail where the radios go, in both popovers; Create still posts the name', async () => {
  const { fetch, router } = await open(undefined, {
    [`GET ${TEMPLATES}`]: [500, { detail: 'templates unavailable' }],
    [`POST ${LIST}`]: [201, { id: 9, project_id: 3, name: 'nightly' }],
  })
  for (const label of [NEW_WORKFLOW, NEW_AUTOMATION]) {
    expect(within(templateGroup(label)).getByRole('alert', { hidden: true }).textContent).toBe('templates unavailable')
    expect(radios(label)).toEqual([])
  }
  create(NEW_AUTOMATION, 'nightly')
  await waitFor(() => expect(router.state.location.pathname).toBe('/projects/3/factories/9'))
  const [[, init]] = calls(fetch, 'POST', LIST)
  expect(JSON.parse(init.body)).toEqual({ name: 'nightly', template: null, kind: 'automation' })
})

test('FE4: Rename swaps the name for a focused, selected field; Enter PUTs the name and the list reloads with it', async () => {
  const { fetch, responses } = await open(undefined, { 'PUT /api/factories/7': [200, { id: 7, name: 'nightly-2' }] })
  fireEvent.click(screen.getByRole('button', { name: 'Rename default' }))
  const input = screen.getByRole('textbox', { name: 'Rename default' })
  expect(input.value).toBe('default')
  expect(document.activeElement).toBe(input)
  expect([input.selectionStart, input.selectionEnd]).toEqual([0, 7])
  expect(screen.queryByRole('link', { name: 'default' })).toBeNull()
  responses[`GET ${LIST}`] = [200, [{ ...DEFAULT, name: 'nightly-2' }, NIGHTLY, AUDIT]]
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
  const dialog = screen.getByRole('dialog', { name: 'Delete workflow default?' })
  expect(dialog.open).toBe(true)
  expect(within(dialog).getByText(
    "This removes the factory's design from the app. Files in the repo, such as the ones Create factory wrote, stay.",
  )).toBeTruthy()
  const buttons = within(dialog).getAllByRole('button')
  expect(buttons.map((b) => b.textContent)).toEqual(['Cancel', 'Delete'])
  expect(buttons[1].className).toMatch(cls('bg-danger'))
  responses[`GET ${LIST}`] = [200, [NIGHTLY, AUDIT]]
  fireEvent.click(buttons[1])
  await waitFor(() => expect(names()).toEqual(['nightly']))
  expect(screen.queryByRole('dialog')).toBeNull()
  const [[, init]] = calls(fetch, 'DELETE', '/api/factories/7')
  expect(init.headers['X-Requested-By']).toBe('fctl')
})

test('101 AC16, Q4: deleting a row moves focus to its section\'s + New; the dialog names the kind', async () => {
  for (const [row, label, title, rest] of [
    ['default', NEW_WORKFLOW, 'Delete workflow default?', [NIGHTLY, AUDIT]],
    ['audit', NEW_AUTOMATION, 'Delete automation audit?', [DEFAULT, NIGHTLY]],
  ]) {
    const id = { default: 7, audit: 9 }[row]
    const { responses, unmount } = await open(undefined, { [`DELETE /api/factories/${id}`]: [204] })
    fireEvent.click(screen.getByRole('button', { name: `Delete ${row}` }))
    const dialog = screen.getByRole('dialog', { name: title })
    responses[`GET ${LIST}`] = [200, rest]
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(document.activeElement).toBe(screen.getByRole('button', { name: label }))
    unmount()
  }
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
