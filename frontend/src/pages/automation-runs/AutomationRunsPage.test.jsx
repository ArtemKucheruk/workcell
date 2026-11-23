import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { cls, expectOfflineBanner, expectSkeleton, fetched, mockFetch, renderAt } from '../../test/render.jsx'

const PAGE = '/api/pages/factories/7/runs'
const PATH = '/projects/3/factories/7/runs'
const RUN = '/api/factories/7/run'
const STOP = (id) => `/api/runs/${id}/stop`
const LOG = (id, after) => `/api/runs/${id}/log?after=${after}`
const AUTOMATION = { id: 7, name: 'Security audit', project_id: 3, project: 'api-server', workspace_id: 2, workspace: 'personal' }
const ACCOUNTS = [
  { id: 1, label: 'a@x', active: true, five_hour: { utilization: 0.42, resets_at: 1, status: 'allowed' }, seven_day: null },
  { id: 2, label: 'b@y', active: false, five_hour: null, seven_day: { utilization: 0.1, resets_at: 1, status: 'allowed' } },
]
const TRANSCRIPT = {
  id: 5, run_id: 43, round: null, agent_type: 'orchestrator', name: null, model: 'claude-opus-4-1', turns: 38,
  input_tokens: 412, cache_read_tokens: 1830211, output_tokens: 20977,
  started_at: '2026-10-21T09:00:10Z', ended_at: '2026-10-21T09:04:00Z',
}
const run = (id, status, extra = {}) => ({
  id, status, trigger: 'manual', started_at: '2026-10-21T09:00:00Z', ended_at: status === 'running' ? null : '2026-10-21T09:04:12Z',
  error: null, account: 'a@x', transcripts: [], ...extra,
})
const ago = (ms) => new Date(Date.now() - ms).toISOString()
const RUNNING = () => run(44, 'running', { started_at: ago(90_000), account: null })
const FAILED = run(43, 'failed', { error: 'claude exited with code 1', account: 'b@y', transcripts: [TRANSCRIPT] })
const SCHEDULED = run(42, 'succeeded', { trigger: 'schedule' })
const STOPPED = run(41, 'stopped', { ended_at: null })
const page = (extra = {}) => ({
  automation: AUTOMATION, runs: [RUNNING(), FAILED, SCHEDULED, STOPPED],
  runs_enabled: true, runs_active: 1, max_concurrent_runs: 2, accounts: ACCOUNTS, auto: { account_id: 1, label: 'a@x' },
  ...extra,
})
const STARTED = { run_id: 45, session_id: 's', worktree: '.claude/worktrees/automation-security-audit-1a2b', account_id: 2, account: 'b@y' }

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

/** Renders `path` with the page answering `body`; waits for its h1. */
async function open(path = PATH, body = page(), more = {}) {
  const responses = { [`GET ${PAGE}`]: [200, body], ...more }
  const fetch = mockFetch(responses)
  const view = renderAt(path)
  await screen.findByRole('heading', { level: 1, name: 'Security audit' })
  return { fetch, responses, ...view }
}

const pad = (n) => String(n).padStart(2, '0')
const local = (iso) => {
  const d = new Date(iso)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
const rows = () => within(screen.getByRole('list', { name: 'Runs' })).getAllByRole('listitem')
const rowOf = (id) => rows().find((li) => within(li).queryByRole('link', { name: `run #${id}` }))
const count = (fetch, url) => fetched(fetch).filter((u) => u === url).length
const calls = (fetch, method, url) => fetch.mock.calls.filter(([u, init]) => u === url && (init?.method ?? 'GET') === method)
const runNow = () => screen.getByRole('button', { name: 'Run now' })
const chooser = () => screen.getByRole('button', { name: 'Choose account' })
const menu = () => within(document.getElementById(chooser().getAttribute('popovertarget')))
const advance = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))

test('103 AC11: loads the page data; the breadcrumb, the h1, and the tab title', async () => {
  const { fetch } = await open()
  expect(fetched(fetch)).toContain(PAGE)
  const crumbs = screen.getByRole('navigation', { name: 'Breadcrumb' })
  expect(crumbs.textContent).toBe('personal › api-server › Workflows › Security audit')
  expect(within(crumbs).getByRole('link', { name: 'Workflows' }).getAttribute('href')).toBe('/projects/3/factories')
  const current = within(crumbs).getByText('Security audit')
  expect([current.getAttribute('aria-current'), current.closest('a')]).toEqual(['page', null])
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('Security audit')
  await waitFor(() => expect(document.title).toBe('Security audit runs · api-server · Claude Factories'))
})

test("103 AC12: a 404 is the not-found page, and so is an automation of another project", async () => {
  mockFetch({ [`GET ${PAGE}`]: [404, { detail: 'Factory #7 not found' }] })
  const gone = renderAt(PATH)
  expect(await screen.findByRole('heading', { level: 1, name: 'Factory #7 not found' })).toBeTruthy()
  gone.unmount()
  mockFetch({ [`GET ${PAGE}`]: [200, page({ automation: { ...AUTOMATION, project_id: 4 } })] })
  renderAt(PATH)
  expect(await screen.findByRole('heading', { level: 1, name: 'Factory #7 not found' })).toBeTruthy()
  expect(screen.queryByRole('list', { name: 'Runs' })).toBeNull()
})

test('103 AC13: one row per run in the API order: run #, pill, trigger, relative start with local title, duration, account, error', async () => {
  await open()
  expect(rows().map((li) => li.querySelector('a').textContent)).toEqual(['run #44', 'run #43', 'run #42', 'run #41'])
  const parts = (id) => [...rowOf(id).children].map((el) => el.textContent)
  expect(parts(43).slice(0, 2)).toEqual(['run #43', 'failed'])
  expect(parts(43).slice(2)).toEqual(['manual', expect.any(String), '4m 12s', 'b@y', 'claude exited with code 1'])
  expect(parts(42)).toEqual(['run #42', 'succeeded', 'schedule', expect.any(String), '4m 12s', 'a@x'])
  expect(parts(41)).toEqual(['run #41', 'stopped', 'manual', expect.any(String), '—', 'a@x']) // Q7: no end, not running
  const [, pill, , , elapsed, account] = parts(44)
  expect([pill, account]).toEqual(['● running', '—'])
  expect(elapsed).toMatch(/^1m 3\ds$/) // Q7: elapsed to now
  const time = rowOf(43).querySelector('time')
  expect([time.getAttribute('title'), time.getAttribute('datetime')]).toEqual([local(FAILED.started_at), FAILED.started_at])
  // Q6: outlined pills in their tokens, the word as the label
  expect(within(rowOf(43)).getByText('failed').className).toMatch(cls('border-danger'))
  expect(within(rowOf(42)).getByText('succeeded').className).toMatch(cls('border-success'))
  expect(within(rowOf(41)).getByText('stopped').className).toMatch(cls('border-muted'))
})

test('103 AC14: with no runs, No runs yet. and an enabled Run now', async () => {
  await open(PATH, page({ runs: [], runs_active: 0 }))
  expect(screen.getByText('No runs yet.')).toBeTruthy()
  expect(runNow().disabled).toBe(false)
  expect(screen.getAllByRole('button', { name: 'Run now' })).toHaveLength(1) // Q4: exactly one
})

test('103 AC15: clicking run #43 sets ?run=43, marks its row current, and opens its log from after=0', async () => {
  const { router } = await open(PATH, page(), {
    [`GET ${LOG(43, 0)}`]: [200, { next: 2, lines: [{ text: 'first line' }, { text: 'second line' }] }],
  })
  fireEvent.click(screen.getByRole('link', { name: 'run #43' }))
  await waitFor(() => expect(router.state.location.search).toBe('?run=43'))
  expect(rowOf(43).getAttribute('aria-current')).toBe('true')
  expect(rows().filter((li) => li.hasAttribute('aria-current'))).toHaveLength(1)
  const panel = document.getElementById('run-log')
  expect(panel.open).toBe(true)
  expect(panel.querySelector('summary').textContent).toBe('Run log · run #43')
  expect(await within(panel).findByText('second line')).toBeTruthy()
  expect(within(panel).getByText('first line')).toBeTruthy()
})

test("103 AC16: a running run's log is fetched every 3 s; once a page poll shows it ended, one last fetch, then none", async () => {
  vi.useFakeTimers()
  const responses = {
    [`GET ${PAGE}`]: [200, page()],
    [`GET ${LOG(44, 0)}`]: [200, { next: 1, lines: [{ text: 'one' }] }],
    [`GET ${LOG(44, 1)}`]: [200, { next: 1, lines: [] }],
  }
  const fetch = mockFetch(responses)
  renderAt(`${PATH}?run=44`)
  await advance(0)
  const logs = () => fetched(fetch).filter((u) => u.startsWith('/api/runs/44/log')).length
  expect(logs()).toBe(1)
  await advance(3000)
  expect(logs()).toBe(2)
  await advance(3000)
  expect(logs()).toBe(3)
  responses[`GET ${PAGE}`] = [200, page({ runs: [run(44, 'succeeded'), FAILED] })]
  await advance(3000)
  const ended = logs()
  expect(ended).toBeGreaterThan(3)
  await advance(15_000)
  expect(logs()).toBe(ended)
})

test("103 AC17: the open run's transcripts link to their pages with their stats; with none, No transcripts yet.", async () => {
  const { unmount } = await open(`${PATH}?run=43`)
  const list = screen.getByRole('list', { name: 'Transcripts of run #43' })
  const [item] = within(list).getAllByRole('listitem')
  const link = within(item).getByRole('link', { name: 'orchestrator' })
  expect(link.getAttribute('href')).toBe('/transcripts/5')
  expect(item.textContent).toBe('orchestrator · claude-opus-4-1 · 38 turns · in 412 · cache 1,830,211 · out 20,977 · 3m 50s')
  unmount()
  await open(`${PATH}?run=42`)
  expect(screen.getByText('No transcripts yet.')).toBeTruthy()
})

test('103 AC18: Stop only on running rows; it posts with its spinner and no confirm, reloads on 200, alerts a refusal', async () => {
  const { fetch, responses } = await open()
  expect(screen.getAllByRole('button', { name: /^Stop/ }).map((b) => b.getAttribute('aria-label'))).toEqual(['Stop run #44'])
  expect(within(rowOf(44)).getByRole('button', { name: 'Stop run #44' })).toBeTruthy()
  let answer
  fetch.mockImplementationOnce(() => new Promise((resolve) => (answer = resolve)))
  const before = count(fetch, PAGE)
  const stop = screen.getByRole('button', { name: 'Stop run #44' })
  fireEvent.click(stop)
  await waitFor(() => expect(stop.getAttribute('aria-busy')).toBe('true'))
  expect(calls(fetch, 'POST', STOP(44))).toHaveLength(1)
  answer(new Response(JSON.stringify({ id: 44, status: 'stopped' }), { status: 200 }))
  await waitFor(() => expect(count(fetch, PAGE)).toBe(before + 1))
  responses[`POST ${STOP(44)}`] = [409, { detail: 'run #44 isn\'t running' }]
  fireEvent.click(screen.getByRole('button', { name: 'Stop run #44' }))
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe("run #44 isn't running")
  expect(alert.className).toMatch(cls('text-danger'))
  expect(screen.getByRole('heading', { level: 1, name: 'Security audit' })).toBeTruthy()
})

test('103 AC19: Run now posts no body, a menu account {account_id}; a start sets ?run=, says so politely, and reloads', async () => {
  const { fetch, router } = await open(PATH, page(), { [`POST ${RUN}`]: [202, STARTED] })
  expect(chooser().textContent).toBe('▾')
  const before = count(fetch, PAGE)
  fireEvent.click(runNow())
  await waitFor(() => expect(calls(fetch, 'POST', RUN).map(([, init]) => init.body ?? null)).toEqual([null]))
  expect(await screen.findByText('Started run #45 as b@y.')).toBeTruthy()
  expect(screen.getByText('Started run #45 as b@y.').getAttribute('role')).toBe('status')
  expect(router.state.location.search).toBe('?run=45')
  await waitFor(() => expect(count(fetch, PAGE)).toBeGreaterThan(before))
  fireEvent.click(menu().getByRole('button', { name: 'b@y · 5h — · 7d 10%', hidden: true }))
  await waitFor(() =>
    expect(calls(fetch, 'POST', RUN).map(([, init]) => init.body ?? null)).toEqual([null, JSON.stringify({ account_id: 2 })]),
  )
})

test('103 AC19: a refused Run now shows in the red alert; the next Run now or Stop empties it as it starts', async () => {
  await open(PATH, page(), { [`POST ${RUN}`]: [409, { detail: 'not on subscription auth' }] })
  fireEvent.click(runNow())
  expect((await screen.findByRole('alert')).textContent).toBe('not on subscription auth')
  for (const button of [runNow, () => screen.getByRole('button', { name: 'Stop run #44' })]) {
    let answer
    globalThis.fetch.mockImplementationOnce(() => new Promise((resolve) => (answer = resolve)))
    fireEvent.click(button())
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    answer(new Response(JSON.stringify({ detail: 'refused again' }), { status: 409 }))
    expect((await screen.findByRole('alert')).textContent).toBe('refused again')
  }
})

test('103 AC20: not signed in, or at the run cap, disables Run now and ▾ with 102\'s titles', async () => {
  for (const [extra, text] of [
    [{ runs_enabled: false }, 'Not signed in — runs disabled'],
    [{ runs_active: 2, max_concurrent_runs: 2 }, '2 of 2 runs active'],
  ]) {
    const { unmount } = await open(PATH, page(extra))
    for (const button of [runNow(), chooser()]) expect([button.disabled, button.title]).toEqual([true, text])
    unmount()
  }
})

test('103 AC21: polls every 3 s behind a skeleton; a failed first load is the red alert', async () => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
  const pending = renderAt(PATH)
  expectSkeleton(screen.getByRole('status'))
  pending.unmount()
  const fetch = mockFetch({ [`GET ${PAGE}`]: [200, page()] })
  const view = renderAt(PATH)
  await advance(0)
  expect(count(fetch, PAGE)).toBe(1)
  await advance(3000)
  expect(count(fetch, PAGE)).toBe(2)
  view.unmount()
  vi.useRealTimers()
  mockFetch({ [`GET ${PAGE}`]: [500, { detail: 'boom' }] })
  renderAt(PATH)
  const alert = await screen.findByRole('alert')
  expect([alert.textContent, cls('text-danger').test(alert.className)]).toEqual(['boom', true])
})

test('103 AC21: a failed poll after a good load shows Offline — retrying and keeps the page', async () => {
  vi.useFakeTimers()
  const responses = { [`GET ${PAGE}`]: [200, page()] }
  mockFetch(responses)
  renderAt(PATH)
  await advance(0)
  await expectOfflineBanner(responses, `GET ${PAGE}`, () =>
    expect(screen.getByRole('heading', { level: 1, name: 'Security audit' })).toBeTruthy(),
  )
})

test('103 AC22: without ?run=, or with one not listed, no log panel shows', async () => {
  for (const path of [PATH, `${PATH}?run=99`, `${PATH}?run=abc`]) {
    const { unmount } = await open(path)
    expect(document.getElementById('run-log')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(rows().filter((li) => li.hasAttribute('aria-current'))).toEqual([])
    unmount()
  }
})
