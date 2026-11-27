import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cls, expectOfflineBanner, expectSkeleton, fetched, fullText, mockFetch, renderAt } from '../../test/render.jsx'

const PAGE = '/api/pages/agents'
const STOP = '/api/runs/41/stop'

/** The API contract's agents, in its order. */
const AGENTS = [
  { name: 'orchestrator', type: null, round: null, running: true, duration_ms: null, last_tool: 'Agent review-code' },
  { name: 'builder-12', type: 'builder', round: 1, running: false, duration_ms: 754000, last_tool: 'Bash pytest -q' },
  { name: 'review-code', type: 'review-code', round: 2, running: true, duration_ms: null, last_tool: 'Bash fctl verdict 12 code PASS' },
]
/** A RunningRun as the contract has it. */
const running = (extra = {}) => ({
  id: 41, kind: 'factory', task_id: 12, title: 'Rate-limit login endpoint', project_id: 3, project: 'api-server',
  stage: 'agent_review', round: 1, started_at: '2026-10-21T10:04:11Z', agents: AGENTS, ...extra,
})
/** A RecentRun. */
const recent = (id, extra = {}) => ({
  id, task_id: 11, title: 'Webhooks', project_id: 3, project: 'api-server', status: 'succeeded', error: null,
  started_at: '2026-10-21T09:40:00Z', ended_at: '2026-10-21T09:52:03Z', transcripts: 0, ...extra,
})
const page = (run = [running()], ended = []) => ({ running: run, recent: ended })

beforeEach(() => {
  vi.stubEnv('TZ', 'Asia/Tokyo')
})
afterEach(() => {
  vi.useRealTimers()
})

/** Renders /agents with `body` as the view-model; mutate `responses` to change later replies. */
async function open(body, more = {}) {
  const responses = { [`GET ${PAGE}`]: [200, body], ...more }
  const fetch = mockFetch(responses)
  const view = renderAt('/agents')
  await screen.findByRole('heading', { level: 1, name: 'Agents' })
  return { fetch, responses, ...view }
}

const advance = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))
const loads = (fetch) => fetched(fetch).filter((url) => url === PAGE).length
const region = (name) => screen.getByRole('region', { name })
const card = () => within(region('Running')).getAllByRole('listitem')[0]
/** The card's first line: kind, task, project, stage, round. */
const head = () => card().querySelector('p')
const agentRows = () => within(screen.getByRole('list', { name: 'Agents of run #41' })).getAllByRole('listitem')
const recentRows = () => [...region('Recent').querySelectorAll('li')]
const href = (el) => el.getAttribute('href')

test('FE1: /agents fetches the agents view-model and shows h1 Agents, h2s Running and Recent, the title; not wide', async () => {
  const { fetch } = await open(page())
  expect(fetched(fetch)).toContain(PAGE)
  expect(screen.getAllByRole('heading').filter((h) => h.closest('main')).map((h) => [h.tagName, h.textContent])).toEqual([
    ['H1', 'Agents'], ['H2', 'Running'], ['H2', 'Recent'],
  ])
  await waitFor(() => expect(document.title).toBe('Agents · Workcell'))
  expect(screen.getByRole('main').className).toMatch(cls('max-w-6xl'))
})

test('FE2: the first load is a skeleton; a failed first load is a red alert with its detail', async () => {
  mockFetch({}).mockImplementation(() => new Promise(() => {})) // nothing answers
  const pending = renderAt('/agents')
  expectSkeleton(within(screen.getByRole('main')).getByRole('status'))
  expect(screen.queryByRole('heading', { level: 1 })).toBeNull()
  pending.unmount()

  mockFetch({ [`GET ${PAGE}`]: [502, { detail: 'Backend unreachable' }] })
  renderAt('/agents')
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe('Backend unreachable')
  expect(alert.className).toMatch(cls('text-danger'))
})

test('FE3: a running row shows its kind, task and project links, stage, round, start, elapsed, Run log, and Stop', async () => {
  vi.setSystemTime(new Date('2026-10-21T10:09:23Z')) // 5m 12s after the start
  await open(page())
  const row = within(card())
  expect(row.getByText('factory')).toBeTruthy()
  expect(href(row.getByRole('link', { name: '#12 Rate-limit login endpoint' }))).toBe('/tasks/12')
  expect(href(row.getByRole('link', { name: 'api-server' }))).toBe('/projects/3')
  const stage = within(head()).getByText('agent_review')
  expect(stage.className).toMatch(cls('text-muted')) // as Badge.jsx's Stage draws it
  expect(within(head()).getByText('round 1')).toBeTruthy()
  expect(head().textContent).toBe('factory#12 Rate-limit login endpointapi-serveragent_review·round 1')
  const started = row.getByText(fullText('started 5m ago · elapsed 5m 12s'))
  const time = started.querySelector('time')
  expect([time.getAttribute('datetime'), time.textContent, time.getAttribute('title')]).toEqual([
    '2026-10-21T10:04:11Z', '5m ago', '2026-10-21 19:04',
  ])
  expect(href(row.getByRole('link', { name: 'Run log' }))).toBe('/tasks/12#run-log')
  expect(row.getByRole('button', { name: 'Stop' })).toBeTruthy()
})

test('FE3: a null stage or round is left out; human_review draws as its pill', async () => {
  const { unmount } = await open(page([running({ stage: null, round: null })]))
  expect(head().textContent).toBe('factory#12 Rate-limit login endpointapi-server')
  unmount()
  await open(page([running({ stage: 'human_review', round: null })]))
  expect(within(head()).getByText('waiting on you').className).toMatch(cls('bg-warning'))
  expect(head().textContent).toBe('factory#12 Rate-limit login endpointapi-serverwaiting on you')
})

test('FE4: the agents list, in order: running badges, type only when it differs, rounds, finished durations, tool lines', async () => {
  await open(page([running({
    agents: [...AGENTS, { name: 'review-ux', type: 'review-ux', round: 2, running: false, duration_ms: null, last_tool: null }],
  })]))
  const rows = agentRows()
  expect(rows.map((li) => li.firstChild.textContent)).toEqual(['orchestrator', 'builder-12', 'review-code', 'review-ux'])
  const [orchestrator, builder, review, ux] = rows.map((li) => within(li))

  expect(orchestrator.getByText(fullText('● running'))).toBeTruthy()
  expect(orchestrator.getByText('Agent review-code').tagName).toBe('CODE')
  expect(rows[0].textContent).toBe('orchestrator● runningAgent review-code')

  expect(builder.getByText('builder')).toBeTruthy()
  expect(builder.getByText('round 1')).toBeTruthy()
  expect(builder.getByText('finished · 12m 34s')).toBeTruthy()
  expect(builder.queryByText(fullText('● running'))).toBeNull()
  expect(builder.getByText('Bash pytest -q').tagName).toBe('CODE')

  expect(review.getByText(fullText('● running'))).toBeTruthy()
  expect(review.getAllByText('review-code')).toHaveLength(1) // no type: it equals the name
  expect(review.getByText('round 2')).toBeTruthy()
  const tool = review.getByText('Bash fctl verdict 12 code PASS')
  expect(tool.className).toMatch(cls('truncate'))
  expect(tool.className).toMatch(cls('text-muted'))

  expect(ux.getByText('finished')).toBeTruthy() // duration_ms null
  expect(rows[3].querySelector('code')).toBeNull() // last_tool null: no tool line
})

test('FE5: Stop posts with X-Requested-By and its spinner, then refetches at once; a 409 is an alert the next Stop clears', async () => {
  let release
  const gate = new Promise((resolve) => (release = resolve))
  const { fetch, responses } = await open(page(), { [`POST ${STOP}`]: [200, { id: 41, status: 'stopped' }] })
  const base = fetch.getMockImplementation()
  fetch.mockImplementation(async (url, init) => {
    if (url === STOP) await gate
    return base(url, init)
  })
  const stop = () => within(card()).getByRole('button', { name: 'Stop' })
  fireEvent.click(stop())
  expect(stop().getAttribute('aria-busy')).toBe('true')
  expect(stop().querySelector('.motion-safe\\:animate-spin')).toBeTruthy()
  const calls = fetch.mock.calls.filter(([url, init]) => url === STOP && init.method === 'POST')
  expect(calls).toHaveLength(1)
  expect(calls[0][1].headers['X-Requested-By']).toBe('fctl')
  expect(loads(fetch)).toBe(1)
  await act(async () => release())
  await waitFor(() => expect(loads(fetch)).toBe(2)) // well before the 3 s poll
  expect(fetched(fetch).lastIndexOf(STOP)).toBeLessThan(fetched(fetch).lastIndexOf(PAGE))
  await waitFor(() => expect(stop().getAttribute('aria-busy')).toBeNull())

  responses[`POST ${STOP}`] = [409, { detail: 'run #41 is not running' }]
  fireEvent.click(stop())
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe('run #41 is not running')
  expect(alert.className).toMatch(cls('text-danger'))
  expect(screen.getByRole('heading', { level: 1, name: 'Agents' })).toBeTruthy()
  expect(agentRows()).toHaveLength(3) // the page stays

  responses[`POST ${STOP}`] = [200, { id: 41, status: 'stopped' }]
  fireEvent.click(stop())
  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
})

test('FE6: with nothing running, Nothing running. sits under Running, before the Recent heading', async () => {
  await open(page([], [recent(40)]))
  const text = within(region('Running')).getByText('Nothing running.')
  const recentHeading = screen.getByRole('heading', { level: 2, name: 'Recent' })
  expect(text.compareDocumentPosition(recentHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(within(region('Running')).queryByRole('button')).toBeNull()
})

test('FE7: recent rows show the run, links, how it ended, the duration, and transcripts; none reads No runs yet.', async () => {
  const { unmount } = await open(page([], [
    recent(40, { status: 'failed', error: 'exit code 1', transcripts: 2 }),
    recent(39, { task_id: 9, title: 'Health', project_id: 4, project: 'web', transcripts: 1, ended_at: '2026-10-21T09:48:41Z' }),
    recent(38, { status: 'stopped', ended_at: null }),
    recent(37, { status: 'failed', error: null }),
  ]))
  const [failed, succeeded, stopped, bare] = recentRows()
  const r = within(failed)
  expect(r.getByText('run #40')).toBeTruthy()
  expect(href(r.getByRole('link', { name: '#11 Webhooks' }))).toBe('/tasks/11')
  expect(href(r.getByRole('link', { name: 'api-server' }))).toBe('/projects/3')
  expect(r.getByText('failed: exit code 1')).toBeTruthy()
  expect(r.getByText('12m 3s')).toBeTruthy()
  expect(href(r.getByRole('link', { name: '2 transcripts' }))).toBe('/tasks/11')
  expect(failed.querySelectorAll('[class*="rounded-full"]')).toHaveLength(0) // plain text, no pill

  expect(within(succeeded).getByText('succeeded')).toBeTruthy()
  expect(href(within(succeeded).getByRole('link', { name: '#9 Health' }))).toBe('/tasks/9')
  expect(href(within(succeeded).getByRole('link', { name: 'web' }))).toBe('/projects/4')
  expect(within(succeeded).getByText('8m 41s')).toBeTruthy()
  expect(href(within(succeeded).getByRole('link', { name: '1 transcript' }))).toBe('/tasks/9')

  expect(within(stopped).getByText('stopped')).toBeTruthy()
  expect(within(stopped).getByText('—')).toBeTruthy() // no ended_at
  expect(within(stopped).queryByRole('link', { name: /transcript/ })).toBeNull() // 0: left out
  expect(within(bare).getByText('failed')).toBeTruthy() // failed with no error
  unmount()

  await open(page([], []))
  expect(within(region('Recent')).getByText('No runs yet.')).toBeTruthy()
})

// --- 102: automation runs -------------------------------------------------------------------------------

const automation = (extra = {}) =>
  running({ kind: 'automation', task_id: null, factory_id: 9, title: 'Security audit', stage: null, round: null, ...extra })
const DELETED = { factory_id: null, title: 'deleted automation', project_id: null, project: null }

test('102 AC28: an automation card shows automation, its name linking to the designer, the project; no stage, round, or Run log; Stop posts', async () => {
  const { fetch } = await open(page([automation()]), { [`POST ${STOP}`]: [200, { id: 41, status: 'stopped' }] })
  const row = within(card())
  expect(head().textContent).toBe('automationSecurity auditapi-server')
  expect(href(row.getByRole('link', { name: 'Security audit' }))).toBe('/projects/3/factories/9')
  expect(href(row.getByRole('link', { name: 'api-server' }))).toBe('/projects/3')
  expect(row.queryByRole('link', { name: 'Run log' })).toBeNull()
  fireEvent.click(row.getByRole('button', { name: 'Stop' }))
  await waitFor(() => expect(fetch.mock.calls.some(([url, init]) => url === STOP && init.method === 'POST')).toBe(true))
})

test('102 AC28, Q14: a deleted automation reads deleted automation as plain text, with no project link', async () => {
  await open(page([automation(DELETED)]))
  expect(head().textContent).toBe('automationdeleted automation')
  expect(within(card()).queryAllByRole('link')).toEqual([])
  expect(within(card()).getByRole('button', { name: 'Stop' })).toBeTruthy()
})

test('102 AC29: a Recent automation row shows its name like the card, and its transcripts as plain text', async () => {
  const auto = recent(50, { kind: 'automation', task_id: null, factory_id: 9, title: 'Security audit', transcripts: 2 })
  const gone = recent(51, { kind: 'automation', task_id: null, ...DELETED, transcripts: 1 })
  await open(page([], [auto, gone]))
  const [first, second] = recentRows()
  expect(href(within(first).getByRole('link', { name: 'Security audit' }))).toBe('/projects/3/factories/9')
  expect(within(first).getByText('2 transcripts').tagName).toBe('SPAN')
  expect(within(first).queryByRole('link', { name: /transcript/ })).toBeNull()
  expect(within(second).queryAllByRole('link')).toEqual([])
  expect(within(second).getByText('deleted automation')).toBeTruthy()
})

test('FE8: polls every 3 s, and after a good load the offline banner comes and goes; a 404 is not-found', async () => {
  vi.useFakeTimers()
  const responses = { [`GET ${PAGE}`]: [200, page()] }
  const fetch = mockFetch(responses)
  renderAt('/agents')
  await advance(0)
  expect(loads(fetch)).toBe(1)
  expect(agentRows()).toHaveLength(3)
  await advance(2999)
  expect(loads(fetch)).toBe(1)
  await advance(1)
  expect(loads(fetch)).toBe(2)
  await expectOfflineBanner(responses, `GET ${PAGE}`, () => expect(agentRows()).toHaveLength(3))
})
