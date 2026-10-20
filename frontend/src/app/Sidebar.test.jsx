import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { fetched, fullText, mockFetch, renderAt } from '../test/render.jsx'

const SIDEBAR = '/api/pages/sidebar'
const KEY = 'sidebar.workspace'

/** A SidebarProject; the frontend ignores the three counts (Q2). */
const project = (id, name) => ({ id, name, review: 0, running: 0, escalated: 0 })
const PERSONAL = { id: 2, name: 'personal', projects: [project(3, 'api-server'), project(7, 'web')] }
const WORK = { id: 5, name: 'work', projects: [project(4, 'billing')] }
/** GET /api/pages/sidebar, ordered by name as the backend sends it. */
const body = (current = null, workspaces = [PERSONAL, WORK]) => [200, { workspaces, current }]

beforeEach(() => localStorage.clear())
afterEach(() => vi.restoreAllMocks())

const sidebar = () => within(screen.getByRole('navigation', { name: 'Sidebar' }))
const workspace = () => sidebar().findByRole('combobox', { name: 'Workspace' })
const shown = (select) => select.selectedOptions[0].textContent
const projectButton = (name) => sidebar().queryByRole('button', { name })
/** The Board and Code list a project's button controls. */
const linksOf = (name) => within(document.getElementById(projectButton(name).getAttribute('aria-controls')))
const accent = /(^|\s)text-accent(\s|$)/
const settle = () => act(() => new Promise((resolve) => setTimeout(resolve, 20)))

/** Renders `path` with the sidebar answering `reply` at `url`, and waits for its combobox. */
async function open(path, reply = body(), url = SIDEBAR, more = {}) {
  const responses = { [`GET ${url}`]: reply, ...more }
  const fetch = mockFetch(responses)
  const view = renderAt(path)
  const select = await workspace()
  return { fetch, responses, select, ...view }
}

test("FE5: on /projects/4 the project's workspace wins over storage and a null current", async () => {
  localStorage.setItem(KEY, '2')
  const { select } = await open('/projects/4')
  expect(shown(select)).toBe('work')
  expect(projectButton('billing')).toBeTruthy()
  expect(projectButton('api-server')).toBeNull()
  expect(projectButton('web')).toBeNull()
  expect(localStorage.getItem(KEY)).toBe('5') // Q6: a route's choice is kept too
})

test("FE6: on /tasks/12, current selects work and opens project 4's disclosure", async () => {
  localStorage.setItem(KEY, '2')
  const { select } = await open('/tasks/12', body({ workspace_id: 5, project_id: 4 }), `${SIDEBAR}?task=12`)
  expect(shown(select)).toBe('work')
  expect(projectButton('billing').getAttribute('aria-expanded')).toBe('true')
  expect(linksOf('billing').getByRole('link', { name: 'Board' }).getAttribute('href')).toBe('/projects/4')
})

test('FE7: /workspaces/5 selects work even when storage says 2', async () => {
  localStorage.setItem(KEY, '2')
  const { select } = await open('/workspaces/5')
  expect(shown(select)).toBe('work')
  expect(projectButton('billing')).toBeTruthy()
})

test('FE8: with no route workspace, storage picks it; an unlisted id or a throwing getItem falls back to the first', async () => {
  localStorage.setItem(KEY, '5')
  let view = await open('/')
  expect(shown(view.select)).toBe('work')
  view.unmount()

  localStorage.setItem(KEY, '99')
  view = await open('/')
  expect(shown(view.select)).toBe('personal')
  view.unmount()

  localStorage.setItem(KEY, '5')
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new DOMException('The operation is insecure.', 'SecurityError')
  })
  view = await open('/')
  expect(shown(view.select)).toBe('personal')
  expect(projectButton('api-server')).toBeTruthy()
})

test('FE8: with no workspaces there is no combobox, and the empty message says how to add one', async () => {
  mockFetch({ [`GET ${SIDEBAR}`]: body(null, []) })
  renderAt('/')
  const message = await sidebar().findByText(
    fullText('No workspaces yet. Run fctl connect --workspace <name> in a repo, or add one with + New workspace.'),
  )
  expect(message.querySelector('code').textContent).toBe('fctl connect --workspace <name>')
  expect(sidebar().queryByRole('combobox')).toBeNull()
  expect(sidebar().getByRole('button', { name: '+ New workspace' })).toBeTruthy()
})

test("FE9: choosing work lists its projects and stores 5 without navigating; a throwing setItem still switches", async () => {
  for (const throws of [false, true]) {
    localStorage.clear()
    if (throws) {
      vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
        throw new DOMException('Quota exceeded', 'QuotaExceededError')
      })
    }
    const { select, router, unmount } = await open('/')
    expect(shown(select)).toBe('personal')
    fireEvent.change(select, { target: { value: '5' } })
    expect(shown(select)).toBe('work')
    expect(projectButton('billing')).toBeTruthy()
    expect(projectButton('api-server')).toBeNull()
    expect(`${router.state.location.pathname}${router.state.location.search}`).toBe('/')
    if (!throws) expect(localStorage.getItem(KEY)).toBe('5')
    unmount()
  }
})

/** Opens + New workspace and submits `name`. */
function create(name) {
  fireEvent.click(sidebar().getByRole('button', { name: '+ New workspace' }))
  const field = sidebar().getByRole('textbox', { name: 'New workspace name' })
  fireEvent.change(field, { target: { value: name } })
  fireEvent.submit(field.closest('form'))
  return field
}

test('FE10: + New workspace reveals a field and Create; ops posts, opens /workspaces/9, and its refetch selects ops', async () => {
  const { fetch, responses, router } = await open('/', body(), SIDEBAR, {
    'POST /api/workspaces': [200, { id: 9, name: 'ops' }],
    'GET /api/pages/workspaces/9': [200, { workspace: { id: 9, name: 'ops' }, projects: [] }],
  })
  expect(sidebar().queryByRole('textbox')).toBeNull()
  fireEvent.click(sidebar().getByRole('button', { name: '+ New workspace' }))
  expect(sidebar().getByRole('textbox', { name: 'New workspace name' })).toBeTruthy()
  expect(sidebar().getByRole('button', { name: 'Create' })).toBeTruthy()
  fireEvent.click(sidebar().getByRole('button', { name: '+ New workspace' })) // hides it again
  responses[`GET ${SIDEBAR}`] = body(null, [{ id: 9, name: 'ops', projects: [] }, PERSONAL, WORK])
  create('ops')
  await waitFor(() => expect(router.state.location.pathname).toBe('/workspaces/9'))
  const [, init] = fetch.mock.calls.find(([url, i]) => url === '/api/workspaces' && i.method === 'POST')
  expect(init.body).toBe('{"name":"ops"}')
  expect(init.headers['X-Requested-By']).toBe('fctl')
  await waitFor(() => expect(shown(sidebar().getByRole('combobox', { name: 'Workspace' }))).toBe('ops'))
  expect(fetched(fetch).filter((url) => url === SIDEBAR)).toHaveLength(2)
})

test("FE10: a refused create shows its detail next to the field and doesn't navigate", async () => {
  const { router } = await open('/', body(), SIDEBAR, {
    'POST /api/workspaces': [422, { detail: 'name must not be blank' }],
  })
  const field = create('x')
  const alert = await sidebar().findByRole('alert')
  expect(alert.textContent).toBe('name must not be blank')
  expect(alert.closest('form')).toBe(field.closest('form'))
  expect(router.state.location.pathname).toBe('/')
})

test('FE10 (Q8): Cancel or Esc hides the field and returns focus to + New workspace', async () => {
  await open('/')
  const toggle = sidebar().getByRole('button', { name: '+ New workspace' })
  fireEvent.click(toggle)
  expect(toggle.getAttribute('aria-expanded')).toBe('true')
  const field = sidebar().getByRole('textbox', { name: 'New workspace name' })
  expect(field.required).toBe(true)
  expect(field.getAttribute('pattern')).toBe('.*\\S.*')
  fireEvent.click(sidebar().getByRole('button', { name: 'Cancel' }))
  expect(sidebar().queryByRole('textbox')).toBeNull()
  expect(document.activeElement).toBe(toggle)
  fireEvent.click(toggle)
  fireEvent.keyDown(sidebar().getByRole('textbox', { name: 'New workspace name' }), { key: 'Escape' })
  expect(sidebar().queryByRole('textbox')).toBeNull()
  expect(toggle.getAttribute('aria-expanded')).toBe('false')
})

test('FE11, 042 FE34: each project is a disclosure button for Board, Code, Reviews, Context, and Settings', async () => {
  await open('/')
  const button = projectButton('api-server')
  expect(button.getAttribute('aria-expanded')).toBe('false')
  const list = document.getElementById(button.getAttribute('aria-controls'))
  expect(list).toBeTruthy()
  expect(sidebar().queryByRole('link', { name: 'Board' })).toBeNull()
  fireEvent.click(button)
  expect(button.getAttribute('aria-expanded')).toBe('true')
  expect(within(list).getAllByRole('link').map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
    ['Board', '/projects/3'],
    ['Code', '/projects/3/code'],
    ['Reviews', '/projects/3/reviews'],
    ['Context', '/projects/3/context'],
    ['Settings', '/projects/3/settings'],
  ])
  fireEvent.click(button)
  expect(button.getAttribute('aria-expanded')).toBe('false')
  expect(within(list).queryAllByRole('link')).toEqual([])
})

test("042 FE35: Reviews shows the project's review count above 0, and no number at 0", async () => {
  const counted = { id: 2, name: 'personal', projects: [{ ...project(3, 'api-server'), review: 2 }, project(7, 'web')] }
  await open('/', body(null, [counted]))
  fireEvent.click(projectButton('api-server'))
  fireEvent.click(projectButton('web'))
  expect(linksOf('api-server').getByRole('link', { name: 'Reviews 2' }).getAttribute('href')).toBe('/projects/3/reviews')
  const zero = linksOf('web').getByRole('link', { name: 'Reviews' })
  expect(zero.textContent).toBe('Reviews')
  expect(zero.getAttribute('href')).toBe('/projects/7/reviews')
})

test('FE12: on /projects/3 project 3 opens by itself and Board is the current link', async () => {
  await open('/projects/3')
  expect(projectButton('api-server').getAttribute('aria-expanded')).toBe('true')
  const board = linksOf('api-server').getByRole('link', { name: 'Board' })
  const code = linksOf('api-server').getByRole('link', { name: 'Code' })
  expect(board.getAttribute('aria-current')).toBe('page')
  expect(board.className).toMatch(accent)
  expect(code.hasAttribute('aria-current')).toBe(false)
  expect(code.className).not.toMatch(accent)
})

test('FE12: on /projects/3/code?path=… Code is the current link', async () => {
  await open('/projects/3/code?path=src%2Fa.py')
  expect(projectButton('api-server').getAttribute('aria-expanded')).toBe('true')
  const board = linksOf('api-server').getByRole('link', { name: 'Board' })
  const code = linksOf('api-server').getByRole('link', { name: 'Code' })
  expect(code.getAttribute('aria-current')).toBe('page')
  expect(code.className).toMatch(accent)
  expect(board.hasAttribute('aria-current')).toBe(false)
  expect(board.className).not.toMatch(accent)
})

test('FE12 (Q9): on /tasks/12/review project 3 opens and neither link is current', async () => {
  await open('/tasks/12/review', body({ workspace_id: 2, project_id: 3 }), `${SIDEBAR}?task=12`)
  expect(projectButton('api-server').getAttribute('aria-expanded')).toBe('true')
  for (const link of linksOf('api-server').getAllByRole('link')) {
    expect(link.hasAttribute('aria-current')).toBe(false)
    expect(link.className).not.toMatch(accent)
  }
})

test("FE13: open projects stay open across a navigation", async () => {
  const both = { id: 2, name: 'personal', projects: [project(3, 'api-server'), project(4, 'web')] }
  const { fetch, router } = await open('/projects/3', body(null, [both]))
  fireEvent.click(projectButton('web'))
  fireEvent.click(linksOf('api-server').getByRole('link', { name: 'Code' }))
  await waitFor(() => expect(router.state.location.pathname).toBe('/projects/3/code'))
  await waitFor(() => expect(fetched(fetch).filter((url) => url === SIDEBAR)).toHaveLength(2))
  await settle()
  expect(projectButton('api-server').getAttribute('aria-expanded')).toBe('true')
  expect(projectButton('web').getAttribute('aria-expanded')).toBe('true')
})

test('FE14: workspace and project names render as text', async () => {
  const { select } = await open('/', body(null, [{ id: 2, name: '<i>w</i>', projects: [project(3, '<b>x</b>')] }]))
  expect(shown(select)).toBe('<i>w</i>')
  expect(projectButton('<b>x</b>')).toBeTruthy()
  expect(screen.getByRole('navigation', { name: 'Sidebar' }).querySelector('b, i')).toBeNull()
})

test("FE15: a failed load keeps the sidebar, says Projects didn't load with no alert, and the next navigation retries", async () => {
  const PRO = { auth_method: 'claude.ai', plan: 'pro', runs_enabled: true, email: null }
  for (const failure of [[500, { detail: 'boom' }], new TypeError('Failed to fetch')]) {
    const responses = {
      'GET /api/auth': [200, PRO],
      [`GET ${SIDEBAR}`]: failure,
      'GET /api/docs/fctl': [200, { body_html: '', headings: [] }],
    }
    mockFetch(responses)
    const { unmount } = renderAt('/docs/fctl')
    const message = await sidebar().findByText("Projects didn't load")
    expect(message.className).toMatch(/(^|\s)text-muted(\s|$)/)
    expect(message.closest('[role="alert"]')).toBeNull()
    expect(sidebar().queryByRole('alert')).toBeNull()
    expect(await sidebar().findByRole('link', { name: 'Claude: Pro ✓' })).toBeTruthy()
    for (const name of ['Claude Factories', 'Dashboard', 'fctl reference']) {
      expect(sidebar().getByRole('link', { name })).toBeTruthy()
    }
    expect(await screen.findByRole('heading', { level: 1, name: 'fctl reference' })).toBeTruthy()
    responses[`GET ${SIDEBAR}`] = body()
    fireEvent.click(sidebar().getByRole('link', { name: 'Dashboard' }))
    expect(shown(await workspace())).toBe('personal')
    expect(sidebar().queryByText("Projects didn't load")).toBeNull()
    unmount()
  }
})

test('FE16: a workspace with no projects says how to connect one, with the command in <code>', async () => {
  await open('/', body(null, [{ id: 5, name: 'work', projects: [] }]))
  expect(sidebar().getByText(fullText('No projects. Run fctl connect --workspace work in a repo.'))).toBeTruthy()
  expect(sidebar().getByText('fctl connect --workspace work').tagName).toBe('CODE')
})
