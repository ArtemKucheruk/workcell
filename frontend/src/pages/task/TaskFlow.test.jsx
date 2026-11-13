import '../../test/reactflow.js'
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { cls, fetched, mockFetch, renderAt } from '../../test/render.jsx'

// 089: the task page's Factory section (TaskFlow), rendered through the page with both APIs mocked

// Here the nodes arrive with React Flow's first render, so they're observed before its pane effect sets the domNode
// that measuring needs. A browser's ResizeObserver reports later; the shared mock reports at once, so defer it here.
const SyncObserver = globalThis.ResizeObserver
globalThis.ResizeObserver = class extends SyncObserver {
  observe(target) {
    queueMicrotask(() => super.observe(target))
  }
}

const PAGE = '/api/pages/tasks/12'
const FLOW = `${PAGE}/flow`
const FOCUS = ['security', 'ux', 'ui', 'code']
const node = (id, type, x, y, data = {}) => ({ id, type, position: { x, y }, data })
const agent = (name, extra = {}) => ({ name, description: '', model: 'opus', tools: [], prompt: '', ...extra })
const edge = (id, source, target, sourceHandle = null) => ({ id, source, sourceHandle, target })
/** docs/data-model-and-api.md §6.1's default graph. */
const GRAPH = {
  nodes: [
    node('start', 'start', 0, 0),
    node('spec-writer', 'spec_writer', 250, 0, agent('spec-writer')),
    node('builder', 'builder', 550, 0, agent('builder', { side: 'both' })),
    ...FOCUS.map((focus, i) => node(`review-${focus}`, 'reviewer', 850, i * 120 - 180, agent(`review-${focus}`, { focus }))),
    node('all-pass', 'all_pass', 1150, 0),
    node('rounds', 'rounds_below', 1450, 160, { n: 2 }),
    node('approver', 'approver', 1750, 0, agent('approver')),
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
const EMPTY = { spec_md: null, spec_html: null, build_md: null, build_html: null, files: null, additions: null,
  deletions: null, diff_url: null, verdict: null, comments: [], decisions: [], answer: null, why: null, transcripts: [] }
const idle = { state: 'idle', label: 'not reached', current: false, result: EMPTY }
const at = (state, label, extra = {}) => ({ state, label, current: false, result: { ...EMPTY, ...extra } })
const transcript = (id, agent_type) => ({
  id, run_id: 41, round: 1, agent_type, name: null, model: 'claude-opus-4-1', turns: 3, input_tokens: 10,
  cache_read_tokens: 20, output_tokens: 30, started_at: '2026-10-17T10:00:00Z', ended_at: '2026-10-17T10:00:12Z',
})
const verdict = (v, body) => ({ verdict: v, body_md: body, body_html: `<p>${body}</p>\n` })

/** Round 1 in agent review: security PASS, code CHANGES, ux and ui running. */
const ROUND1 = {
  graph: GRAPH, source: null, rounds: [1], round: 1,
  nodes: {
    ...Object.fromEntries(GRAPH.nodes.map((n) => [n.id, idle])),
    start: at('done', 'done'),
    'spec-writer': at('done', 'done', { spec_md: '# S', spec_html: '<h1>S</h1>\n' }),
    builder: at('done', 'done', {
      build_md: 'Token **bucket**', build_html: '<p>Token <strong>bucket</strong></p>\n', files: 2, additions: 10,
      deletions: 1, diff_url: '/tasks/12/review?round=1&tab=files', transcripts: [transcript(5, 'builder')],
    }),
    'review-security': at('done', 'PASS', { verdict: verdict('PASS', 'fine') }),
    'review-code': at('changes', 'CHANGES', {
      verdict: verdict('CHANGES', 'Split the handler'),
      comments: [{ path: 'a.py', line: 4, side: 'new', body_md: 'here', body_html: '<p>here</p>\n' }],
    }),
    'review-ux': { ...at('running', 'running'), current: true },
    'review-ui': { ...at('running', 'running'), current: true },
  },
}
/** Round 2's rework: the builder running, round 1's verdicts gone. */
const ROUND2 = {
  ...ROUND1, rounds: [1, 2], round: 2,
  nodes: {
    ...ROUND1.nodes,
    builder: { ...at('running', 'running'), current: true },
    ...Object.fromEntries(FOCUS.map((f) => [`review-${f}`, idle])),
  },
}
const TASK = {
  id: 12, project_id: 3, project: 'api', workspace_id: 2, workspace: 'personal', title: 'Rate-limit login',
  status: 'in_progress', stage: 'agent_review', branch: 'factory/12-x', worktree_path: '/w',
  description_md: '', description_html: '', spec_md: null, spec_html: '',
}
const taskPage = (run = null) => ({
  task: TASK, can_run: true, hint: null, run, takeover: null, rounds: [], approver: null, history: [],
  transcripts: [], blocked_by: [], blocks: [], project_tasks: [],
})
const running = { id: 41, status: 'running', error: null, session_id: 's', started_at: '2026-10-18T01:02:00Z' }
const LOG = '/api/runs/41/log?after=0'

afterEach(() => {
  vi.useRealTimers()
})

async function open(flow = ROUND1, more = {}) {
  const responses = { [`GET ${PAGE}`]: [200, taskPage()], [`GET ${FLOW}`]: [200, flow], ...more }
  const fetch = mockFetch(responses)
  renderAt('/tasks/12')
  await screen.findByRole('heading', { level: 1 })
  if (flow.graph) await waitFor(() => expect(document.querySelectorAll('.react-flow__edge')).toHaveLength(14))
  return { fetch, responses }
}

const flowNode = (id) => document.querySelector(`.react-flow__node[data-id="${id}"]`)
const region = (name) => screen.queryByRole('region', { name })
const flowLoads = (fetch) => fetched(fetch).filter((url) => url.startsWith(FLOW))
const advance = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))

test('AC21: a Factory section sits between the header and Description', async () => {
  await open()
  const regions = screen.getAllByRole('region').map((el) => el.getAttribute('aria-labelledby')).filter((id) => id?.startsWith('task-'))
  expect(regions.slice(0, 5)).toEqual(['task-factory', 'task-description', 'task-blocked-by', 'task-blocks', 'task-spec'])
  expect(within(region('Factory')).getByRole('heading', { level: 2 }).textContent).toBe('Factory')
  expect(document.querySelector('main header').compareDocumentPosition(region('Factory')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

test('AC21, AC31: a standalone task (graph null) has no Factory section, and the page reads as before', async () => {
  await open({ graph: null, source: null, rounds: [1], round: 1, nodes: {} })
  await waitFor(() => expect(screen.getByRole('region', { name: 'Description' })).toBeTruthy())
  expect(region('Factory')).toBeNull()
  expect(document.querySelector('.react-flow')).toBeNull()
})

test('AC22: the graph is read-only: nothing drags, connects, or deletes, and no edge has a ×', async () => {
  await open()
  expect(document.querySelectorAll('.react-flow__node')).toHaveLength(10)
  expect(document.querySelectorAll('.react-flow__node.draggable')).toHaveLength(0)
  expect(document.querySelectorAll('.react-flow__handle.connectable')).toHaveLength(0)
  expect(screen.queryAllByRole('button', { name: /^Delete edge / })).toEqual([])
  for (const key of ['Backspace', 'Delete']) {
    flowNode('builder').focus()
    fireEvent.keyDown(flowNode('builder'), { key })
    fireEvent.keyDown(document.querySelector('.react-flow'), { key })
  }
  await act(() => Promise.resolve())
  expect(document.querySelectorAll('.react-flow__node')).toHaveLength(10)
  expect(document.querySelectorAll('.react-flow__edge')).toHaveLength(14)
})

test('AC23: each node shows its state as an icon and a label; its accessible name has the title and state', async () => {
  await open()
  const text = (id) => flowNode(id).textContent
  expect(text('review-security')).toContain('✓PASS')
  expect(text('review-code')).toContain('✗CHANGES')
  expect(text('review-ux')).toContain('●running')
  expect(text('approver')).toContain('○not reached')
  expect(flowNode('review-code').getAttribute('aria-label')).toBe('review-code: CHANGES')
  expect(flowNode('all-pass').getAttribute('aria-label')).toBe('All reviews PASS?: not reached')
  const label = within(flowNode('review-code')).getByText('CHANGES')
  expect(label.className).toMatch(cls('text-danger'))
  expect(label.querySelector('[aria-hidden="true"]').textContent).toBe('✗')
})

test('AC23: failed, escalated, and an answered condition each show their icon', async () => {
  await open({
    ...ROUND1,
    nodes: { ...ROUND1.nodes, 'review-ux': at('failed', 'failed'), approver: at('escalated', 'ESCALATE'),
      'all-pass': at('done', 'no', { answer: 'no', why: 'code asked for changes' }) },
  })
  expect(flowNode('review-ux').textContent).toContain('!failed')
  expect(flowNode('approver').textContent).toContain('▲ESCALATE')
  expect(flowNode('all-pass').textContent).toContain('→no')
})

test('AC24: the current nodes have a ring and aria-current="step"; the running dot pulses only with motion allowed', async () => {
  await open()
  const current = [...document.querySelectorAll('.react-flow__node[aria-current="step"]')].map((el) => el.dataset.id)
  expect(current.sort()).toEqual(['review-ui', 'review-ux'])
  expect(flowNode('review-ux').firstElementChild.className).toMatch(cls('ring-2'))
  expect(flowNode('review-code').firstElementChild.className).not.toMatch(cls('ring-2'))
  const dot = within(flowNode('review-ux')).getByText('●')
  expect(dot.className).toMatch(cls('motion-safe:animate-pulse'))
  expect(dot.className).not.toMatch(cls('animate-pulse'))
})

test('AC25: clicking a reviewer opens its result panel; another node replaces it; Close closes it', async () => {
  await open()
  fireEvent.click(flowNode('review-code'))
  const panel = region('review-code result')
  expect(within(panel).getByText('CHANGES', { selector: 'strong' })).toBeTruthy()
  expect(within(panel).getByText('Split the handler').tagName).toBe('P')
  expect(within(within(panel).getByRole('list', { name: 'Comments' })).getByText('a.py:4')).toBeTruthy()
  fireEvent.click(flowNode('review-security'))
  expect(region('review-code result')).toBeNull()
  expect(within(region('review-security result')).getByText('fine')).toBeTruthy()
  fireEvent.click(within(region('review-security result')).getByRole('button', { name: 'Close' }))
  expect(region('review-security result')).toBeNull()
})

test('AC26: nodes are tab stops; Enter on one opens its panel and Esc in the panel closes it', async () => {
  await open()
  const nodes = [...document.querySelectorAll('.react-flow__node')]
  expect(nodes.map((el) => el.getAttribute('tabindex'))).toEqual(Array(10).fill('0'))
  flowNode('approver').focus()
  fireEvent.keyDown(flowNode('approver'), { key: 'Enter' })
  const panel = region('approver result')
  expect(within(panel).getByText('No decision yet.')).toBeTruthy()
  fireEvent.keyDown(within(panel).getByRole('button', { name: 'Close' }), { key: 'Escape' })
  expect(region('approver result')).toBeNull()
})

test('AC27: the Round select lists the rounds, defaults to the latest, and refetches with ?round=; the panel follows', async () => {
  const { fetch } = await open(ROUND2, { [`GET ${FLOW}?round=1`]: [200, ROUND1] })
  const select = screen.getByRole('combobox', { name: 'Round' })
  expect(select.tagName).toBe('SELECT')
  expect([...select.options].map((o) => o.value)).toEqual(['1', '2'])
  expect(select.value).toBe('2')
  fireEvent.click(flowNode('review-code'))
  expect(within(region('review-code result')).getByText('No verdict yet.')).toBeTruthy()
  fireEvent.change(select, { target: { value: '1' } })
  await waitFor(() => expect(flowNode('review-code').textContent).toContain('CHANGES'))
  expect(flowLoads(fetch)).toEqual([FLOW, `${FLOW}?round=1`])
  expect(select.value).toBe('1')
  expect(within(region('review-code result')).getByText('Split the handler')).toBeTruthy()
  expect(flowNode('builder').textContent).toContain('✓done')
})

test('AC28: while the run runs the flow refetches every 3 s, and the selector follows a new latest round', async () => {
  vi.useFakeTimers()
  const responses = {
    [`GET ${PAGE}`]: [200, taskPage(running)], [`GET ${FLOW}`]: [200, ROUND1], [`GET ${LOG}`]: [200, { next: 0, lines: [] }],
  }
  const fetch = mockFetch(responses)
  renderAt('/tasks/12')
  await advance(0)
  expect(flowLoads(fetch)).toHaveLength(1)
  responses[`GET ${FLOW}`] = [200, ROUND2]
  await advance(3000)
  expect(flowLoads(fetch)).toEqual([FLOW, FLOW])
  expect(screen.getByRole('combobox', { name: 'Round' }).value).toBe('2')
})

test('AC28: with no running run the flow loads once', async () => {
  vi.useFakeTimers()
  const fetch = mockFetch({ [`GET ${PAGE}`]: [200, taskPage()], [`GET ${FLOW}`]: [200, ROUND1] })
  renderAt('/tasks/12')
  await advance(0)
  await advance(30000)
  expect(flowLoads(fetch)).toEqual([FLOW])
})

test('AC29: the builder panel links to its diff and shows its notes; each transcript links with its stats', async () => {
  await open()
  fireEvent.click(flowNode('builder'))
  const panel = region('builder result')
  expect(within(panel).getByRole('link', { name: 'Diff' }).getAttribute('href')).toBe('/tasks/12/review?round=1&tab=files')
  expect(within(panel).getByText('2 files +10 −1')).toBeTruthy()
  expect(within(panel).getByText('bucket').tagName).toBe('STRONG')
  const list = within(panel).getByRole('list', { name: 'Transcripts' })
  expect(within(list).getByRole('link', { name: 'builder' }).getAttribute('href')).toBe('/transcripts/5')
  expect(list.textContent).toBe('builder · claude-opus-4-1 · 3 turns · in 10 · cache 20 · out 30 · 12s')
})
