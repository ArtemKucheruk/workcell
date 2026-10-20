import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { expectOfflineBanner, fetched, mockFetch, renderAt } from '../../test/render.jsx'

const PROJECT = {
  id: 3, name: 'api', path: '/Users/me/api', default_branch: 'main', workspace_id: 2, workspace: 'personal',
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
