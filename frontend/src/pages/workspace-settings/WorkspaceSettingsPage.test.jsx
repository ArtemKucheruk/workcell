import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { expectSkeleton, fetched, mockFetch, renderAt } from '../../test/render.jsx'

const PAGE = '/api/pages/workspaces/5'
const SIDEBAR = '/api/pages/sidebar'
const PROJECTS = [
  { id: 3, name: 'api', path: '/Users/me/api', backlog: 2, in_progress: 1, review: 0, done: 7,
    last_activity: '2026-10-18T09:05:00Z', factory: 'ready' },
  { id: 4, name: 'web', path: '/Users/me/web', backlog: 0, in_progress: 0, review: 1, done: 0,
    last_activity: null, factory: 'none' },
]
/** 041's workspace view-model, unchanged. */
const workspace = (name = 'work', projects = PROJECTS) => [200, { workspace: { id: 5, name }, projects }]
const WORKSPACE_TEXT = 'This removes the workspace from the app. It must hold no projects: move or delete them first.'

afterEach(() => vi.useRealTimers())

/** Renders /workspaces/5/settings with `reply` as its view-model; mutate `responses` to change later replies. */
async function open(reply = workspace(), more = {}) {
  const responses = { [`GET ${PAGE}`]: reply, ...more }
  const fetch = mockFetch(responses)
  const view = renderAt('/workspaces/5/settings')
  await screen.findByRole('heading', { level: 1 })
  return { fetch, responses, ...view }
}

const loads = (fetch, url = PAGE) => fetched(fetch).filter((u) => u === url).length
const section = (name) => screen.getByRole('region', { name })
const nameBox = () => within(screen.getByRole('main')).getByRole('textbox', { name: 'Name' })
const sends = (fetch, method, url) => fetch.mock.calls.filter(([u, init]) => u === url && init?.method === method)
/** The one `method url` call: asserts its X-Requested-By and returns its body as sent. */
function sent(fetch, method, url) {
  const calls = sends(fetch, method, url)
  expect(calls).toHaveLength(1)
  expect(calls[0][1].headers['X-Requested-By']).toBe('fctl')
  return calls[0][1].body
}

test('049 FE20: the page shows the skeleton, then fetches the workspace view-model once, and titles itself', async () => {
  vi.useFakeTimers()
  let answer
  const fetch = mockFetch({ [`GET ${SIDEBAR}`]: [200, { workspaces: [], current: null }] })
  fetch.mockImplementation(async (url) =>
    url === PAGE ? new Promise((resolve) => (answer = resolve)) : new Response('{}', { status: 404 }),
  )
  renderAt('/workspaces/5/settings')
  await act(() => vi.advanceTimersByTimeAsync(0))
  const main = within(screen.getByRole('main'))
  expectSkeleton(main.getByRole('status'))
  expect(main.queryByRole('heading')).toBeNull()
  await act(async () => answer(new Response(JSON.stringify(workspace()[1]), { status: 200 })))
  await act(() => vi.advanceTimersByTimeAsync(0))
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('work')
  expect(main.queryByRole('status')).toBeNull()
  expect(document.title).toBe('work · Settings · Claude Factories')
  await act(() => vi.advanceTimersByTimeAsync(10_000))
  expect(loads(fetch)).toBe(1)
  expect(within(screen.getByRole('main')).queryByRole('navigation', { name: 'Breadcrumb' })).toBeNull() // Q14
})

test('049 FE20: a 404 is the not-found page', async () => {
  mockFetch({ [`GET ${PAGE}`]: [404, { detail: 'Workspace #5 not found' }] })
  renderAt('/workspaces/5/settings')
  expect(await screen.findByRole('heading', { level: 1, name: 'Workspace #5 not found' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Go to the dashboard' }).getAttribute('href')).toBe('/')
})

test('049 FE21: Save sends PATCH /api/workspaces/5 {name}; on 200 the view-model and the sidebar reload', async () => {
  const { fetch, responses } = await open(workspace(), { 'PATCH /api/workspaces/5': [200, { id: 5, name: 'office' }] })
  await waitFor(() => expect(loads(fetch, SIDEBAR)).toBe(1))
  expect(nameBox().value).toBe('work')
  fireEvent.change(nameBox(), { target: { value: ' office ' } })
  responses[`GET ${PAGE}`] = workspace('office')
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'office' })).toBeTruthy()
  expect(JSON.parse(sent(fetch, 'PATCH', '/api/workspaces/5'))).toEqual({ name: ' office ' })
  expect(loads(fetch)).toBe(2)
  await waitFor(() => expect(loads(fetch, SIDEBAR)).toBe(2))
  expect(nameBox().value).toBe('office')
  expect(screen.getByText('Saved.')).toBeTruthy()
})

test('049 FE21: a 409 shows its detail in the form, which keeps the typed name', async () => {
  const { fetch } = await open(workspace(), {
    'PATCH /api/workspaces/5': [409, { detail: 'workspace personal already exists' }],
  })
  fireEvent.change(nameBox(), { target: { value: 'personal' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe('workspace personal already exists')
  expect(alert.closest('form')).toBe(nameBox().closest('form'))
  expect(nameBox().value).toBe('personal')
  expect(loads(fetch)).toBe(1)
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('work')
})

test("049 FE22: Projects lists each project's name, linking to its Settings, and its path; with none it says No projects.", async () => {
  const { unmount } = await open()
  const rows = within(section('Projects')).getAllByRole('listitem')
  expect(rows.map((li) => [within(li).getByRole('link').textContent, within(li).getByRole('link').getAttribute('href'), li.textContent])).toEqual([
    ['api', '/projects/3/settings', 'api/Users/me/api'],
    ['web', '/projects/4/settings', 'web/Users/me/web'],
  ])
  unmount()
  await open(workspace('work', []))
  expect(within(section('Projects')).getByText('No projects.')).toBeTruthy()
  expect(within(section('Projects')).queryByRole('list')).toBeNull()
})

test('049 FE23: the last section, Danger zone, has Delete workspace: the dialog, then DELETE and /; a 409 stays in the dialog', async () => {
  const HOLDS = 'workspace work still holds 2 projects; move or delete them first'
  for (const [reply, refused] of [[[409, { detail: HOLDS }], true], [[204], false]]) {
    const { fetch, router, unmount } = await open(workspace(), { 'DELETE /api/workspaces/5': reply })
    expect(screen.getAllByRole('region').at(-1)).toBe(section('Danger zone'))
    const button = within(section('Danger zone')).getByRole('button', { name: 'Delete workspace' })
    expect(button.className).toMatch(/(^|\s)bg-danger(\s|$)/)
    fireEvent.click(button)
    const dialog = screen.getByRole('dialog', { name: 'Delete workspace work?' })
    expect(document.getElementById(dialog.getAttribute('aria-describedby')).textContent).toBe(WORKSPACE_TEXT)
    expect(within(dialog).getAllByRole('button').map((b) => b.textContent)).toEqual(['Cancel', 'Delete'])
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    if (refused) {
      const alert = await within(dialog).findByRole('alert')
      expect(alert.textContent).toBe(HOLDS)
      expect(dialog.open).toBe(true)
      expect(router.state.location.pathname).toBe('/workspaces/5/settings')
    } else {
      await waitFor(() => expect(router.state.location.pathname).toBe('/'))
    }
    expect(sent(fetch, 'DELETE', '/api/workspaces/5')).toBeUndefined()
    unmount()
  }
})
