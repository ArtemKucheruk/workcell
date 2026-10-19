import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, test, vi } from 'vitest'
import { fetched, fullText, mockFetch, renderAt } from '../../test/render.jsx'

const PROJECTS = [
  { id: 3, name: 'api', path: '/Users/me/api', backlog: 2, in_progress: 1, review: 0, done: 7,
    last_activity: '2026-10-18T09:05:00Z', factory: 'ready' },
  { id: 4, name: 'web', path: '/Users/me/web', backlog: 0, in_progress: 0, review: 1, done: 0,
    last_activity: '2026-10-01T00:00:00Z', factory: 'none' },
]
const workspace = (id, name, projects = []) => [200, { workspace: { id, name }, projects }]

beforeEach(() => {
  vi.stubEnv('TZ', 'Asia/Tokyo') // UTC+9, as in the dashboard test
})

function submit(name) {
  fireEvent.change(screen.getByRole('textbox', { name: 'New workspace name' }), { target: { value: name } })
  fireEvent.submit(screen.getByRole('button', { name: '+ Workspace' }).closest('form'))
}

test('AC27: /workspaces/2 shows the name, title, and one row per project', async () => {
  const fetch = mockFetch({ 'GET /api/pages/workspaces/2': workspace(2, 'personal', PROJECTS) })
  renderAt('/workspaces/2')
  expect(await screen.findByRole('heading', { level: 1, name: 'personal' })).toBeTruthy()
  expect(fetched(fetch)).toContain('/api/pages/workspaces/2')
  await waitFor(() => expect(document.title).toBe('personal · Claude Factories')) // the title is set in an effect, after the heading renders
  const rows = screen.getAllByRole('row').slice(1)
  expect(rows.map((tr) => [...tr.querySelectorAll('td')].map((td) => td.textContent))).toEqual([
    ['api', '/Users/me/api', '2', '1', '0', '7', 'ready', '2026-10-18 18:05'],
    ['web', '/Users/me/web', '0', '0', '1', '0', 'none', '2026-10-01 09:00'],
  ])
  expect(rows.map((tr) => within(tr).getByRole('link').getAttribute('href'))).toEqual(['/projects/3', '/projects/4'])
  expect(rows[0].querySelector('time').getAttribute('datetime')).toBe('2026-10-18T09:05:00Z')
})

test('AC28: no projects says how to connect one to this workspace', async () => {
  mockFetch({ 'GET /api/pages/workspaces/2': workspace(2, 'personal') })
  renderAt('/workspaces/2')
  expect(
    await screen.findByText(fullText('No projects yet. Run fctl connect --workspace personal inside a repo.')),
  ).toBeTruthy()
})

test('AC29: + Workspace posts the name, then shows the new workspace', async () => {
  const fetch = mockFetch({
    'GET /api/pages/workspaces/2': workspace(2, 'personal'),
    'POST /api/workspaces': [200, { id: 5, name: 'work' }],
    'GET /api/pages/workspaces/5': workspace(5, 'work'),
  })
  const { router } = renderAt('/workspaces/2')
  await screen.findByRole('heading', { level: 1, name: 'personal' })
  submit('work')
  expect(await screen.findByRole('heading', { level: 1, name: 'work' })).toBeTruthy()
  const [, init] = fetch.mock.calls.find(([url, i]) => url === '/api/workspaces' && i.method === 'POST')
  expect(init.body).toBe('{"name":"work"}')
  expect(init.headers['X-Requested-By']).toBe('fctl')
  expect(router.state.location.pathname).toBe('/workspaces/5')
  expect(fetched(fetch)).toContain('/api/pages/workspaces/5')
})

test('AC30: a refused create shows the detail in an alert by the form and stays put', async () => {
  mockFetch({
    'GET /api/pages/workspaces/2': workspace(2, 'personal'),
    'POST /api/workspaces': [422, { detail: 'name must not be blank' }],
  })
  const { router } = renderAt('/workspaces/2')
  await screen.findByRole('heading', { level: 1, name: 'personal' })
  submit('x')
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe('name must not be blank')
  expect(alert.closest('form')).toBe(screen.getByRole('button', { name: '+ Workspace' }).closest('form'))
  expect(router.state.location.pathname).toBe('/workspaces/2')
})

test("AC31: the API's 404 shows the not-found state with its detail", async () => {
  mockFetch({ 'GET /api/pages/workspaces/999': [404, { detail: 'Not Found' }] })
  renderAt('/workspaces/999')
  expect(await screen.findByRole('heading', { name: 'Not Found' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Go to the dashboard' }).getAttribute('href')).toBe('/')
})

test('AC32: a failed workspace view-model shows its detail in an alert', async () => {
  for (const [status, detail] of [[500, 'boom'], [502, 'Backend unreachable at http://127.0.0.1:4545']]) {
    mockFetch({ 'GET /api/pages/workspaces/2': [status, { detail }] })
    const { unmount } = renderAt('/workspaces/2')
    expect((await screen.findByRole('alert')).textContent).toBe(detail)
    unmount()
  }
})
