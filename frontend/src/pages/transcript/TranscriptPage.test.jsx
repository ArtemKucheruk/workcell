import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { fetched, mockFetch, renderAt } from '../../test/render.jsx'

const URL = '/api/transcripts/5'
const FULL = '/api/transcripts/5?full=1'

/** 030's TranscriptDetail, with 047's project and workspace; `messages` defaults to none. */
const detail = (extra = {}) => ({
  id: 5, run_id: 41, task_id: 12, project_id: 3, project: 'api', workspace_id: 2, workspace: 'personal', round: 1, agent_type: 'builder', name: 'builder-12', model: 'claude-opus-4-1',
  turns: 38, input_tokens: 412, cache_read_tokens: 1830211, output_tokens: 20977,
  started_at: '2026-10-17T10:04:11Z', ended_at: '2026-10-17T10:21:40Z', messages: [], ...extra,
})
const result = (text, truncated = false, is_error = false) => ({ type: 'tool_result', text, is_error, truncated })
const MESSAGES = [
  { role: 'user', at: '2026-10-17T10:04:11.500Z', blocks: [{ type: 'text', text_html: '<p>Task 12, round 1.</p>' }] },
  {
    role: 'assistant', at: '2026-10-17T10:04:12Z', blocks: [
      { type: 'thinking', text: 'plan <i>it</i>' },
      { type: 'text', text_html: '<p>&lt;script&gt;x&lt;/script&gt; <strong>hi</strong></p>' },
      { type: 'tool_use', name: 'Bash', input: '{\n  "command": "<b>x</b>"\n}' },
    ],
  },
  { role: 'user', at: '2026-10-17T10:04:20Z', blocks: [result('3 <b>passed</b>'), result('boom', false, true)] },
]

afterEach(() => {
  vi.useRealTimers()
})

async function open(responses) {
  const fetch = mockFetch(responses)
  const view = renderAt('/transcripts/5')
  await screen.findByRole('heading', { level: 1 })
  return { fetch, ...view }
}

const header = () => document.querySelector('main header')
const items = () => [...document.querySelectorAll('main ol > li')].filter((li) => !li.closest('nav')) // 047: not the breadcrumb's

test('030 AC25: fetches the transcript once and shows its header: label, run, stats, Download raw', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  const { fetch } = await open({ [`GET ${URL}`]: [200, detail()] })
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('builder-12')
  expect(header().textContent).toContain('run #41')
  expect(header().textContent).toContain(
    'claude-opus-4-1 · 38 turns · in 412 · cache 1,830,211 · out 20,977 · 17m 29s',
  )
  expect(within(header()).getByRole('link', { name: 'Download raw' }).getAttribute('href')).toBe(
    '/api/transcripts/5/raw',
  )
  await act(() => vi.advanceTimersByTimeAsync(10000))
  expect(fetched(fetch).filter((url) => url.startsWith('/api/transcripts'))).toEqual([URL])
  await waitFor(() => expect(document.title).toBe('builder-12 · Claude Factories'))
})

test('047 FE5: the breadcrumb reads personal › api › #12 › builder-12, #12 links to the task, and no Task #12 link is left', async () => {
  await open({ [`GET ${URL}`]: [200, detail()] })
  const crumbs = screen.getByRole('navigation', { name: 'Breadcrumb' })
  expect(crumbs.closest('header')).toBe(header())
  expect(crumbs.textContent).toBe('personal › api › #12 › builder-12')
  expect(within(crumbs).getAllByRole('link').map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
    ['personal', '/workspaces/2'], ['api', '/projects/3'], ['#12', '/tasks/12'],
  ])
  const current = within(crumbs).getByText('builder-12')
  expect([current.getAttribute('aria-current'), current.closest('a')]).toEqual(['page', null])
  expect(screen.queryByText(/Task #12/)).toBeNull()
  expect(within(header()).getAllByRole('link').filter((a) => !crumbs.contains(a)).map((a) => a.textContent)).toEqual(['Download raw'])
})

test("103 AC25: an automation transcript's breadcrumb is personal › api › Workflows › Security audit › orchestrator", async () => {
  const auto = { task_id: null, factory_id: 7, factory: 'Security audit', agent_type: 'orchestrator', name: null }
  await open({ [`GET ${URL}`]: [200, detail(auto)] })
  const crumbs = screen.getByRole('navigation', { name: 'Breadcrumb' })
  expect(crumbs.textContent).toBe('personal › api › Workflows › Security audit › orchestrator')
  expect(within(crumbs).getAllByRole('link').map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
    ['personal', '/workspaces/2'], ['api', '/projects/3'], ['Workflows', '/projects/3/factories'],
    ['Security audit', '/projects/3/factories/7/runs?run=41'],
  ])
  expect(within(crumbs).getByText('orchestrator').getAttribute('aria-current')).toBe('page')
  expect(screen.queryByText(/#null/)).toBeNull()
})

test('030 AC25: the label falls back to the agent type, then to agent', async () => {
  const typed = await open({ [`GET ${URL}`]: [200, detail({ name: null, agent_type: 'orchestrator' })] })
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('orchestrator')
  typed.unmount()
  await open({ [`GET ${URL}`]: [200, detail({ name: null, agent_type: null })] })
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('agent')
})

test('030 AC26: each message shows its role and blocks; only text is HTML, the rest is text', async () => {
  await open({ [`GET ${URL}`]: [200, detail({ messages: MESSAGES })] })
  const [first, second, third] = items()
  expect(items()).toHaveLength(3)
  expect(within(first).getByText('user').tagName).toBe('STRONG')
  expect(first.querySelector('.markdown').innerHTML).toBe('<p>Task 12, round 1.</p>')
  expect(within(second).getByText('assistant').tagName).toBe('STRONG')
  const markdown = second.querySelector('.markdown')
  expect(markdown.querySelector('strong').textContent).toBe('hi')
  expect(markdown.querySelector('script')).toBeNull()
  expect(markdown.textContent).toBe('<script>x</script> hi')
  const thinking = second.querySelector('details')
  expect(thinking.open).toBe(false)
  expect(thinking.querySelector('summary').textContent).toBe('Thinking')
  expect(thinking.textContent).toContain('plan <i>it</i>')
  expect(thinking.querySelector('i')).toBeNull()
  expect(within(second).getByText('Bash').tagName).toBe('CODE')
  const [input] = second.querySelectorAll('pre')
  expect(input.textContent).toBe('{\n  "command": "<b>x</b>"\n}')
  expect(input.querySelector('b')).toBeNull()
  const results = [...third.querySelectorAll('pre')]
  expect(results.map((p) => p.textContent)).toEqual(['3 <b>passed</b>', 'boom'])
  expect(results[0].querySelector('b')).toBeNull()
  expect(within(third).getByText('Tool error')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Show all' })).toBeNull()
})

test('030 AC27: a cut tool result has Show all, which refetches with ?full=1 and shows the whole text', async () => {
  const cut = detail({ messages: [{ role: 'user', at: null, blocks: [result('x'.repeat(4096), true)] }] })
  const whole = detail({ messages: [{ role: 'user', at: null, blocks: [result('x'.repeat(5000))] }] })
  const { fetch } = await open({ [`GET ${URL}`]: [200, cut], [`GET ${FULL}`]: [200, whole] })
  expect(document.querySelector('main pre').textContent).toHaveLength(4096)
  fireEvent.click(screen.getByRole('button', { name: 'Show all' }))
  await waitFor(() => expect(document.querySelector('main pre').textContent).toHaveLength(5000))
  expect(screen.queryByRole('button', { name: 'Show all' })).toBeNull()
  expect(fetched(fetch).filter((url) => url.startsWith('/api/transcripts'))).toEqual([URL, FULL])
})

test("030 AC28: a 404 shows the not-found page with the API's detail; any other error, the alert", async () => {
  mockFetch({ [`GET ${URL}`]: [404, { detail: 'Transcript #5 not found' }] })
  const missing = renderAt('/transcripts/5')
  expect((await screen.findByRole('heading', { level: 1 })).textContent).toBe('Transcript #5 not found')
  expect(screen.getByRole('link', { name: 'Go to the dashboard' })).toBeTruthy()
  missing.unmount()

  mockFetch({ [`GET ${URL}`]: [500, { detail: 'boom' }] })
  renderAt('/transcripts/5')
  expect((await screen.findByRole('alert')).textContent).toBe('boom')
  expect(screen.queryByRole('heading', { level: 1 })).toBeNull()
})

test('046 FE8: message times stay absolute local YYYY-MM-DD HH:MM, with no title, however recent', async () => {
  vi.stubEnv('TZ', 'Asia/Tokyo')
  vi.setSystemTime(new Date('2026-10-17T10:09:20Z')) // 5 minutes after the last message
  await open({ [`GET ${URL}`]: [200, detail({ messages: MESSAGES })] })
  const times = [...document.querySelectorAll('main time')]
  expect(times.map((t) => [t.getAttribute('datetime'), t.textContent, t.getAttribute('title')])).toEqual([
    ['2026-10-17T10:04:11.500Z', '2026-10-17 19:04', null],
    ['2026-10-17T10:04:12Z', '2026-10-17 19:04', null],
    ['2026-10-17T10:04:20Z', '2026-10-17 19:04', null],
  ])
})
