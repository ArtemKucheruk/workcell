import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { fetched, fullText, mockFetch, renderAt } from '../../test/render.jsx'

// handlers/pages.py TILES, as /api/pages/dashboard returns them
const TILES = {
  backlog: 'Backlog', in_progress: 'In progress', review: 'Review', done: 'Done',
  waiting: 'Waiting on me', escalated: 'Escalated', running: 'Running now',
  done_week: 'Done this week', runs_week: 'Runs this week',
}
const COUNTS = Object.fromEntries(Object.keys(TILES).map((key, i) => [key, i + 10]))
const page = (over = {}) => ({
  tiles: TILES, counts: COUNTS, show: '', listed: null, waiting: [], escalated: [], open_tasks: [], done: [], ...over,
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
afterEach(() => {
  vi.useRealTimers()
})

// Q7: the frontend's split of the backend's TILES
const ATTENTION = ['waiting', 'escalated', 'running']
const THROUGHPUT = ['done_week', 'runs_week', 'backlog', 'in_progress', 'review', 'done']
const group = (name) => within(screen.getByRole('list', { name })).getAllByRole('link')

test('AC20, FE7: / shows the tiles in the Attention and Throughput groups with counts, each linking to its list', async () => {
  const fetch = mockFetch({ 'GET /api/pages/dashboard': [200, page()] })
  const { unmount } = renderAt('/')
  await screen.findByRole('list', { name: 'Attention' })
  for (const [name, keys] of [['Attention', ATTENTION], ['Throughput', THROUGHPUT]]) {
    expect(group(name).map((a) => [a.textContent, href(a)])).toEqual(
      keys.map((key) => [`${TILES[key]} ${COUNTS[key]}`, `/?show=${key}`]),
    )
  }
  expect(screen.getByText('Attention').tagName).not.toMatch(/^H/) // Q7: a small label, not a heading
  expect([...group('Attention'), ...group('Throughput')].some((a) => a.hasAttribute('aria-current'))).toBe(false)
  expect(fetched(fetch)).toContain('/api/pages/dashboard')
  await waitFor(() => expect(document.title).toBe('Workcell')) // the title is set in an effect, after the heading renders
  unmount()

  mockFetch({ 'GET /api/pages/dashboard?show=done_week': [200, page({ show: 'done_week', listed: [] })] })
  renderAt('/?show=done_week')
  await screen.findByRole('heading', { name: 'Done this week' })
  expect(group('Throughput').filter((a) => a.getAttribute('aria-current') === 'page').map((a) => a.textContent)).toEqual([
    `Done this week ${COUNTS.done_week}`,
  ])
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

test('FE13: no Workspaces list and no connect hint; a view-model without `workspaces` renders', async () => {
  const vm = page()
  expect('workspaces' in vm).toBe(false)
  mockFetch({ 'GET /api/pages/dashboard': [200, vm] })
  renderAt('/')
  await screen.findByRole('heading', { level: 1, name: 'Dashboard' })
  expect(screen.queryByRole('heading', { name: 'Workspaces' })).toBeNull()
  expect(screen.queryByText(/No projects yet\./)).toBeNull()
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

// 045: the Needs you list. NOW is the faked clock; `ago` gives a `since` that many seconds before it.
const NOW = Date.parse('2026-10-20T12:00:00Z')
const ago = (s) => new Date(NOW - s * 1000).toISOString().replace('.000Z', 'Z')
const ESC = { id: 21, title: 'Migrate sessions', project_id: 4, project: 'web', round: 1, since: ago(3 * 86400) }
const WAIT = { id: 22, title: 'Rate-limit login', project_id: 3, project: 'api', round: 2, since: ago(90) }
const NO_ROUND = { id: 23, title: 'Docs pass', project_id: 3, project: 'api', round: null, since: ago(5 * 3600) }

async function needsYou(over) {
  mockFetch({ 'GET /api/pages/dashboard': [200, page(over)] })
  renderAt('/')
  return (await screen.findByRole('heading', { name: 'Needs you' })).closest('section')
}
const rows = (section) => within(section).getAllByRole('listitem')

test('FE1: Needs you is the first section after the h1, before any tile, escalated row first', async () => {
  const section = await needsYou({ waiting: [WAIT], escalated: [ESC] })
  const h1 = screen.getByRole('heading', { level: 1, name: 'Dashboard' })
  expect(h1.nextElementSibling).toBe(section)
  for (const name of ['Attention', 'Throughput']) {
    expect(section.compareDocumentPosition(screen.getByRole('list', { name })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  }
  expect(rows(section).map((li) => within(li).getAllByRole('link')[0].textContent)).toEqual([
    '#21 Migrate sessions',
    '#22 Rate-limit login',
  ])
})

test('FE2: a row has its review link, pill, project link, round, and age', async () => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
  const section = await needsYou({ waiting: [WAIT], escalated: [ESC] })
  const [esc, wait] = rows(section)
  for (const [li, t, pill, fill, age] of [[esc, ESC, 'escalated', 'bg-danger', '3d'], [wait, WAIT, 'waiting on you', 'bg-warning', '1m']]) {
    const row = within(li)
    expect(href(row.getByRole('link', { name: `#${t.id} ${t.title}` }))).toBe(`/tasks/${t.id}/review`)
    expect(row.getByText(pill).className).toMatch(cls(fill)) // components/Badge.jsx's filled pill
    expect(href(row.getByRole('link', { name: t.project }))).toBe(`/projects/${t.project_id}`)
    expect(row.getByText(`round ${t.round}`)).toBeTruthy()
    expect(li.querySelector('time').textContent).toBe(age)
  }
})

test('FE3: an escalated row has the red left bar, a waiting row does not', async () => {
  const [esc, wait] = rows(await needsYou({ waiting: [WAIT], escalated: [ESC] }))
  expect(esc.className).toMatch(cls('border-danger'))
  expect(wait.className).not.toMatch(cls('border-danger'))
})

test('FE4: an item with round null has no round text', async () => {
  const [withRound, without] = rows(await needsYou({ waiting: [WAIT, NO_ROUND] }))
  expect(withRound.textContent).toContain('round 2')
  expect(without.textContent).not.toMatch(/round/)
})

test('FE5: ages are floored m, h, d from a faked clock, each a <time dateTime={since}>; the future reads 0m', async () => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
  const future = { ...WAIT, id: 24, since: ago(-120) } // Q4: clock skew
  const section = await needsYou({ waiting: [WAIT, NO_ROUND, future], escalated: [ESC] })
  expect([...section.querySelectorAll('time')].map((t) => [t.getAttribute('datetime'), t.textContent])).toEqual([
    [ESC.since, '3d'],
    [WAIT.since, '1m'],
    [NO_ROUND.since, '5h'],
    [future.since, '0m'],
  ])
})

test('FE6: empty waiting and escalated → Nothing needs you. and no list', async () => {
  const section = await needsYou()
  expect(within(section).getByText('Nothing needs you.')).toBeTruthy()
  expect(within(section).queryByRole('list')).toBeNull()
})

test('FE8: each tile count is text-3xl and its label text-muted', async () => {
  mockFetch({ 'GET /api/pages/dashboard': [200, page()] })
  renderAt('/')
  await screen.findByRole('list', { name: 'Attention' })
  const tiles = [...group('Attention'), ...group('Throughput')]
  expect(tiles).toHaveLength(9)
  for (const a of tiles) {
    expect(a.querySelector('strong').className).toMatch(cls('text-3xl'))
    expect(a.querySelector('span').className).toMatch(cls('text-muted'))
  }
})

test('FE9: Attention counts above 0 take danger (Escalated) or accent; at 0, and on Throughput, neither', async () => {
  const count = (a) => a.querySelector('strong').className
  const tone = (a) => ['text-danger', 'text-accent'].filter((c) => count(a).match(cls(c)))
  const throughputPlain = () => group('Throughput').forEach((a) => expect(tone(a)).toEqual([]))

  mockFetch({ 'GET /api/pages/dashboard': [200, page()] }) // every count is above 0
  const { unmount } = renderAt('/')
  await screen.findByRole('list', { name: 'Attention' })
  expect(group('Attention').map(tone)).toEqual([['text-accent'], ['text-danger'], ['text-accent']])
  expect(group('Attention').map((a) => a.className.match(/(^|\s)(border-(accent|danger))(\s|$)/)?.[2])).toEqual([
    'border-accent', 'border-danger', 'border-accent',
  ])
  throughputPlain()
  unmount()

  const counts = { ...COUNTS, waiting: 0, escalated: 0, running: 0 }
  mockFetch({ 'GET /api/pages/dashboard': [200, page({ counts })] })
  renderAt('/')
  await screen.findByRole('list', { name: 'Attention' })
  expect(group('Attention').map(tone)).toEqual([[], [], []])
  group('Attention').forEach((a) => expect(a.className).toMatch(cls('border-line')))
  throughputPlain()
})

test('FE10: one aria-hidden svg beside Average · Max, one rect per done task, oldest left, height by rounds', async () => {
  mockFetch({ 'GET /api/pages/dashboard': [200, page({ done: DONE })] })
  renderAt('/')
  const section = (await screen.findByRole('heading', { name: /Rounds per task/ })).closest('section')
  const svgs = section.querySelectorAll('svg')
  expect(svgs).toHaveLength(1)
  const [svg] = svgs
  expect(svg.getAttribute('aria-hidden')).toBe('true')
  expect(svg.parentElement.contains(within(section).getByText(fullText('Average 1.5 · Max 2')))).toBe(true)
  const full = Number(svg.getAttribute('viewBox').split(' ')[3])
  const rects = [...svg.querySelectorAll('rect')]
  expect(rects.map((r) => r.querySelector('title').textContent)).toEqual(['#8 Add logout: 2 rounds', '#7 Add login: 1 round'])
  const heights = rects.map((r) => Number(r.getAttribute('height')))
  expect(heights).toEqual([full, full / 2]) // the max is full height; 2 rounds is twice 1
  rects.forEach((r, i) => expect(Number(r.getAttribute('y')) + heights[i]).toBe(full)) // bottom-aligned
  expect(Number(rects[0].getAttribute('x'))).toBeLessThan(Number(rects[1].getAttribute('x')))
  expect(within(section).getByRole('table')).toBeTruthy() // Q8: the per-task table stays
})

test('FE11: done: [] → the empty text and no svg', async () => {
  mockFetch({ 'GET /api/pages/dashboard': [200, page()] })
  renderAt('/')
  const section = (await screen.findByRole('heading', { name: /Rounds per task/ })).closest('section')
  expect(within(section).getByText('No tasks done in the last 30 days.')).toBeTruthy()
  expect(section.querySelector('svg')).toBeNull()
})

test('FE12: the open-tasks table sits in an overflow-x-auto box', async () => {
  const open_tasks = [{ id: 1, name: 'personal', projects: [{ id: 3, name: 'api', backlog: 2, in_progress: 1, review: 0 }] }]
  mockFetch({ 'GET /api/pages/dashboard': [200, page({ open_tasks })] })
  renderAt('/')
  const section = (await screen.findByRole('heading', { name: 'Open tasks' })).closest('section')
  expect(within(section).getByRole('table').parentElement.className).toMatch(cls('overflow-x-auto'))
})
