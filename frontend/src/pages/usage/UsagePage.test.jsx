import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { cls, expectSkeleton, fetched, mockFetch, renderAt } from '../../test/render.jsx'

const URL7 = '/api/usage?days=7'
const URL30 = '/api/usage?days=30'
const NOW = new Date(2026, 10, 13, 10, 0)
const at = (minutes) => Math.floor(NOW.getTime() / 1000) + minutes * 60
const win = (utilization, state = 'allowed') => ({ utilization, resets_at: at(130), state, reset: false })

/** GET /api/usage's accounts as the contract has them. */
const ACCOUNTS = [
  { id: 1, label: 'me@x.io', active: true, recorded_at: new Date(NOW - 90 * 60000).toISOString(), run_id: 41, overage: false,
    five_hour: win(0.34), seven_day: win(0.85, 'near_limit') },
  { id: 2, label: 'work', active: false, recorded_at: '2026-11-13T00:00:00Z', run_id: 40, overage: true,
    five_hour: win(1, 'limited'), seven_day: win(0.5) },
  { id: 3, label: 'fresh', active: false, recorded_at: null, run_id: null, overage: null, five_hour: null, seven_day: null },
]
const day = (d, input = 0, cache = 0, output = 0, runs = 0) => ({
  day: d, input_tokens: input, cache_read_tokens: cache, output_tokens: output, runs,
})
const group = (key, input, cache, output, runs) => ({ key, input_tokens: input, cache_read_tokens: cache, output_tokens: output, runs })
const STATS = {
  days: 7,
  by_day: [day('2026-11-07'), day('2026-11-12', 1200, 34000, 560, 1), day('2026-11-13', 300, 0, 40, 2)],
  by_account: [group('me@x.io', 1500, 34000, 600, 3)],
  by_model: [group('claude-opus-4-1', 1500, 34000, 600, 3)],
  by_agent: [group('builder', 1000, 20000, 400, 2), group('orchestrator', 500, 14000, 200, 1)],
  top_tasks: [{ task_id: 12, title: 'Rate-limit login', project_id: 3, input_tokens: 1500, cache_read_tokens: 34000, output_tokens: 600 }],
}
const LIMITED = [{ run_id: 40, task_id: 12, title: 'Rate-limit login', label: 'work', ended_at: '2026-11-12T23:00:00Z' }]
const body = (extra = {}) => ({ accounts: ACCOUNTS, stats: STATS, limited_runs: LIMITED, ...extra })
const EMPTY_STATS = { days: 7, by_day: [day('2026-11-12'), day('2026-11-13')], by_account: [], by_model: [], by_agent: [], top_tasks: [] }

afterEach(() => vi.useRealTimers())

async function open(reply = body(), more = {}) {
  vi.setSystemTime(NOW)
  const fetch = mockFetch({ [`GET ${URL7}`]: [200, reply], ...more })
  const view = renderAt('/usage')
  await screen.findByRole('heading', { level: 1, name: 'Usage' })
  return { fetch, ...view }
}

const region = (name) => within(screen.getByRole('region', { name }))
const settle = () => act(() => new Promise((resolve) => setTimeout(resolve, 20)))

test('AC25: one GET /api/usage, no polling; title, h1 Usage, not wide', async () => {
  const { fetch } = await open()
  await waitFor(() => expect(document.title).toBe('Usage · Workcell'))
  expect(screen.getByRole('main').className).toMatch(cls('max-w-6xl'))
  await settle()
  expect(fetched(fetch).filter((u) => u.startsWith('/api/usage'))).toEqual([URL7])
})

test('AC25: the first load is a skeleton; a failed load is the red alert', async () => {
  mockFetch({}).mockImplementation(() => new Promise(() => {}))
  const pending = renderAt('/usage')
  expectSkeleton(within(screen.getByRole('main')).getByRole('status'))
  pending.unmount()

  mockFetch({ [`GET ${URL7}`]: [500, { detail: 'boom' }] })
  renderAt('/usage')
  const alert = await within(screen.getByRole('main')).findByRole('alert')
  expect(alert.textContent).toBe('boom')
  expect(alert.className).toMatch(cls('text-danger'))
})

test('AC26: a card per account with label, active pill, both windows, as of · run #N, and overage', async () => {
  await open()
  const cards = region('Accounts').getAllByRole('listitem')
  expect(cards).toHaveLength(3)
  const [mine, work, fresh] = cards.map((c) => c.textContent)
  expect(mine).toContain('me@x.ioactive')
  expect(mine).toContain('5h34%resets in 2h 10m · allowed')
  expect(mine).toContain('7d85%resets in 2h 10m · near limit')
  expect(mine).toContain('as of 1h ago · run #41 · Overage: not in use')
  expect(within(cards[0]).getByText('active').className).toMatch(cls('rounded-full'))
  expect(work).not.toContain('active')
  expect(work).toContain('5h100%resets in 2h 10m · limited')
  expect(work).toContain('Overage: in use')
  expect(cards[1].querySelector('time').getAttribute('datetime')).toBe('2026-11-13T00:00:00Z')
  expect(fresh).toBe('freshno usage data yet, run a task')
})

test('round 2 (ui): with no accounts, Accounts says so and links to Settings instead of an empty list', async () => {
  await open(body({ accounts: [] }))
  const accounts = region('Accounts')
  expect(accounts.queryByRole('list')).toBeNull()
  expect(accounts.getByText((_, el) => el?.tagName === 'P' && el.textContent === 'No Claude accounts yet. Sign in from Settings.')).toBeTruthy()
  expect(accounts.getByRole('link', { name: 'Sign in from Settings' }).getAttribute('href')).toBe('/settings')
})

test('AC27: Last 7 days / Last 30 days radios refetch with ?days=', async () => {
  const { fetch } = await open(body(), { [`GET ${URL30}`]: [200, body({ stats: { ...STATS, days: 30, top_tasks: [] } })] })
  const seven = screen.getByRole('radio', { name: 'Last 7 days' })
  const thirty = screen.getByRole('radio', { name: 'Last 30 days' })
  expect(seven.checked).toBe(true)
  fireEvent.click(thirty)
  await waitFor(() => expect(region('Most expensive tasks').getByText('No usage in this period.')).toBeTruthy())
  expect(thirty.checked).toBe(true)
  expect(fetched(fetch).filter((u) => u.startsWith('/api/usage'))).toEqual([URL7, URL30])
})

test('AC28: By day draws a stacked bar per day with its totals and runs as text', async () => {
  await open()
  const days = region('By day').getAllByRole('listitem')
  expect(days.map((d) => d.textContent)).toEqual([
    '2026-11-07input 0 · cache read 0 · output 0 · 0 runs',
    '2026-11-12input 1,200 · cache read 34,000 · output 560 · 1 run',
    '2026-11-13input 300 · cache read 0 · output 40 · 2 runs',
  ])
  const bar = days[1].querySelector('[aria-hidden="true"]')
  expect([...bar.children].map((s) => s.className)).toEqual(['bg-accent', 'bg-muted', 'bg-warning'])
  // the busiest day fills the track, its three pieces in proportion
  const widths = [...bar.children].map((s) => parseFloat(s.style.width))
  expect(widths.reduce((a, b) => a + b)).toBeCloseTo(100)
  expect(widths[1] / widths[0]).toBeCloseTo(34000 / 1200)
  expect(document.querySelector('main svg, main canvas')).toBeNull()
})

test('AC28: account, model, and agent tables with thousands separators; top tasks link to the task', async () => {
  await open()
  const rows = (name) => region(name).getAllByRole('row').map((r) => [...r.children].map((c) => c.textContent))
  expect(rows('By account')).toEqual([
    ['Account', 'Input', 'Cache read', 'Output', 'Runs'],
    ['me@x.io', '1,500', '34,000', '600', '3'],
  ])
  expect(rows('By model')[1][0]).toBe('claude-opus-4-1')
  expect(rows('By agent').slice(1).map((r) => r[0])).toEqual(['builder', 'orchestrator'])
  const task = region('Most expensive tasks').getByRole('link', { name: '#12 Rate-limit login' })
  expect(task.getAttribute('href')).toBe('/tasks/12')
  expect(task.closest('li').textContent).toContain('input 1,500 · cache read 34,000 · output 600')
})

test('AC29: limited runs list run #N, the task link, the label, and the ended time; or No limited runs.', async () => {
  const view = await open()
  const [item] = region('Limited runs').getAllByRole('listitem')
  expect(item.textContent).toMatch(/^run #40·#12 Rate-limit login·work·2026-11-1\d \d\d:\d\d$/)
  expect(within(item).getByRole('link').getAttribute('href')).toBe('/tasks/12')
  view.unmount()

  await open(body({ limited_runs: [] }))
  expect(region('Limited runs').getByText('No limited runs.')).toBeTruthy()
})

test('AC30: empty stats say No usage in this period. in each section', async () => {
  await open(body({ stats: EMPTY_STATS }))
  for (const name of ['By day', 'By account', 'By model', 'By agent', 'Most expensive tasks']) {
    expect(region(name).getByText('No usage in this period.')).toBeTruthy()
    expect(region(name).queryByRole('table')).toBeNull()
  }
})
