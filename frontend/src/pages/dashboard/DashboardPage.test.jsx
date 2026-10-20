import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import { fetched, fullText, mockFetch, renderAt } from '../../test/render.jsx'

// handlers/pages.py TILES, as /api/pages/dashboard returns them
const TILES = {
  backlog: 'Backlog', in_progress: 'In progress', review: 'Review', done: 'Done',
  waiting: 'Waiting on me', escalated: 'Escalated', running: 'Running now',
  done_week: 'Done this week', runs_week: 'Runs this week',
}
const COUNTS = Object.fromEntries(Object.keys(TILES).map((key, i) => [key, i + 10]))
const page = (over = {}) => ({
  tiles: TILES, counts: COUNTS, show: '', listed: null, open_tasks: [], done: [], workspaces: [], ...over,
})
const WAITING = [
  { id: 12, title: 'Rate-limit login', status: 'review', stage: 'human_review', project_id: 3, project: 'api' },
  { id: 13, title: 'Fix typo', status: 'backlog', stage: null, project_id: 4, project: 'web' },
]
const RUNS = [
  { id: 41, status: 'running', started_at: '2026-10-18T09:05:00Z', task_id: 12, title: 'Rate-limit login', project_id: 3, project: 'api' },
]
const DONE = [
  { id: 7, title: 'Add login', done_at: '2026-10-17T23:30:00Z', project_id: 3, project: 'api', rounds: 1 },
  { id: 8, title: 'Add logout', done_at: '2026-10-01T00:00:00Z', project_id: 4, project: 'web', rounds: 2 },
]

const rowOf = (el) => el.closest('tr')
const href = (el) => el.getAttribute('href')

beforeEach(() => {
  vi.stubEnv('TZ', 'Asia/Tokyo') // AC26: UTC+9, no DST, so local times are known
})

test('AC20: / shows the 9 tiles in order with counts, each linking to its list', async () => {
  const fetch = mockFetch({ 'GET /api/pages/dashboard': [200, page()] })
  renderAt('/')
  const tiles = within((await within(screen.getByRole('main')).findAllByRole('list'))[0]).getAllByRole('link')
  expect(tiles.map((a) => [a.textContent, href(a)])).toEqual(
    Object.entries(TILES).map(([key, label]) => [`${label} ${COUNTS[key]}`, `/?show=${key}`]),
  )
  expect(tiles.some((a) => a.hasAttribute('aria-current'))).toBe(false)
  expect(fetched(fetch)).toContain('/api/pages/dashboard')
  await waitFor(() => expect(document.title).toBe('Claude Factories')) // the title is set in an effect, after the heading renders
})

const cls = (name) => new RegExp(`(^|\\s)${name}(\\s|$)`)

test('AC21, 043 FE14: ?show=waiting lists tasks with their state pills, marks its tile; another tile loads its own list', async () => {
  const fetch = mockFetch({
    'GET /api/pages/dashboard?show=waiting': [200, page({ show: 'waiting', listed: WAITING })],
    'GET /api/pages/dashboard?show=escalated': [200, page({ show: 'escalated', listed: [] })],
  })
  renderAt('/?show=waiting')
  const list = (await screen.findByRole('heading', { name: 'Waiting on me' })).closest('section')
  expect(fetched(fetch)).toContain('/api/pages/dashboard?show=waiting')
  expect(screen.getByRole('link', { name: 'Waiting on me 14' }).getAttribute('aria-current')).toBe('page')

  const task = within(list).getByRole('link', { name: '#12 Rate-limit login' })
  expect(href(task)).toBe('/tasks/12')
  const row = within(rowOf(task))
  expect(href(row.getByRole('link', { name: 'api' }))).toBe('/projects/3')
  const status = (tr) => [...tr.querySelectorAll('td')][2]
  const pills = (tr) => [...status(tr).firstElementChild.children]
  const twelve = rowOf(task)
  expect(pills(twelve).map((el) => el.textContent)).toEqual(['Review', 'waiting on you'])
  expect(pills(twelve)[0].className).toMatch(cls('text-warning'))
  expect(pills(twelve)[1].className).toMatch(cls('bg-warning'))
  const thirteen = rowOf(within(list).getByRole('link', { name: '#13 Fix typo' }))
  expect(pills(thirteen).map((el) => el.textContent)).toEqual(['Backlog'])
  expect(status(thirteen).textContent).toBe('Backlog')

  fireEvent.click(screen.getByRole('link', { name: 'Escalated 15' }))
  expect(await screen.findByRole('heading', { name: 'Escalated' })).toBeTruthy()
  expect(fetched(fetch)).toContain('/api/pages/dashboard?show=escalated')
  expect(screen.getByText('No tasks.')).toBeTruthy()
})

test('AC22, 043 FE14: ?show=runs_week lists runs, a running one as the ● running badge, the rest as text; an empty list says No runs.', async () => {
  const ended = ['succeeded', 'failed', 'stopped'].map((status, i) => ({ ...RUNS[0], id: 42 + i, status }))
  mockFetch({ 'GET /api/pages/dashboard?show=runs_week': [200, page({ show: 'runs_week', listed: [...RUNS, ...ended] })] })
  const { unmount } = renderAt('/?show=runs_week')
  const run = await screen.findByText('run #41')
  const row = within(rowOf(run))
  expect(href(row.getByRole('link', { name: '#12 Rate-limit login' }))).toBe('/tasks/12')
  expect(href(row.getByRole('link', { name: 'api' }))).toBe('/projects/3')
  const badge = row.getByText(fullText('● running'))
  expect(badge.className).toMatch(cls('text-accent'))
  expect(badge.parentElement.tagName).toBe('TD')
  expect(row.getByText('2026-10-18 18:05')).toBeTruthy()
  for (const [i, status] of ['succeeded', 'failed', 'stopped'].entries()) {
    const cell = [...rowOf(screen.getByText(`run #${42 + i}`)).querySelectorAll('td')][3]
    expect([cell.textContent, cell.children.length]).toEqual([status, 0])
  }
  unmount()

  mockFetch({ 'GET /api/pages/dashboard?show=runs_week': [200, page({ show: 'runs_week', listed: [] })] })
  renderAt('/?show=runs_week')
  expect(await screen.findByText('No runs.')).toBeTruthy()
})

test('AC23: open tasks group projects under their workspace', async () => {
  const open_tasks = [
    { id: 1, name: 'personal', projects: [{ id: 3, name: 'api', backlog: 2, in_progress: 1, review: 0 }] },
    { id: 2, name: 'work', projects: [{ id: 4, name: 'web', backlog: 0, in_progress: 0, review: 5 }] },
  ]
  mockFetch({ 'GET /api/pages/dashboard': [200, page({ open_tasks })] })
  const { unmount } = renderAt('/')
  const section = (await screen.findByRole('heading', { name: 'Open tasks' })).closest('section')
  const groups = within(section).getAllByRole('rowgroup').slice(1) // after the thead
  expect(groups).toHaveLength(2)
  for (const [i, ws] of open_tasks.entries()) {
    const group = within(groups[i])
    expect(href(group.getByRole('link', { name: ws.name }))).toBe(`/workspaces/${ws.id}`)
    const [p] = ws.projects
    const cells = rowOf(group.getByRole('link', { name: p.name })).querySelectorAll('td')
    expect(href(group.getByRole('link', { name: p.name }))).toBe(`/projects/${p.id}`)
    expect([...cells].slice(1).map((td) => td.textContent)).toEqual([p.backlog, p.in_progress, p.review].map(String))
  }
  unmount()

  mockFetch({ 'GET /api/pages/dashboard': [200, page()] })
  renderAt('/')
  expect(await screen.findByText('No open tasks.')).toBeTruthy()
})

test('AC24: rounds per task shows average, max, and each done task', async () => {
  mockFetch({ 'GET /api/pages/dashboard': [200, page({ done: DONE })] })
  const { unmount } = renderAt('/')
  const section = (await screen.findByRole('heading', { name: /Rounds per task/ })).closest('section')
  expect(within(section).getByText(fullText('Average 1.5 · Max 2'))).toBeTruthy()
  const row = within(rowOf(within(section).getByRole('link', { name: '#8 Add logout' })))
  expect(href(row.getByRole('link', { name: '#8 Add logout' }))).toBe('/tasks/8')
  expect(href(row.getByRole('link', { name: 'web' }))).toBe('/projects/4')
  expect(row.getByText('2')).toBeTruthy()
  expect(row.getByText('2026-10-01 09:00')).toBeTruthy()
  expect(within(section).getByRole('link', { name: '#7 Add login' })).toBeTruthy()
  unmount()

  mockFetch({ 'GET /api/pages/dashboard': [200, page()] })
  renderAt('/')
  expect(await screen.findByText('No tasks done in the last 30 days.')).toBeTruthy()
})

test('AC25: workspaces link to their page with a project count', async () => {
  const workspaces = [{ id: 1, name: 'personal', projects: 1 }, { id: 2, name: 'work', projects: 3 }]
  mockFetch({ 'GET /api/pages/dashboard': [200, page({ workspaces })] })
  const { unmount } = renderAt('/')
  const section = (await screen.findByRole('heading', { name: 'Workspaces' })).closest('section')
  const items = within(section).getAllByRole('listitem')
  expect(items.map((li) => [li.textContent, href(within(li).getByRole('link'))])).toEqual([
    ['personal 1 project', '/workspaces/1'],
    ['work 3 projects', '/workspaces/2'],
  ])
  unmount()

  mockFetch({ 'GET /api/pages/dashboard': [200, page()] })
  renderAt('/')
  expect(
    await screen.findByText(fullText('No projects yet. Run fctl connect --workspace <name> inside a repo.')),
  ).toBeTruthy()
})

test('AC26: every time is a <time datetime> in local YYYY-MM-DD HH:MM', async () => {
  mockFetch({ 'GET /api/pages/dashboard?show=runs_week': [200, page({ show: 'runs_week', listed: RUNS, done: DONE })] })
  const { container } = renderAt('/?show=runs_week')
  await screen.findByText('run #41')
  const times = [...container.querySelectorAll('time')]
  expect(times.map((t) => [t.getAttribute('datetime'), t.textContent])).toEqual([
    ['2026-10-18T09:05:00Z', '2026-10-18 18:05'],
    ['2026-10-17T23:30:00Z', '2026-10-18 08:30'],
    ['2026-10-01T00:00:00Z', '2026-10-01 09:00'],
  ])
})

test('AC32: a failed dashboard view-model shows its detail in an alert', async () => {
  for (const [status, detail] of [[500, 'boom'], [502, 'Backend unreachable at http://127.0.0.1:4545']]) {
    mockFetch({ 'GET /api/pages/dashboard': [status, { detail }] })
    const { unmount } = renderAt('/')
    expect((await screen.findByRole('alert')).textContent).toBe(detail)
    unmount()
  }
})
