import '../../test/reactflow.js'
import { act, createEvent, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { cls, expectSkeleton, fetched, mockFetch, renderAt } from '../../test/render.jsx'
import { optionLabels, pick } from '../../test/select.js'

const URL = '/api/factories/7'
const agent = (name, model, extra = {}) => ({
  name, description: `The ${name}.`, model, tools: ['Read', 'Edit'], prompt: `Input: a task id {{ test_cmd }}\n`, ...extra,
})
const node = (id, type, x, y, data = {}) => ({ id, type, position: { x, y }, data })
const edge = (id, source, target, sourceHandle = null) => ({ id, source, sourceHandle, target })
const FOCUS = ['security', 'ux', 'ui', 'code']
/** docs/data-model-and-api.md §6.1's default graph: 10 nodes and 14 edges. */
const GRAPH = {
  nodes: [
    node('start', 'start', 0, 0),
    node('spec-writer', 'spec_writer', 250, 0, agent('spec-writer', 'opus')),
    node('builder', 'builder', 550, 0, agent('builder', 'opus', { side: 'both' })),
    ...FOCUS.map((focus, i) => node(`review-${focus}`, 'reviewer', 850, i * 120 - 180, agent(`review-${focus}`, 'sonnet', { focus }))),
    node('all-pass', 'all_pass', 1150, 0),
    node('rounds', 'rounds_below', 1450, 160, { n: 2 }),
    node('approver', 'approver', 1750, 0, agent('approver', 'opus')),
  ],
  edges: [
    edge('e1', 'start', 'spec-writer'),
    edge('e2', 'spec-writer', 'builder'),
    ...FOCUS.map((focus, i) => edge(`e${3 + i}`, 'builder', `review-${focus}`)),
    ...FOCUS.map((focus, i) => edge(`e${7 + i}`, `review-${focus}`, 'all-pass')),
    edge('e11', 'all-pass', 'approver', 'yes'),
    edge('e12', 'all-pass', 'rounds', 'no'),
    edge('e13', 'rounds', 'builder', 'yes'),
    edge('e14', 'rounds', 'approver', 'no'),
  ],
}
const FACTORY = {
  id: 7, project_id: 3, project: 'api-server', workspace_id: 2, workspace: 'personal', name: 'default', kind: 'workflow',
  graph: GRAPH, created_at: '2026-10-21T08:00:00Z', updated_at: '2026-10-21T09:30:00Z',
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

/** Renders the designer with `factory` as GET's reply; waits until React Flow has drawn every edge. */
async function open(more = {}, factory = FACTORY) {
  const responses = { [`GET ${URL}`]: [200, factory], ...more }
  const fetch = mockFetch(responses)
  const view = renderAt('/projects/3/factories/7')
  await screen.findByRole('heading', { level: 1, name: factory.name })
  await waitFor(() => expect(document.querySelectorAll('.react-flow__edge')).toHaveLength(factory.graph.edges.length))
  return { fetch, responses, ...view }
}

const flowNode = (id) => document.querySelector(`.react-flow__node[data-id="${id}"]`)
const flowNodes = () => [...document.querySelectorAll('.react-flow__node')]
const save = () => screen.getByRole('button', { name: 'Save' })
const titleRow = () => within(screen.getByRole('heading', { level: 1 }).parentElement)
const status = () => titleRow().getByRole('status').textContent
const panel = () => within(screen.getByRole('region', { name: 'Node' }))
const palette = (name) => screen.getByRole('button', { name })
const puts = (fetch) => fetch.mock.calls.filter(([url, init]) => url === URL && init?.method === 'PUT')
const sent = (call) => JSON.parse(call[1].body)
const select = (id) => fireEvent.click(flowNode(id))
const press = (key, init = {}) => {
  const down = fireEvent.keyDown(document.body, { key, ...init })
  fireEvent.keyUp(document.body, { key, ...init })
  return down // false when the keydown was cancelled
}

/** The flow's viewport transform, so a screen point can be turned into a flow position the way React Flow does. */
function viewport() {
  const [, x, y, zoom] = document.querySelector('.react-flow__viewport').style.transform.match(/translate\(([-\d.]+)px, ?([-\d.]+)px\) scale\(([\d.]+)\)/)
  return { x: +x, y: +y, zoom: +zoom }
}
/** Every element's box, from here on: the flow and its wrapper at (100, 50), 800 × 600. */
const BOX = { left: 100, top: 50, x: 100, y: 50, width: 800, height: 600, right: 900, bottom: 650 }
const boxes = () => vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(BOX)
const toFlow = (clientX, clientY) => {
  const { x, y, zoom } = viewport()
  return { x: (clientX - BOX.left - x) / zoom, y: (clientY - BOX.top - y) / zoom }
}

/** A fetch whose PUTs wait for `release()`, then answer `reply`; the GET answers the factory. */
function gatedFetch() {
  const gate = { reply: [200, FACTORY] }
  const fetch = vi.fn(async (url, init = {}) => {
    if (init.method !== 'PUT') return new Response(JSON.stringify(url === URL ? FACTORY : {}), { status: url === URL ? 200 : 404 })
    await new Promise((resolve) => (gate.release = resolve))
    const [status, body] = gate.reply
    return new Response(JSON.stringify(body), { status })
  })
  vi.stubGlobal('fetch', fetch)
  return { fetch, gate }
}

test('FE8: a wide route that fetches GET /api/factories/7 once, never polled, behind a skeleton; the title names it', async () => {
  vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
  const pending = renderAt('/projects/3/factories/7')
  expectSkeleton(screen.getByRole('status'))
  pending.unmount()

  vi.useFakeTimers()
  const fetch = mockFetch({ [`GET ${URL}`]: [200, FACTORY] })
  const { container } = renderAt('/projects/3/factories/7')
  await act(() => vi.advanceTimersByTimeAsync(0))
  expect(screen.getByRole('heading', { level: 1, name: 'default' })).toBeTruthy()
  await act(() => vi.advanceTimersByTimeAsync(10_000))
  expect(fetched(fetch).filter((url) => url === URL)).toHaveLength(1)
  expect(document.title).toBe('default · api-server · Claude Factories')
  expect(container.querySelector('main').className).not.toContain('max-w-6xl')
})

test('FE8: a 404, or a factory of another project (Q13), is the not-found page; another failure is the red alert', async () => {
  for (const [reply, heading] of [
    [[404, { detail: 'Factory #7 not found' }], 'Factory #7 not found'],
    [[200, { ...FACTORY, project_id: 4, project: 'web' }], 'Factory #7 not found'],
  ]) {
    mockFetch({ [`GET ${URL}`]: reply })
    const { unmount } = renderAt('/projects/3/factories/7')
    expect(await screen.findByRole('heading', { level: 1, name: heading })).toBeTruthy()
    expect(document.querySelector('.react-flow')).toBeNull()
    expect(document.title).toBe('Not found · Claude Factories')
    unmount()
  }
  mockFetch({ [`GET ${URL}`]: [500, { detail: 'boom' }] })
  renderAt('/projects/3/factories/7')
  expect((await screen.findByRole('alert')).textContent).toBe('boom')
})

test('FE9, 101: the breadcrumb, then the h1 with the name, the kind, an empty status, and Save', async () => {
  await open()
  const crumbs = within(screen.getByRole('navigation', { name: 'Breadcrumb' }))
  expect(crumbs.getAllByRole('link').map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
    ['personal', '/workspaces/2'],
    ['api-server', '/projects/3'],
    ['Workflows', '/projects/3/factories'],
  ])
  const current = crumbs.getByText('default')
  expect(current.getAttribute('aria-current')).toBe('page')
  expect(screen.getByRole('navigation', { name: 'Breadcrumb' }).textContent).toBe('personal › api-server › Workflows › default')
  const row = screen.getByRole('heading', { level: 1, name: 'default' }).parentElement
  // 101 AC18: the kind; 052: Files, then Save
  expect([...row.children].map((el) => el.tagName)).toEqual(['H1', 'P', 'P', 'BUTTON', 'BUTTON'])
  expect(status()).toBe('')
  expect(save().disabled).toBe(true)
})

test('101 AC18: the header shows the design\'s kind as muted text beside its name', async () => {
  for (const [kind, label] of [['workflow', 'Workflow'], ['automation', 'Automation']]) {
    const { unmount } = await open({}, { ...FACTORY, kind })
    const h1 = screen.getByRole('heading', { level: 1, name: 'default' })
    const note = h1.nextElementSibling
    expect(note.textContent).toBe(label)
    expect(note.className).toMatch(cls('text-muted'))
    unmount()
  }
})

test("103 AC24: an automation's header has a Runs link to its runs page, before Files; a workflow's has none", async () => {
  const auto = await open({}, { ...FACTORY, kind: 'automation' })
  const row = screen.getByRole('heading', { level: 1, name: 'default' }).parentElement
  const runs = within(row).getByRole('link', { name: 'Runs' })
  expect(runs.getAttribute('href')).toBe('/projects/3/factories/7/runs')
  expect([...row.querySelectorAll('a, button')].map((el) => el.textContent)).toEqual(['Runs', 'Files', 'Save'])
  auto.unmount()
  await open()
  expect(screen.queryByRole('link', { name: 'Runs' })).toBeNull()
})

test('FE10: each node is a card with an aria-hidden SVG icon, its title, and its summary; Controls and a dots Background', async () => {
  const graph = {
    nodes: [
      ...GRAPH.nodes,
      node('helper', 'custom_agent', 0, 400, agent('helper', 'haiku')),
      node('changes', 'any_changes', 300, 400),
      node('approved', 'approved', 600, 400),
      node('three', 'rounds_below', 900, 400, { n: 3 }),
    ],
    edges: GRAPH.edges,
  }
  await open({}, { ...FACTORY, graph })
  const card = (id) => {
    const el = flowNode(id)
    const svg = el.querySelector('svg')
    expect(svg.getAttribute('aria-hidden')).toBe('true')
    // the title and summary, as their `title` attributes give them whole
    return [...el.querySelectorAll('[title]')].map((t) => t.getAttribute('title'))
  }
  expect(card('start')).toEqual(['Start']) // and no summary
  expect(flowNode('start').textContent).toBe('Start')
  expect(card('spec-writer')).toEqual(['spec-writer', 'Spec writer · opus'])
  expect(card('builder')).toEqual(['builder', 'Builder · both · opus'])
  expect(card('review-security')).toEqual(['review-security', 'Reviewer · security · sonnet'])
  expect(card('approver')).toEqual(['approver', 'Approver · opus'])
  expect(card('helper')).toEqual(['helper', 'Custom agent · haiku'])
  expect(card('all-pass')).toEqual(['All reviews PASS?', 'Condition'])
  expect(card('changes')).toEqual(['Any review CHANGES?', 'Condition'])
  expect(card('rounds')).toEqual(['Rounds used < 2?', 'Condition'])
  expect(card('three')).toEqual(['Rounds used < 3?', 'Condition'])
  expect(card('approved')).toEqual(['Decision APPROVE?', 'Condition'])
  const controls = within(document.querySelector('.react-flow__controls'))
  for (const name of ['Zoom In', 'Zoom Out', 'Fit View', 'Toggle Interactivity']) expect(controls.getByRole('button', { name })).toBeTruthy()
  expect(document.querySelector('.react-flow__background .react-flow__background-pattern.dots')).toBeTruthy()
})

test('FE11: a condition has yes (success) and no (danger) source handles with their words; agents one in, one out; start one out', async () => {
  await open()
  const handles = (id, kind) => [...flowNode(id).querySelectorAll(`.react-flow__handle.${kind}`)]
  for (const id of ['all-pass', 'rounds']) {
    const [yes, no] = handles(id, 'source')
    expect(handles(id, 'source')).toHaveLength(2)
    expect([yes.dataset.handleid, yes.textContent, no.dataset.handleid, no.textContent]).toEqual(['yes', 'yes', 'no', 'no'])
    for (const name of ['bg-success', 'text-success']) expect(yes.className).toMatch(cls(name))
    for (const name of ['bg-danger', 'text-danger']) expect(no.className).toMatch(cls(name))
    expect(handles(id, 'target')).toHaveLength(1)
  }
  for (const id of ['spec-writer', 'builder', 'review-ux', 'approver']) {
    expect([handles(id, 'target').length, handles(id, 'source').length]).toEqual([1, 1])
    expect(handles(id, 'source')[0].dataset.handleid ?? null).toBeNull()
  }
  expect([handles('start', 'target').length, handles('start', 'source').length]).toEqual([0, 1])
})

test('FE12: the palette toggle has aria-expanded and aria-controls; Agents and Conditions hold draggable buttons in table order', async () => {
  await open()
  const toggle = screen.getByRole('button', { name: 'Palette' })
  const list = document.getElementById(toggle.getAttribute('aria-controls'))
  expect(toggle.getAttribute('aria-expanded')).toBe('true')
  const group = (name) => within(within(list).getByRole('region', { name })).getAllByRole('button')
  expect(group('Agents').map((b) => b.textContent)).toEqual(['Spec writer', 'Builder', 'Reviewer', 'Approver', 'Custom agent'])
  expect(group('Conditions').map((b) => b.textContent)).toEqual([
    'All reviews PASS', 'Any review CHANGES', 'Rounds used < N', 'Decision APPROVE',
  ])
  for (const b of [...group('Agents'), ...group('Conditions')]) {
    expect([b.tagName, b.getAttribute('draggable')]).toEqual(['BUTTON', 'true'])
  }
  fireEvent.click(toggle)
  expect(toggle.getAttribute('aria-expanded')).toBe('false')
  expect(list.hidden).toBe(true)
  expect(screen.queryByRole('button', { name: 'Builder' })).toBeNull()
  fireEvent.click(toggle)
  expect(list.hidden).toBe(false)
})

test('FE13: clicking Builder adds builder-2 at the viewport center, selected and unsaved; Rounds used < N adds n 2', async () => {
  const { fetch } = await open({ [`PUT ${URL}`]: [200, FACTORY] })
  boxes()
  const center = toFlow(BOX.left + BOX.width / 2, BOX.top + BOX.height / 2)
  fireEvent.click(palette('Builder'))
  await waitFor(() => expect(flowNodes()).toHaveLength(11))
  expect(flowNodes().at(-1).querySelector('[title="builder-2"]')).toBeTruthy()
  expect(status()).toBe('Unsaved changes')
  const p = panel()
  expect(p.getByRole('textbox', { name: 'Name' }).value).toBe('builder-2')
  expect(p.getByRole('combobox', { name: 'Side' }).value).toBe('both')
  expect(p.getByRole('combobox', { name: 'Model' }).value).toBe('inherit')
  expect(['Description', 'Tools', 'Prompt'].map((name) => p.getByRole('textbox', { name }).value)).toEqual(['', '', ''])

  fireEvent.click(palette('Rounds used < N'))
  await waitFor(() => expect(flowNodes()).toHaveLength(12))
  expect(panel().getByRole('spinbutton', { name: 'N' }).value).toBe('2')
  expect(document.querySelectorAll('.react-flow__node [title="Rounds used < 2?"]')).toHaveLength(2)

  fireEvent.click(save())
  await waitFor(() => expect(puts(fetch)).toHaveLength(1))
  const [, , , , , , , , , , added, rounds] = sent(puts(fetch)[0]).graph.nodes
  expect(added).toEqual({
    id: expect.any(String), type: 'builder', position: { x: expect.any(Number), y: expect.any(Number) },
    data: { name: 'builder-2', description: '', model: 'inherit', tools: [], prompt: '', side: 'both' },
  })
  expect(added.position.x).toBeCloseTo(center.x)
  expect(added.position.y).toBeCloseTo(center.y)
  expect(rounds).toMatchObject({ type: 'rounds_below', data: { n: 2 } })
  expect(rounds.id).not.toBe(added.id)
})

/** jsdom has no DataTransfer: a stand-in that keeps what dragstart sets for drop to read. */
function transfer() {
  const data = {}
  const types = []
  return {
    types,
    setData: (type, value) => {
      data[type] = value
      if (!types.includes(type)) types.push(type)
    },
    getData: (type) => data[type] ?? '',
  }
}

test('FE14: dragging a palette item onto the flow adds it at the drop point, through screenToFlowPosition', async () => {
  const { fetch } = await open({ [`PUT ${URL}`]: [200, FACTORY] })
  boxes()
  const dataTransfer = transfer()
  const target = document.querySelector('.react-flow')
  fireEvent.dragStart(palette('Approver'), { dataTransfer })
  expect(fireEvent.dragOver(target, { dataTransfer })).toBe(false) // cancelled: the flow takes the drop
  // jsdom has no DragEvent, so the point is set on the event by hand
  const drop = createEvent.drop(target, { dataTransfer })
  Object.defineProperties(drop, { clientX: { value: 300 }, clientY: { value: 200 } })
  const at = toFlow(300, 200)
  fireEvent(target, drop)
  await waitFor(() => expect(flowNodes()).toHaveLength(11))
  expect(status()).toBe('Unsaved changes')
  fireEvent.click(save())
  await waitFor(() => expect(puts(fetch)).toHaveLength(1))
  const added = sent(puts(fetch)[0]).graph.nodes.at(-1)
  expect([added.type, added.data.name]).toEqual(['approver', 'approver-2'])
  expect(added.position.x).toBeCloseTo(at.x)
  expect(added.position.y).toBeCloseTo(at.y)
})

test('FE15: each edge has a × at its midpoint named for its ends; it removes only that edge and marks the page unsaved', async () => {
  const { fetch } = await open({ [`PUT ${URL}`]: [200, FACTORY] })
  const buttons = screen.getAllByRole('button', { name: /^Delete edge / })
  expect(buttons).toHaveLength(14)
  expect(buttons.map((b) => b.textContent)).toEqual(Array(14).fill('×'))
  expect(buttons.map((b) => b.getAttribute('aria-label'))).toEqual(expect.arrayContaining([
    'Delete edge Start → spec-writer',
    'Delete edge review-ui → All reviews PASS?',
    'Delete edge All reviews PASS? → Rounds used < 2?',
    'Delete edge Rounds used < 2? → builder',
  ]))
  fireEvent.click(screen.getByRole('button', { name: 'Delete edge spec-writer → builder' }))
  await waitFor(() => expect(document.querySelectorAll('.react-flow__edge')).toHaveLength(13))
  expect(screen.queryByRole('button', { name: 'Delete edge spec-writer → builder' })).toBeNull()
  expect(flowNodes()).toHaveLength(10)
  expect(status()).toBe('Unsaved changes')
  fireEvent.click(save())
  await waitFor(() => expect(puts(fetch)).toHaveLength(1))
  expect(sent(puts(fetch)[0]).graph.edges.map((e) => e.id)).toEqual(GRAPH.edges.map((e) => e.id).filter((id) => id !== 'e2'))
})

/** Q10's sentences for start and a condition. */
const KINDS_ABOUT = {
  start: 'Where a run begins. Nothing leads into it, and its one output goes to the first agent.',
  all_pass: 'Yes when every verdict on the latest round is PASS, else no.',
}

test('FE16: the side panel shows the selected node\'s fields by kind, and a hint with none or several', async () => {
  await open()
  const hint = 'Select a node to edit it.'
  expect(panel().getByText(hint)).toBeTruthy()

  select('builder')
  const p = panel()
  const name = p.getByRole('textbox', { name: 'Name' })
  expect(name.value).toBe('builder')
  expect(document.getElementById(name.getAttribute('aria-describedby')).textContent).toBe('a-z, 0-9, and -')
  expect(p.getByRole('textbox', { name: 'Description' }).value).toBe('The builder.')
  const model = p.getByRole('combobox', { name: 'Model' })
  expect(optionLabels(model)).toEqual(['inherit', 'opus', 'sonnet', 'haiku'])
  expect(model.value).toBe('opus')
  const side = p.getByRole('combobox', { name: 'Side' })
  expect([optionLabels(side), side.value]).toEqual([['backend', 'frontend', 'both'], 'both'])
  expect(p.queryByRole('combobox', { name: 'Focus' })).toBeNull()
  expect(p.getByRole('textbox', { name: 'Tools' }).value).toBe('Read, Edit')
  const prompt = p.getByRole('textbox', { name: 'Prompt' })
  expect([prompt.tagName, prompt.value]).toEqual(['TEXTAREA', 'Input: a task id {{ test_cmd }}\n'])
  expect(prompt.className).toMatch(cls('font-mono'))

  select('review-ux')
  const focus = panel().getByRole('combobox', { name: 'Focus' })
  expect([optionLabels(focus), focus.value]).toEqual([['security', 'ux', 'ui', 'code', 'custom'], 'ux'])
  expect(panel().queryByRole('combobox', { name: 'Side' })).toBeNull()

  select('rounds')
  const n = panel().getByRole('spinbutton', { name: 'N' })
  expect([n.type, n.min, n.value]).toEqual(['number', '1', '2'])
  expect(panel().queryByRole('textbox')).toBeNull()

  for (const [id, sentence] of [
    ['start', KINDS_ABOUT.start],
    ['all-pass', KINDS_ABOUT.all_pass],
  ]) {
    select(id)
    expect(panel().getByText(sentence)).toBeTruthy()
    expect(panel().queryAllByRole('textbox')).toEqual([])
    expect(panel().queryAllByRole('combobox')).toEqual([])
    expect(panel().queryAllByRole('spinbutton')).toEqual([])
  }

  // several: Control held (React Flow's multi-selection key off a Mac) while clicking a second node
  select('builder')
  fireEvent.keyDown(document.body, { key: 'Control' })
  select('approver')
  fireEvent.keyUp(document.body, { key: 'Control' })
  await waitFor(() => expect(document.querySelectorAll('.react-flow__node.selected')).toHaveLength(2))
  expect(panel().getByText(hint)).toBeTruthy()
  expect(panel().queryAllByRole('textbox')).toEqual([])
})

test('FE17: an edit reaches the node at once: the card title follows Name, Tools stores a list while the field keeps the text', async () => {
  const { fetch } = await open({ [`PUT ${URL}`]: [200, FACTORY] })
  select('builder')
  fireEvent.change(panel().getByRole('textbox', { name: 'Name' }), { target: { value: 'make' } })
  expect(flowNode('builder').querySelector('[title="make"]').textContent).toBe('make')
  expect(status()).toBe('Unsaved changes')
  const tools = panel().getByRole('textbox', { name: 'Tools' })
  fireEvent.change(tools, { target: { value: 'Read, Grep' } })
  expect(tools.value).toBe('Read, Grep')
  pick(panel().getByRole('combobox', { name: 'Model' }), 'haiku')
  expect(flowNode('builder').querySelector('[title="Builder · both · haiku"]')).toBeTruthy()
  fireEvent.click(save())
  await waitFor(() => expect(puts(fetch)).toHaveLength(1))
  const builder = sent(puts(fetch)[0]).graph.nodes.find((n) => n.id === 'builder')
  expect(builder.data).toEqual({ ...agent('make', 'haiku', { side: 'both' }), tools: ['Read', 'Grep'], description: 'The builder.' })

  select('rounds')
  fireEvent.change(panel().getByRole('spinbutton', { name: 'N' }), { target: { value: '3' } })
  expect(flowNode('rounds').querySelector('[title="Rounds used < 3?"]')).toBeTruthy()
})

test('FE18: selecting, deselecting, and React Flow\'s measuring leave the page saved', async () => {
  await open()
  // every card is measured (visible) by now, through React Flow's dimension changes
  expect(flowNodes().every((el) => el.style.visibility === 'visible')).toBe(true)
  select('builder')
  await waitFor(() => expect(flowNode('builder').classList.contains('selected')).toBe(true))
  expect(panel().getByRole('textbox', { name: 'Name' })).toBeTruthy()
  fireEvent.click(document.querySelector('.react-flow__pane'))
  await waitFor(() => expect(flowNode('builder').classList.contains('selected')).toBe(false))
  expect(status()).toBe('')
  expect(save().disabled).toBe(true)
})

test('FE19: Save PUTs only the contract\'s keys with X-Requested-By, spins while pending, and on 200 is saved again', async () => {
  const { fetch, gate } = gatedFetch()
  renderAt('/projects/3/factories/7')
  await screen.findByRole('heading', { level: 1, name: 'default' })
  await waitFor(() => expect(document.querySelectorAll('.react-flow__edge')).toHaveLength(14))
  expect(save().disabled).toBe(true)
  select('builder') // React Flow's own keys (selected, measured) and start's deletable are on the nodes now
  fireEvent.click(screen.getByRole('button', { name: 'Delete edge Start → spec-writer' }))
  await waitFor(() => expect(status()).toBe('Unsaved changes'))
  expect(save().disabled).toBe(false)
  fireEvent.click(save())
  await waitFor(() => expect(puts(fetch)).toHaveLength(1))
  expect(save().getAttribute('aria-busy')).toBe('true')
  expect(save().querySelector('.motion-safe\\:animate-spin')).toBeTruthy()
  const [[, init]] = puts(fetch)
  expect(init.headers['X-Requested-By']).toBe('fctl')
  expect(sent(puts(fetch)[0])).toEqual({ graph: { nodes: GRAPH.nodes, edges: GRAPH.edges.slice(1) } })
  await act(async () => gate.release())
  await waitFor(() => expect(status()).toBe(''))
  expect(save().disabled).toBe(true)
  expect(save().getAttribute('aria-busy')).toBeNull()
})

test('FE20: Ctrl+S and ⌘+S are prevented; while unsaved they send the PUT, and with nothing unsaved no request', async () => {
  const { fetch } = await open({ [`PUT ${URL}`]: [200, FACTORY] })
  expect(press('s', { ctrlKey: true })).toBe(false)
  expect(press('s', { metaKey: true })).toBe(false)
  await act(() => new Promise((resolve) => setTimeout(resolve, 20)))
  expect(puts(fetch)).toEqual([])

  fireEvent.click(screen.getByRole('button', { name: 'Delete edge Start → spec-writer' }))
  await waitFor(() => expect(status()).toBe('Unsaved changes'))
  expect(press('s', { ctrlKey: true })).toBe(false)
  await waitFor(() => expect(status()).toBe(''))
  expect(puts(fetch)).toHaveLength(1)

  fireEvent.click(screen.getByRole('button', { name: 'Delete edge spec-writer → builder' }))
  await waitFor(() => expect(status()).toBe('Unsaved changes'))
  expect(press('s', { metaKey: true })).toBe(false)
  await waitFor(() => expect(status()).toBe(''))
  expect(puts(fetch)).toHaveLength(2)
  expect(sent(puts(fetch)[1]).graph.edges.map((e) => e.id)).not.toContain('e2')
})

test('FE21: a refused save shows its detail in an alert beside Save; the graph and unsaved state stay; the next attempt clears it', async () => {
  const { gate } = gatedFetch()
  gate.reply = [422, { detail: 'two agents are named builder' }]
  renderAt('/projects/3/factories/7')
  await screen.findByRole('heading', { level: 1, name: 'default' })
  await waitFor(() => expect(document.querySelectorAll('.react-flow__edge')).toHaveLength(14))
  select('spec-writer')
  fireEvent.change(panel().getByRole('textbox', { name: 'Name' }), { target: { value: 'builder' } })
  fireEvent.click(save())
  await waitFor(() => expect(gate.release).toBeTypeOf('function'))
  await act(async () => gate.release())
  const alert = await titleRow().findByRole('alert')
  expect(alert.textContent).toBe('two agents are named builder')
  expect(status()).toBe('Unsaved changes')
  expect(save().disabled).toBe(false)
  expect(flowNode('spec-writer').querySelector('[title="builder"]')).toBeTruthy()
  expect(panel().getByRole('textbox', { name: 'Name' }).value).toBe('builder')

  gate.release = null
  gate.reply = [200, FACTORY]
  fireEvent.click(save())
  await waitFor(() => expect(gate.release).toBeTypeOf('function'))
  expect(titleRow().queryByRole('alert')).toBeNull() // cleared as the attempt starts
  await act(async () => gate.release())
  await waitFor(() => expect(status()).toBe(''))
})

test('FE22: beforeunload is cancelled only while unsaved: not when saved, after a save, or after unmount', async () => {
  const unload = () => {
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    return event.defaultPrevented
  }
  const { unmount } = await open({ [`PUT ${URL}`]: [200, FACTORY] })
  expect(unload()).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Delete edge Start → spec-writer' }))
  await waitFor(() => expect(status()).toBe('Unsaved changes'))
  expect(unload()).toBe(true)
  fireEvent.click(save())
  await waitFor(() => expect(status()).toBe(''))
  expect(unload()).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Delete edge spec-writer → builder' }))
  await waitFor(() => expect(status()).toBe('Unsaved changes'))
  expect(unload()).toBe(true)
  unmount()
  expect(unload()).toBe(false)
})

test('FE23: the delete key removes a selected condition with its edges, unsaved; start isn\'t deletable', async () => {
  await open()
  select('start')
  await waitFor(() => expect(flowNode('start').classList.contains('selected')).toBe(true))
  press('Backspace')
  await act(() => new Promise((resolve) => setTimeout(resolve, 20)))
  expect(flowNode('start')).toBeTruthy()
  expect(document.querySelectorAll('.react-flow__edge')).toHaveLength(14)
  expect(status()).toBe('')

  select('rounds')
  await waitFor(() => expect(flowNode('rounds').classList.contains('selected')).toBe(true))
  press('Backspace')
  await waitFor(() => expect(flowNode('rounds')).toBeNull())
  expect(document.querySelectorAll('.react-flow__edge')).toHaveLength(11) // e12, e13, e14 went with it
  expect(status()).toBe('Unsaved changes')

  select('builder')
  await waitFor(() => expect(flowNode('builder').classList.contains('selected')).toBe(true))
  press('Delete')
  await waitFor(() => expect(flowNode('builder')).toBeNull())
  expect(document.querySelectorAll('.react-flow__edge')).toHaveLength(6) // e2 and e3–e6 went with it
})

test('round-1 review-ui: the first view is readable: 0.8× from the loop\'s left edge when wider than the flow, else centred at up to 1×', async () => {
  boxes() // the flow is 800 × 600 from the start; test/reactflow.js measures every node as 1 × 1
  const { unmount } = await open()
  await waitFor(() => expect(viewport().zoom).toBeCloseTo(0.8))
  const { x, y, zoom } = viewport()
  expect(x).toBeCloseTo(40) // Start, at x 0, sits 40 px in from the flow's left edge
  // the loop's bounds run from review-security (y −180) to review-code (y 180, 1 px tall): their middle is the flow's
  expect(y + ((-180 + 181) / 2) * zoom).toBeCloseTo(300)
  unmount()

  await open({}, { ...FACTORY, graph: { nodes: GRAPH.nodes.slice(0, 2), edges: GRAPH.edges.slice(0, 1) } })
  await waitFor(() => expect(viewport().zoom).toBeCloseTo(1))
  // Start (0, 0) to spec-writer (250, 0), 1 px each: 251 × 1, centred in 800 × 600
  expect(viewport().x).toBeCloseTo((800 - 251) / 2)
  expect(viewport().y).toBeCloseTo((600 - 1) / 2)
})

test('round-1 review-ux: a refused save\'s list detail says which node field it points at', async () => {
  const detail = [{ type: 'int_type', loc: ['body', 'graph', 'nodes', 8, 'rounds_below', 'data', 'n'], msg: 'Input should be a valid integer' }]
  const { fetch } = await open({ [`PUT ${URL}`]: [422, { detail }] })
  select('rounds')
  fireEvent.change(panel().getByRole('spinbutton', { name: 'N' }), { target: { value: '' } })
  fireEvent.click(save())
  expect((await titleRow().findByRole('alert')).textContent).toBe('nodes.8.rounds_below.data.n: Input should be a valid integer')
  expect(sent(puts(fetch)[0]).graph.nodes[8]).toMatchObject({ id: 'rounds', data: { n: null } })
  expect(status()).toBe('Unsaved changes')
})

// --- 052: the Files dialog -----------------------------------------------------------------

const FILES_URL = '/api/factories/7/files'
const FILES = [
  { path: '.claude/skills/factory/SKILL.md', content: '---\nname: factory\n---\n' },
  { path: '.claude/agents/spec-writer.md', content: '---\nname: spec-writer\n---\n' },
]
const NOTE = 'Showing the last saved design. Save to include your changes.'
const filesGets = (fetch) => fetch.mock.calls.filter(([url, init]) => url === FILES_URL && (init?.method ?? 'GET') === 'GET')
/** Opens Files and waits for its list. */
async function openFiles() {
  fireEvent.click(screen.getByRole('button', { name: 'Files' }))
  const dialog = screen.getByRole('dialog', { name: 'Files' })
  await within(dialog).findByRole('button', { name: FILES[0].path })
  return dialog
}

test('FE1: the title row has Files before Save; it opens a modal dialog headed Files and GETs the files', async () => {
  const { fetch } = await open({ [`GET ${FILES_URL}`]: [200, FILES] })
  const buttons = titleRow().getAllByRole('button').map((b) => b.textContent)
  expect(buttons).toEqual(['Files', 'Save'])
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(filesGets(fetch)).toEqual([])
  const dialog = await openFiles()
  expect(dialog.tagName).toBe('DIALOG')
  expect(dialog.open).toBe(true)
  expect(within(dialog).getByRole('heading', { level: 2 }).textContent).toBe('Files')
  expect(filesGets(fetch)).toHaveLength(1)
})

test('FE10: with unsaved changes the dialog says it shows the last saved design; saved, it doesn\'t', async () => {
  await open({ [`GET ${FILES_URL}`]: [200, FILES], [`PUT ${URL}`]: [200, FACTORY] })
  let dialog = await openFiles()
  expect(within(dialog).queryByText(NOTE)).toBeNull()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }))

  fireEvent.click(screen.getByRole('button', { name: 'Delete edge Start → spec-writer' }))
  await waitFor(() => expect(status()).toBe('Unsaved changes'))
  dialog = await openFiles()
  expect(within(dialog).getByText(NOTE)).toBeTruthy()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }))

  fireEvent.click(save())
  await waitFor(() => expect(status()).toBe(''))
  dialog = await openFiles()
  expect(within(dialog).queryByText(NOTE)).toBeNull()
})

test('FE11: Close closes the dialog; opening Files again sends a fresh GET', async () => {
  const { fetch } = await open({ [`GET ${FILES_URL}`]: [200, FILES] })
  const dialog = await openFiles()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }))
  expect(dialog.open).toBe(false)
  expect(screen.queryByRole('dialog')).toBeNull()
  await openFiles()
  expect(filesGets(fetch)).toHaveLength(2)
})
