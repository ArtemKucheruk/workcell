import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { expectOfflineBanner, fetched, mockFetch, renderAt } from '../../test/render.jsx'
import { optionLabels, pick as pickOption } from '../../test/select.js'

const PROJECT = {
  id: 3, name: 'api', path: '/home/me/api', default_branch: 'main', workspace_id: 2, workspace: 'personal',
  remote_url: null, test_cmd: 'pytest -q',
}
const BOARD = '/api/pages/projects/3'

/** A Card as 042's API contract has it, with `branch`. */
const card = (id, status, extra = {}) => ({
  id, title: `Task ${id}`, status, stage: null, round: null, verdicts: null, additions: null, deletions: null,
  run: null, position: id, started_at: null, waiting: false, escalated: false, stalled: false, branch: null, ...extra,
})
const waiting = (id, extra) => card(id, 'review', { stage: 'human_review', waiting: true, ...extra })
const escalated = (id, extra) => card(id, 'review', { stage: 'escalated', escalated: true, ...extra })
const board = (columns = {}) => ({
  project: PROJECT, factory: 'ready', hint: null, can_run: true, workspaces: [{ id: 2, name: 'personal', projects: 1 }],
  columns: { backlog: [], in_progress: [], review: [], done: [], ...columns },
})

afterEach(() => {
  vi.useRealTimers()
})

/** Renders `at` with `page` as the board view-model, and waits for the h1. */
async function open(page, at = '/projects/3/reviews') {
  const responses = { [`GET ${BOARD}`]: [200, page] }
  const fetch = mockFetch(responses)
  const view = renderAt(at)
  await screen.findByRole('heading', { level: 1 })
  return { fetch, responses, ...view }
}

const loads = (fetch) => fetched(fetch).filter((url) => url === BOARD).length
const tabs = () => screen.getByRole('navigation', { name: 'Reviews tabs' })
/** The listed rows' `#id title` links, in order. */
const listed = () => [...document.querySelectorAll('main li')].map((li) => within(li).getAllByRole('link')[0].textContent)
const row = (id) => screen.getByRole('link', { name: new RegExp(`^#${id} `) }).closest('li')
const advance = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))
const cls = (name) => new RegExp(`(^|\\s)${name}(\\s|$)`)

test('FE8: the page fetches the board view-model on load and again 3000 ms after each load settles', async () => {
  vi.useFakeTimers()
  const responses = { [`GET ${BOARD}`]: [200, board({ review: [waiting(12)] })] }
  const fetch = mockFetch(responses)
  renderAt('/projects/3/reviews')
  await advance(0)
  expect(loads(fetch)).toBe(1)
  expect(listed()).toEqual(['#12 Task 12'])
  responses[`GET ${BOARD}`] = [200, board({ review: [waiting(12), waiting(13)] })]
  await advance(2999)
  expect(loads(fetch)).toBe(1)
  await advance(1)
  expect(loads(fetch)).toBe(2)
  expect(listed()).toEqual(['#12 Task 12', '#13 Task 13'])
  await advance(3000)
  expect(loads(fetch)).toBe(3)
})

test('FE9: Open lists the Review column, escalated, then waiting, then null stage, each in view-model order', async () => {
  await open(board({
    backlog: [card(1, 'backlog')],
    review: [waiting(21), card(22, 'review'), escalated(23), waiting(24)],
    done: [card(9, 'done', { round: 1 })],
  }))
  expect(listed()).toEqual(['#23 Task 23', '#21 Task 21', '#24 Task 24', '#22 Task 22'])
})

test('FE10: ?tab=closed lists the Done column in view-model order; any other tab is Open', async () => {
  const page = board({ review: [waiting(12)], done: [card(8, 'done'), card(5, 'done'), card(9, 'done')] })
  const closed = await open(page, '/projects/3/reviews?tab=closed')
  expect(listed()).toEqual(['#8 Task 8', '#5 Task 5', '#9 Task 9'])
  closed.unmount()
  await open(page, '/projects/3/reviews?tab=bogus')
  expect(listed()).toEqual(['#12 Task 12'])
})

test('FE11: two tab links with counts and aria-current; clicking Closed changes the URL and fetches nothing', async () => {
  const { fetch, router } = await open(board({ review: [waiting(12), card(13, 'review')], done: [card(8, 'done')] }))
  const nav = within(tabs())
  const open_ = nav.getByRole('link', { name: 'Open 2' })
  const closed = nav.getByRole('link', { name: 'Closed 1' })
  expect(nav.getAllByRole('link')).toEqual([open_, closed])
  expect(open_.getAttribute('href')).toBe('/projects/3/reviews')
  expect(closed.getAttribute('href')).toBe('/projects/3/reviews?tab=closed')
  expect(open_.getAttribute('aria-current')).toBe('page')
  expect(closed.hasAttribute('aria-current')).toBe(false)
  fireEvent.click(closed)
  await waitFor(() => expect(router.state.location.search).toBe('?tab=closed'))
  expect(listed()).toEqual(['#8 Task 8'])
  expect(nav.getByRole('link', { name: 'Closed 1' }).getAttribute('aria-current')).toBe('page')
  expect(nav.getByRole('link', { name: 'Open 2' }).hasAttribute('aria-current')).toBe(false)
  await act(() => new Promise((resolve) => setTimeout(resolve, 20)))
  expect(loads(fetch)).toBe(1)
})

test('FE12: a row links to the review, with branch, round, shared chips, and +/−; null parts are left out', async () => {
  await open(board({
    review: [
      waiting(12, {
        title: 'Rate-limit login endpoint', branch: 'factory/12-rate-limit-login', round: 2, additions: 126, deletions: 9,
        verdicts: { security: 'PASS', ux: 'PASS', ui: 'pending', code: 'CHANGES' },
      }),
      waiting(14, { branch: 'factory/14-x' }),
      waiting(15, { round: 1, additions: 3, deletions: 0, verdicts: { security: 'PASS', ux: 'PASS', ui: 'PASS', code: 'PASS' } }),
    ],
  }))
  const li = row(12)
  const link = within(li).getByRole('link', { name: '#12 Rate-limit login endpoint' })
  expect(link.getAttribute('href')).toBe('/tasks/12/review')
  expect(li.querySelector('code').textContent).toBe('factory/12-rate-limit-login')
  expect(within(li).getByText('round 2')).toBeTruthy()
  expect([...li.querySelectorAll('[title]')].map((s) => [s.tagName, s.textContent, s.title])).toEqual([
    ['SPAN', 'sec ✓', 'security: PASS'], ['SPAN', 'ux ✓', 'ux: PASS'], ['SPAN', 'ui ·', 'ui: pending'], ['SPAN', 'code ✗', 'code: CHANGES'],
  ])
  // 043 FE13: colored as in FE5
  expect([...li.querySelectorAll('[title]')].map((s) => ['text-success', 'text-danger', 'text-muted'].find((c) => cls(c).test(s.className)))).toEqual([
    'text-success', 'text-success', 'text-muted', 'text-danger',
  ])
  expect(within(li).queryByRole('button')).toBeNull() // no `posted`: plain chips
  expect(within(li).getByText('+126 −9')).toBeTruthy()

  expect(row(14).querySelector('code').textContent).toBe('factory/14-x') // round null: no round, chips, or +/−
  expect(row(14).querySelectorAll('[title]')).toHaveLength(0)
  expect(row(14).textContent).not.toMatch(/round|\+\d|−/)
  expect(row(15).querySelector('code')).toBeNull() // branch null: no branch
  expect(within(row(15)).getByText('round 1')).toBeTruthy()
})

test('FE13, 043 FE13: escalated Open rows have the escalated pill and red bar, waiting ones the waiting pill; null stage and Closed rows neither', async () => {
  const page = board({
    review: [escalated(11), waiting(12), card(13, 'review')],
    done: [card(9, 'done', { stage: 'escalated', escalated: true }), card(8, 'done', { stage: 'human_review', waiting: true })],
  })
  const { unmount } = await open(page)
  const pill = within(row(11)).getByText('escalated')
  expect(pill.className).toMatch(cls('bg-danger'))
  expect(pill.className).toMatch(cls('text-surface'))
  expect(row(11).className).toMatch(/(^|\s)border-danger(\s|$)/)
  expect(within(row(11)).queryByText('waiting on you')).toBeNull()
  expect(within(row(12)).getByText('waiting on you').className).toMatch(cls('bg-warning'))
  expect(within(row(12)).queryByText('escalated')).toBeNull()
  for (const id of [12, 13]) expect(row(id).className).not.toMatch(/(^|\s)border-danger(\s|$)/)
  expect(row(13).textContent).toBe('#13 Task 13')
  unmount()
  await open(page, '/projects/3/reviews?tab=closed')
  for (const id of [9, 8]) {
    expect(row(id).textContent).toBe(`#${id} Task ${id}`)
    expect(row(id).className).not.toMatch(/(^|\s)border-danger(\s|$)/)
  }
})

test('FE14: an empty Open and an empty Closed say so', async () => {
  const { unmount } = await open(board())
  expect(screen.getByText('Nothing waiting for review.')).toBeTruthy()
  expect(document.querySelector('main li')).toBeNull()
  unmount()
  await open(board({ review: [waiting(12)] }), '/projects/3/reviews?tab=closed')
  expect(screen.getByText('No closed reviews yet.')).toBeTruthy()
  expect(screen.queryByText('Nothing waiting for review.')).toBeNull()
})

test('FE15, 046 FE11, FE12, FE13: the title; a 404 is not-found; a failed first load is the alert alone; a failed poll keeps the list under the offline banner', async () => {
  const { unmount } = await open(board())
  await waitFor(() => expect(document.title).toBe('api · Reviews · Claude Factories'))
  unmount()

  mockFetch({ 'GET /api/pages/projects/99': [404, { detail: 'Project #99 not found' }] })
  const missing = renderAt('/projects/99/reviews')
  expect(await screen.findByRole('heading', { level: 1, name: 'Project #99 not found' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Go to the dashboard' }).getAttribute('href')).toBe('/')
  missing.unmount()

  mockFetch({ [`GET ${BOARD}`]: [500, { detail: 'boom' }] })
  const first = renderAt('/projects/3/reviews')
  expect((await screen.findByRole('alert')).textContent).toBe('boom')
  expect(screen.queryByRole('heading', { level: 1 })).toBeNull()
  expect(screen.queryByRole('navigation', { name: 'Reviews tabs' })).toBeNull()
  first.unmount()

  vi.useFakeTimers()
  const responses = { [`GET ${BOARD}`]: [200, board({ review: [waiting(12)] })] }
  mockFetch(responses)
  renderAt('/projects/3/reviews')
  await advance(0)
  expect(listed()).toEqual(['#12 Task 12'])
  await expectOfflineBanner(responses, `GET ${BOARD}`, () => expect(listed()).toEqual(['#12 Task 12']))
})

// --- 117: the filter bar --------------------------------------------------------------

const MODULES = '/api/projects/3/modules'
const LISTED = {
  modules: [{ id: 5, name: 'backend', description_md: '', counts: {} }, { id: 7, name: 'frontend', description_md: '', counts: {} }],
  no_module: {},
}
const BACKEND = { id: 5, name: 'backend' }
/** Open: 11 (login, backend), 12 (no module), 13 (login, frontend). Closed: 8 (login, backend), 9 (no module). */
const FILTERABLE = board({
  review: [
    waiting(11, { title: 'Rate-limit login', module: BACKEND }),
    waiting(12, { title: 'Dark mode', module: null }),
    escalated(13, { title: 'Login copy', module: { id: 7, name: 'frontend' } }),
  ],
  done: [card(8, 'done', { title: 'Login form', module: BACKEND }), card(9, 'done', { title: 'Health', module: null })],
})

/** Renders `at` over `page`, with the modules listed unless `modules` is false; waits for the h1. */
async function openFiltered(at, page = FILTERABLE, modules = true) {
  const responses = { [`GET ${BOARD}`]: [200, page], ...(modules && { [`GET ${MODULES}`]: [200, LISTED] }) }
  const fetch = mockFetch(responses)
  const view = renderAt(at)
  await screen.findByRole('heading', { level: 1 })
  if (modules) await waitFor(() => expect(moduleFilter()).not.toBeNull())
  return { fetch, responses, ...view }
}
const search = () => screen.getByRole('searchbox', { name: 'Filter by #id or title' })
const typeIn = (value) => fireEvent.change(search(), { target: { value } })
const moduleFilter = () => document.getElementById('task-filter-module')
const tabNames = () => within(tabs()).getAllByRole('link').map((a) => a.textContent)
const said = () => screen.getAllByRole('status').find((el) => el.className.includes('sr-only'))

test('117 AC1, Q6: a labelled search field above the tabs; the Module select only when the project has modules', async () => {
  const { unmount } = await openFiltered('/projects/3/reviews', FILTERABLE, false)
  expect(search().getAttribute('type')).toBe('search')
  expect(search().compareDocumentPosition(tabs()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(moduleFilter()).toBeNull()
  unmount()
  const { fetch } = await openFiltered('/projects/3/reviews')
  expect(screen.getByRole('combobox', { name: 'Module' })).toBe(moduleFilter())
  expect(optionLabels(moduleFilter())).toEqual(['All modules', 'No module', 'backend', 'frontend'])
  expect(fetched(fetch).filter((u) => u === MODULES)).toHaveLength(1)
})

test('117 AC2: the text filter matches #id exactly, digits by id or title, and other text by title, ignoring case', async () => {
  await openFiltered('/projects/3/reviews', FILTERABLE, false)
  for (const [q, rows] of [
    ['LOGIN', ['#13 Login copy', '#11 Rate-limit login']], ['#12', ['#12 Dark mode']], ['13', ['#13 Login copy']], ['#1', []],
    ['  dark ', ['#12 Dark mode']], ['', ['#13 Login copy', '#11 Rate-limit login', '#12 Dark mode']],
  ]) {
    typeIn(q)
    expect(listed()).toEqual(rows)
  }
})

test('117 AC3: No module and a module filter the rows; text and module must both match', async () => {
  await openFiltered('/projects/3/reviews')
  pickOption(moduleFilter(), 'none')
  expect(listed()).toEqual(['#12 Dark mode'])
  pickOption(moduleFilter(), '5')
  expect(listed()).toEqual(['#11 Rate-limit login'])
  typeIn('login')
  expect(listed()).toEqual(['#11 Rate-limit login'])
  pickOption(moduleFilter(), '7')
  expect(listed()).toEqual(['#13 Login copy'])
})

test('117 AC4: the filter replaces ?q= and ?module=, keeps ?tab=, and a loaded URL fills and applies it', async () => {
  const { router, unmount } = await openFiltered('/projects/3/reviews?tab=closed')
  typeIn('login')
  expect(router.state.location.search).toBe('?tab=closed&q=login')
  expect(router.state.historyAction).toBe('REPLACE')
  pickOption(moduleFilter(), 'none')
  expect(router.state.location.search).toBe('?tab=closed&q=login&module=none')
  typeIn('')
  pickOption(moduleFilter(), '')
  expect(router.state.location.search).toBe('?tab=closed')
  unmount()
  await openFiltered('/projects/3/reviews?tab=closed&q=login&module=5')
  expect(search().value).toBe('login')
  expect(moduleFilter().textContent).toBe('backend')
  expect(listed()).toEqual(['#8 Login form'])
})

test('117 AC5: the filter survives a poll', async () => {
  vi.useFakeTimers()
  const responses = { [`GET ${BOARD}`]: [200, FILTERABLE] }
  const fetch = mockFetch(responses)
  renderAt('/projects/3/reviews')
  await advance(0)
  typeIn('login')
  expect(listed()).toEqual(['#13 Login copy', '#11 Rate-limit login'])
  responses[`GET ${BOARD}`] = [200, { ...FILTERABLE, columns: { ...FILTERABLE.columns, review: [...FILTERABLE.columns.review, waiting(14, { title: 'Login audit' })] } }]
  await advance(3000)
  expect(loads(fetch)).toBe(2)
  expect(search().value).toBe('login')
  expect(listed()).toEqual(['#13 Login copy', '#11 Rate-limit login', '#14 Login audit'])
})

test('117 AC6: the Open and Closed tab counts show the matching rows while filtered', async () => {
  await openFiltered('/projects/3/reviews')
  expect(tabNames()).toEqual(['Open 3', 'Closed 2'])
  typeIn('login')
  expect(tabNames()).toEqual(['Open 2', 'Closed 1'])
  pickOption(moduleFilter(), 'none')
  expect(tabNames()).toEqual(['Open 0', 'Closed 0'])
  typeIn('')
  expect(tabNames()).toEqual(['Open 1', 'Closed 1'])
})

test('117 AC7: the tab links carry the filter, so switching tabs keeps it and the field', async () => {
  const { router } = await openFiltered('/projects/3/reviews?q=login&module=5')
  const nav = within(tabs())
  expect(nav.getByRole('link', { name: /^Open/ }).getAttribute('href')).toBe('/projects/3/reviews?q=login&module=5')
  expect(nav.getByRole('link', { name: /^Closed/ }).getAttribute('href')).toBe('/projects/3/reviews?tab=closed&q=login&module=5')
  fireEvent.click(nav.getByRole('link', { name: /^Closed/ }))
  await waitFor(() => expect(router.state.location.search).toBe('?tab=closed&q=login&module=5'))
  expect(search().value).toBe('login')
  expect(listed()).toEqual(['#8 Login form'])
  typeIn('form')
  fireEvent.click(nav.getByRole('link', { name: /^Open/ }))
  await waitFor(() => expect(router.state.location.search).toBe('?q=form&module=5'))
  expect(search().value).toBe('form')
  expect(listed()).toEqual([])
})

test('117 AC8: no matching row says No reviews match. with Clear filter, which keeps the tab and focuses the field', async () => {
  const { router } = await openFiltered('/projects/3/reviews?tab=closed&q=zzz&module=5')
  expect(document.querySelector('main ul')).toBeNull()
  expect(screen.getByText('No reviews match.')).toBeTruthy()
  expect(screen.queryByText('No closed reviews yet.')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Clear filter' }))
  expect(router.state.location.search).toBe('?tab=closed')
  expect(search().value).toBe('')
  expect(document.activeElement).toBe(search())
  expect(listed()).toEqual(['#8 Login form', '#9 Health'])
})

test('117 AC9: Esc in the field clears it and ?q=, and the module filter stays', async () => {
  const { router } = await openFiltered('/projects/3/reviews?q=login&module=5')
  fireEvent.keyDown(search(), { key: 'Escape' })
  expect(search().value).toBe('')
  expect(router.state.location.search).toBe('?module=5')
  expect(listed()).toEqual(['#11 Rate-limit login'])
})

test("117 AC10, Q4: a filter change announces the current tab's match count in a hidden status region; clearing empties it", async () => {
  await openFiltered('/projects/3/reviews?tab=closed&q=log')
  expect(said().textContent).toBe('')
  typeIn('login')
  await waitFor(() => expect(said().textContent).toBe('1 review matches.'))
  typeIn('')
  await waitFor(() => expect(said().textContent).toBe(''))
  fireEvent.click(within(tabs()).getByRole('link', { name: /^Open/ }))
  await waitFor(() => expect(tabNames()).toEqual(['Open 3', 'Closed 2']))
  expect(said().textContent).toBe('')
  typeIn('o')
  await waitFor(() => expect(said().textContent).toBe('3 reviews match.'))
})
