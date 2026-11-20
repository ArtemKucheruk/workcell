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

test('FE11, 042 FE34, 051 FE6, 101 AC10: each project is a disclosure button for Board, Code, Reviews, Context, Workflows, and Settings', async () => {
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
    ['Workflows', '/projects/3/factories'],
    ['Settings', '/projects/3/settings'],
  ])
  fireEvent.click(button)
  expect(button.getAttribute('aria-expanded')).toBe('false')
  expect(within(list).queryAllByRole('link')).toEqual([])
})

test('051 FE6, 101 AC10: Workflows is the current page on the list and in a factory\'s designer, and no other link is', async () => {
  for (const path of ['/projects/3/factories', '/projects/3/factories/7']) {
    const { unmount } = await open(path)
    const links = linksOf('api-server').getAllByRole('link')
    expect(links.filter((a) => a.getAttribute('aria-current') === 'page').map((a) => a.textContent)).toEqual(['Workflows'])
    expect(linksOf('api-server').getByRole('link', { name: 'Workflows' }).className).toMatch(accent)
    unmount()
  }
})

test("042 FE35, 043 FE15: Reviews shows the project's review count above 0 as a warning pill, and no number at 0", async () => {
  const counted = { id: 2, name: 'personal', projects: [{ ...project(3, 'api-server'), review: 2 }, project(7, 'web')] }
  await open('/', body(null, [counted]))
  fireEvent.click(projectButton('api-server'))
  fireEvent.click(projectButton('web'))
  const reviews = linksOf('api-server').getByRole('link', { name: 'Reviews 2' })
  expect(reviews.getAttribute('href')).toBe('/projects/3/reviews')
  const pill = within(reviews).getByText('2')
  expect(pill.className.split(/\s+/)).toEqual(expect.arrayContaining(['rounded-full', 'bg-warning', 'text-surface']))
  const zero = linksOf('web').getByRole('link', { name: 'Reviews' })
  expect(zero.textContent).toBe('Reviews')
  expect(zero.querySelector('span')).toBeNull()
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

// --- 049: the ⋯ menus, rename in place, move, and delete ---------------------------------------------------------

const PROJECT_TEXT =
  'This removes its tasks, with their runs, rounds and their files, verdicts, comments, decisions, status history, and ' +
  'transcript records, from the app. The repo, its worktrees and branches, run logs, and copied transcript files stay on disk.'
const WORKSPACE_TEXT = 'This removes the workspace from the app. It must hold no projects: move or delete them first.'

const actionsOf = (name) => sidebar().getByRole('button', { name: `Actions for ${name}` })
const menuOf = (actions) => document.getElementById(actions.getAttribute('popovertarget'))
/** Chooses `item` in the ⋯ menu of `name` (a project, or `workspace personal`); jsdom has no Popover API, so it's hidden. */
const choose = (name, item, role = 'button') =>
  fireEvent.click(within(menuOf(actionsOf(name))).getByRole(role, { name: item, hidden: true }))
/** A menu's items in order, as `TAG text`. */
const itemsOf = (menu) => [...menu.querySelectorAll('button, a, p, hr')].map((el) => `${el.tagName} ${el.textContent}`.trim())
const sends = (fetch, method, url) => fetch.mock.calls.filter(([u, init]) => u === url && init?.method === method)
/** The one `method url` call: asserts its X-Requested-By and returns its body as sent. */
function sent(fetch, method, url) {
  const calls = sends(fetch, method, url)
  expect(calls).toHaveLength(1)
  expect(calls[0][1].headers['X-Requested-By']).toBe('fctl')
  return calls[0][1].body
}
const sidebarLoads = (fetch) => fetched(fetch).filter((url) => url === SIDEBAR).length
const renamed = (name) => sidebar().getByRole('textbox', { name })

test('049 FE1: each project row has an Actions for <project> ⋯ after its disclosure, for a popover menu of Rename, Settings, Move to workspace, Delete', async () => {
  await open('/')
  for (const [name, id, other] of [['api-server', 3, 'work'], ['web', 7, 'work']]) {
    const actions = actionsOf(name)
    const disclosure = projectButton(name)
    expect(actions.parentElement).toBe(disclosure.parentElement)
    expect(disclosure.compareDocumentPosition(actions) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    const menu = menuOf(actions)
    expect(menu.getAttribute('popover')).toBe('auto')
    expect(itemsOf(menu)).toEqual(['BUTTON Rename', 'A Settings', 'P Move to workspace', `BUTTON ${other}`, 'HR', 'BUTTON Delete'])
    const m = within(menu)
    expect(m.getByRole('link', { name: 'Settings', hidden: true }).getAttribute('href')).toBe(`/projects/${id}/settings`)
    expect(m.getByText('Move to workspace').className).toMatch(/(^|\s)text-muted(\s|$)/)
    const remove = m.getByRole('button', { name: 'Delete', hidden: true })
    expect(remove.className).toMatch(/(^|\s)text-danger(\s|$)/)
    expect(remove.className).not.toMatch(/(^|\s)text-(fg|muted)(\s|$)/) // no other color to win by CSS order
    for (const button of m.getAllByRole('button', { hidden: true })) {
      expect([button.getAttribute('popovertarget'), button.getAttribute('popovertargetaction')]).toEqual([menu.id, 'hide'])
    }
  }
})

test('049 FE1 (Q9): with no other workspace the menu leaves out the Move caption and buttons', async () => {
  await open('/', body(null, [PERSONAL]))
  expect(itemsOf(menuOf(actionsOf('api-server')))).toEqual(['BUTTON Rename', 'A Settings', 'HR', 'BUTTON Delete'])
})

test('049 FE2: beside the workspace select, Actions for workspace personal opens a menu of Rename, Settings, and Delete', async () => {
  const { select } = await open('/')
  const actions = actionsOf('workspace personal')
  expect(actions.parentElement).toBe(select.parentElement)
  expect(select.compareDocumentPosition(actions) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  const menu = menuOf(actions)
  expect(menu.getAttribute('popover')).toBe('auto')
  expect(itemsOf(menu)).toEqual(['BUTTON Rename', 'A Settings', 'HR', 'BUTTON Delete'])
  expect(within(menu).getByRole('link', { name: 'Settings', hidden: true }).getAttribute('href')).toBe('/workspaces/2/settings')
  expect(within(menu).getByRole('button', { name: 'Delete', hidden: true }).className).toMatch(/(^|\s)text-danger(\s|$)/)
  fireEvent.change(select, { target: { value: '5' } })
  expect(actionsOf('workspace work')).toBe(actions) // it follows the selected workspace
})

test('049 FE3 (Q16): every ⋯ is focusable and hidden only by md:opacity-0, shown on its row hover, focus, or open menu', async () => {
  await open('/')
  const all = sidebar().getAllByRole('button', { name: /^Actions for / })
  expect(all).toHaveLength(3)
  for (const actions of all) {
    const tokens = actions.className.split(/\s+/)
    expect(tokens).toEqual(
      expect.arrayContaining([
        'md:opacity-0',
        'md:group-hover/row:opacity-100',
        'md:group-focus-within/row:opacity-100',
        'md:group-has-[:popover-open]/row:opacity-100',
      ]),
    )
    // below md nothing hides it, and nothing anywhere takes it out of the layout or the Tab order
    expect(tokens.filter((t) => /(^|:)(opacity-0|hidden|invisible|sr-only)$/.test(t))).toEqual(['md:opacity-0'])
    expect(actions.hidden).toBe(false)
    expect(actions.tabIndex).toBe(0)
    actions.focus()
    expect(document.activeElement).toBe(actions)
    // its row is the group: the ⋯, what it acts on, and the menu
    const row = actions.closest('.group\\/row')
    expect(row.contains(menuOf(actions))).toBe(true)
    expect(row.querySelector('select, [aria-expanded]')).toBeTruthy()
  }
})

test('049 FE4: Settings in either menu navigates to that settings page and hides the menu', async () => {
  const { router } = await open('/')
  for (const [name, path] of [['api-server', '/projects/3/settings'], ['workspace personal', '/workspaces/2/settings']]) {
    const menu = menuOf(actionsOf(name))
    menu.hidePopover = vi.fn()
    choose(name, 'Settings', 'link')
    await waitFor(() => expect(router.state.location.pathname).toBe(path))
    expect(menu.hidePopover).toHaveBeenCalledOnce()
  }
})

test('049 FE5: Rename replaces the name with a focused input labelled Rename api-server, holding it all selected', async () => {
  await open('/')
  choose('api-server', 'Rename')
  const input = renamed('Rename api-server')
  expect(projectButton('api-server')).toBeNull()
  expect(input.value).toBe('api-server')
  expect(document.activeElement).toBe(input)
  expect([input.selectionStart, input.selectionEnd]).toEqual([0, 'api-server'.length])
  expect(actionsOf('api-server')).toBeTruthy() // the row keeps its ⋯
})

test('049 FE6: Enter sends PATCH {name}; on 200 the input goes, the sidebar reloads with the new name, and focus is on its ⋯', async () => {
  const { fetch, responses } = await open('/', body(), SIDEBAR, {
    'PATCH /api/projects/3': [200, { id: 3, workspace_id: 2, name: 'api2', test_cmd: null }],
  })
  choose('api-server', 'Rename')
  const input = renamed('Rename api-server')
  fireEvent.change(input, { target: { value: 'api2' } })
  responses[`GET ${SIDEBAR}`] = body(null, [{ ...PERSONAL, projects: [project(3, 'api2'), project(7, 'web')] }, WORK])
  fireEvent.submit(input.closest('form'))
  await waitFor(() => expect(projectButton('api2')).toBeTruthy())
  expect(JSON.parse(sent(fetch, 'PATCH', '/api/projects/3'))).toEqual({ name: 'api2' })
  expect(sidebar().queryByRole('textbox')).toBeNull()
  expect(sidebarLoads(fetch)).toBe(2)
  expect(document.activeElement).toBe(actionsOf('api2'))
})

test('049 FE7: Esc, or the input losing focus, removes it with no request; after Esc focus is on the ⋯', async () => {
  const { fetch } = await open('/')
  choose('api-server', 'Rename')
  fireEvent.change(renamed('Rename api-server'), { target: { value: 'nope' } })
  fireEvent.keyDown(renamed('Rename api-server'), { key: 'Escape' })
  expect(sidebar().queryByRole('textbox')).toBeNull()
  expect(projectButton('api-server')).toBeTruthy()
  expect(document.activeElement).toBe(actionsOf('api-server'))

  choose('api-server', 'Rename')
  fireEvent.change(renamed('Rename api-server'), { target: { value: 'nope' } })
  act(() => renamed('Rename api-server').blur())
  expect(sidebar().queryByRole('textbox')).toBeNull()
  expect(projectButton('api-server')).toBeTruthy()
  await settle()
  expect(fetch.mock.calls.filter(([, init]) => init?.method && init.method !== 'GET')).toEqual([])
  expect(sidebarLoads(fetch)).toBe(1)
})

test('049 FE8: a refused rename shows its detail beside the input, which stays with the typed text', async () => {
  const { fetch } = await open('/', body(), SIDEBAR, { 'PATCH /api/projects/3': [422, { detail: 'name must not be blank' }] })
  choose('api-server', 'Rename')
  const input = renamed('Rename api-server')
  fireEvent.change(input, { target: { value: '   ' } })
  fireEvent.submit(input.closest('form'))
  const alert = await sidebar().findByRole('alert')
  expect(alert.textContent).toBe('name must not be blank')
  expect(alert.closest('form')).toBe(input.closest('form'))
  expect(renamed('Rename api-server')).toBe(input)
  expect(input.value).toBe('   ')
  expect(JSON.parse(sent(fetch, 'PATCH', '/api/projects/3'))).toEqual({ name: '   ' })
  expect(sidebarLoads(fetch)).toBe(1)
})

test('049 FE9: workspace Rename replaces the select; Enter sends PATCH /api/workspaces/2, and the reload shows the new name', async () => {
  const { fetch, responses } = await open('/', body(), SIDEBAR, { 'PATCH /api/workspaces/2': [200, { id: 2, name: 'home' }] })
  choose('workspace personal', 'Rename')
  const input = renamed('Rename workspace personal')
  expect(sidebar().queryByRole('combobox')).toBeNull()
  expect(input.value).toBe('personal')
  expect(document.activeElement).toBe(input)
  expect([input.selectionStart, input.selectionEnd]).toEqual([0, 'personal'.length])
  fireEvent.change(input, { target: { value: 'home' } })
  responses[`GET ${SIDEBAR}`] = body(null, [{ ...PERSONAL, name: 'home' }, WORK])
  fireEvent.submit(input.closest('form'))
  await waitFor(() => expect(shown(sidebar().getByRole('combobox', { name: 'Workspace' }))).toBe('home'))
  expect(JSON.parse(sent(fetch, 'PATCH', '/api/workspaces/2'))).toEqual({ name: 'home' })
  expect(sidebarLoads(fetch)).toBe(2)
  expect(document.activeElement).toBe(actionsOf('workspace home'))
})

test('049 FE9: a 409 on a workspace rename shows beside the input, which stays', async () => {
  await open('/', body(), SIDEBAR, { 'PATCH /api/workspaces/2': [409, { detail: 'workspace work already exists' }] })
  choose('workspace personal', 'Rename')
  const input = renamed('Rename workspace personal')
  fireEvent.change(input, { target: { value: 'work' } })
  fireEvent.submit(input.closest('form'))
  const alert = await sidebar().findByRole('alert')
  expect(alert.textContent).toBe('workspace work already exists')
  expect(alert.closest('form')).toBe(input.closest('form'))
  expect(renamed('Rename workspace personal').value).toBe('work')
})

test('049 FE10: Move to workspace → work sends PATCH {workspace_id: 5}; on 200 the sidebar reloads and focus is on the select', async () => {
  const { fetch, responses } = await open('/', body(), SIDEBAR, {
    'PATCH /api/projects/3': [200, { id: 3, workspace_id: 5, name: 'api-server', test_cmd: null }],
  })
  responses[`GET ${SIDEBAR}`] = body(null, [
    { ...PERSONAL, projects: [project(7, 'web')] },
    { ...WORK, projects: [project(3, 'api-server'), project(4, 'billing')] },
  ])
  choose('api-server', 'work')
  await waitFor(() => expect(projectButton('api-server')).toBeNull())
  expect(JSON.parse(sent(fetch, 'PATCH', '/api/projects/3'))).toEqual({ workspace_id: 5 })
  expect(sidebarLoads(fetch)).toBe(2)
  const select = sidebar().getByRole('combobox', { name: 'Workspace' })
  expect(document.activeElement).toBe(select)
  expect(shown(select)).toBe('personal')
})

test('049 FE10: a refused move shows its detail in the sidebar', async () => {
  const { fetch } = await open('/', body(), SIDEBAR, { 'PATCH /api/projects/3': [404, { detail: 'Not Found' }] })
  choose('api-server', 'work')
  const alert = await sidebar().findByRole('alert')
  expect(alert.textContent).toBe('Not Found')
  expect(projectButton('api-server')).toBeTruthy()
  expect(sidebarLoads(fetch)).toBe(1)
})

test('049 FE11: the project Delete opens a modal dialog through showModal: Delete project api-server?, the Q12 text, Cancel, a danger Delete', async () => {
  let shown
  const showModal = vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function showModal() {
    shown = this.textContent
    this.open = true
  })
  await open('/')
  expect(screen.queryByRole('dialog')).toBeNull()
  choose('api-server', 'Delete')
  expect(showModal).toHaveBeenCalledOnce()
  expect(shown).toContain('Delete project api-server?') // its body rendered first, so showModal focuses Cancel
  const dialog = screen.getByRole('dialog', { name: 'Delete project api-server?' })
  expect(dialog.tagName).toBe('DIALOG')
  expect(document.getElementById(dialog.getAttribute('aria-describedby')).textContent).toBe(PROJECT_TEXT)
  expect(within(dialog).getAllByRole('button').map((b) => b.textContent)).toEqual(['Cancel', 'Delete'])
  const remove = within(dialog).getByRole('button', { name: 'Delete' })
  expect(remove.className).toMatch(/(^|\s)bg-danger(\s|$)/)
  expect(remove.className).toMatch(/(^|\s)text-surface(\s|$)/)
})

test("049 FE12: the dialog's Delete sends DELETE /api/projects/3; on 204 it closes and the app opens /workspaces/2", async () => {
  const { fetch, router } = await open('/', body(), SIDEBAR, { 'DELETE /api/projects/3': [204] })
  choose('api-server', 'Delete')
  const dialog = screen.getByRole('dialog', { name: 'Delete project api-server?' })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
  await waitFor(() => expect(router.state.location.pathname).toBe('/workspaces/2'))
  expect(sent(fetch, 'DELETE', '/api/projects/3')).toBeUndefined()
  expect(dialog.open).toBe(false)
  expect(screen.queryByRole('dialog')).toBeNull()
  await waitFor(() => expect(sidebarLoads(fetch)).toBe(2)) // the navigation reloads the sidebar
})

test('049 FE12 (Q13): deleting from /workspaces/2 itself reloads the sidebar without a navigation', async () => {
  const { fetch, responses, router } = await open('/workspaces/2', body(), SIDEBAR, { 'DELETE /api/projects/3': [204] })
  responses[`GET ${SIDEBAR}`] = body(null, [{ ...PERSONAL, projects: [project(7, 'web')] }, WORK])
  choose('api-server', 'Delete')
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }))
  await waitFor(() => expect(projectButton('api-server')).toBeNull())
  expect(sidebarLoads(fetch)).toBe(2)
  expect(router.state.location.pathname).toBe('/workspaces/2')
})

test('049 FE13: Cancel, or Esc, closes the dialog with no request, and focus goes back to the ⋯', async () => {
  const { fetch } = await open('/')
  choose('api-server', 'Delete')
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(actionsOf('api-server'))
  choose('api-server', 'Delete')
  const dialog = screen.getByRole('dialog', { name: 'Delete project api-server?' })
  act(() => dialog.close()) // what Esc does after its cancel event
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(actionsOf('api-server'))
  expect(fetch.mock.calls.filter(([, init]) => init?.method && init.method !== 'GET')).toEqual([])
})

test("049 FE13: in the drawer, closing the delete dialog leaves the drawer open with its sidebar", async () => {
  await open('/')
  fireEvent.click(screen.getByRole('button', { name: 'Menu' }))
  const drawer = screen.getByRole('dialog', { name: 'Menu' })
  const inDrawer = within(within(drawer).getByRole('navigation', { name: 'Sidebar' }))
  const actions = await inDrawer.findByRole('button', { name: 'Actions for api-server' })
  fireEvent.click(within(menuOf(actions)).getByRole('button', { name: 'Delete', hidden: true }))
  fireEvent.click(within(screen.getByRole('dialog', { name: 'Delete project api-server?' })).getByRole('button', { name: 'Cancel' }))
  expect(drawer.open).toBe(true)
  expect(inDrawer.getByRole('button', { name: 'Actions for api-server' })).toBe(actions)
  expect(document.activeElement).toBe(actions)
})

test('049 FE14: a refused delete shows its detail inside the dialog, which stays open', async () => {
  const { fetch, router } = await open('/', body(), SIDEBAR, { 'DELETE /api/projects/3': [409, { detail: 'run #41 active' }] })
  choose('api-server', 'Delete')
  const dialog = screen.getByRole('dialog', { name: 'Delete project api-server?' })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
  const alert = await within(dialog).findByRole('alert')
  expect(alert.textContent).toBe('run #41 active')
  expect(dialog.open).toBe(true)
  expect(sent(fetch, 'DELETE', '/api/projects/3')).toBeUndefined()
  expect(router.state.location.pathname).toBe('/')
  expect(sidebarLoads(fetch)).toBe(1)
})

test('049 FE15: the workspace Delete asks Delete workspace personal?; 204 opens /, and a 409 shows inside the dialog', async () => {
  for (const [reply, refused] of [[[204], false], [[409, { detail: 'workspace personal still holds 2 projects; move or delete them first' }], true]]) {
    const { fetch, router, unmount } = await open('/workspaces/2', body(), SIDEBAR, { 'DELETE /api/workspaces/2': reply })
    choose('workspace personal', 'Delete')
    const dialog = screen.getByRole('dialog', { name: 'Delete workspace personal?' })
    expect(document.getElementById(dialog.getAttribute('aria-describedby')).textContent).toBe(WORKSPACE_TEXT)
    expect(within(dialog).getAllByRole('button').map((b) => b.textContent)).toEqual(['Cancel', 'Delete'])
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    if (refused) {
      const alert = await within(dialog).findByRole('alert')
      expect(alert.textContent).toBe('workspace personal still holds 2 projects; move or delete them first')
      expect(dialog.open).toBe(true)
      expect(router.state.location.pathname).toBe('/workspaces/2')
    } else {
      await waitFor(() => expect(router.state.location.pathname).toBe('/'))
      expect(dialog.open).toBe(false)
    }
    expect(sent(fetch, 'DELETE', '/api/workspaces/2')).toBeUndefined()
    unmount()
  }
})

// --- 053: Agents -----------------------------------------------------------------------

test('053 FE9: Agents links to /agents, after Dashboard and before fctl reference, and is the current page on /agents', async () => {
  await open('/agents', body(), SIDEBAR, { 'GET /api/pages/agents': [200, { running: [], recent: [] }] })
  const link = (name) => sidebar().getByRole('link', { name })
  const agents = link('Agents')
  expect(agents.getAttribute('href')).toBe('/agents')
  expect(link('Dashboard').compareDocumentPosition(agents) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(agents.compareDocumentPosition(link('fctl reference')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  // 095 AC24: Usage now sits between Dashboard and Agents
  expect(agents.closest('li').previousElementSibling).toBe(link('Usage').closest('li'))
  expect(link('Usage').closest('li').previousElementSibling).toBe(link('Dashboard').closest('li'))
  expect(agents.closest('li').nextElementSibling).toBe(link('fctl reference').closest('li'))
  expect(agents.getAttribute('aria-current')).toBe('page')
  expect(agents.className).toMatch(accent)
  expect(link('Dashboard').hasAttribute('aria-current')).toBe(false)
})

test('053 FE10 (Q8): the Agents pill sums running over every workspace, the unselected one included; none at 0', async () => {
  const running = (ws, counts) => ({ ...ws, projects: ws.projects.map((p, i) => ({ ...p, running: counts[i] ?? 0 })) })
  const one = await open('/', body(null, [PERSONAL, running(WORK, [1])]))
  expect(shown(one.select)).toBe('personal') // work, holding the run, isn't selected
  const agents = sidebar().getByRole('link', { name: 'Agents 1' })
  const pill = within(agents).getByText('1')
  expect(pill.className.split(/\s+/)).toEqual(expect.arrayContaining(['rounded-full', 'bg-accent', 'text-surface']))
  one.unmount()

  const two = await open('/', body(null, [running(PERSONAL, [1, 0]), running(WORK, [1])]))
  expect(within(sidebar().getByRole('link', { name: 'Agents 2' })).getByText('2')).toBeTruthy()
  two.unmount()

  await open('/')
  const zero = sidebar().getByRole('link', { name: 'Agents' })
  expect(zero.textContent).toBe('Agents')
  expect(zero.querySelector('span')).toBeNull()
})

// --- 095: Claude usage ------------------------------------------------------------------

const NOW = new Date(2026, 10, 13, 10, 0) // local time, so `reset at HH:MM` reads the same in any TZ
const at = (minutes) => Math.floor(NOW.getTime() / 1000) + minutes * 60
const win = (utilization, state = 'allowed', minutes = 130) => ({ utilization, resets_at: at(minutes), state, reset: false })
const acct = (id, label, active, five = win(0.34), seven = win(0.12, 'allowed', 5 * 1440 + 60)) => ({
  id, label, active, recorded_at: '2026-11-13T09:00:00Z', run_id: 41, overage: false, five_hour: five, seven_day: seven,
})
const noData = (id, label, active = false) => ({ ...acct(id, label, active, null, null), recorded_at: null, run_id: null, overage: null })
const withUsage = (usage) => [200, { workspaces: [PERSONAL, WORK], current: null, usage }]
const usageLink = () => sidebar().queryByRole('link', { name: 'Claude usage' })
/** The block's text lines, as rendered. */
const lines = () => [...usageLink().querySelectorAll('p')].map((p) => p.textContent)

afterEach(() => vi.useRealTimers())

test('095 AC20: one link named Claude usage to /usage; the active account expanded with 5h and 7d rows and their text', async () => {
  vi.setSystemTime(NOW)
  await open('/', withUsage([acct(1, 'me@x.io', true)]))
  const link = usageLink()
  expect(link.getAttribute('href')).toBe('/usage')
  expect(lines()).toEqual(['me@x.ioactive', 'resets in 2h 10m · allowed', 'resets in 5d 1h · allowed'])
  expect(link.textContent).toContain('5h34%')
  expect(link.textContent).toContain('7d12%')
  const bars = [...link.querySelectorAll('[data-fill]')]
  expect(bars.map((b) => b.style.width)).toEqual(['34%', '12%'])
  for (const bar of bars) expect(bar.parentElement.getAttribute('aria-hidden')).toBe('true')
  // the details reach assistive tech as the link's description
  expect(document.getElementById(link.getAttribute('aria-describedby')).textContent).toContain('resets in 2h 10m')
})

test('095 AC20: a passed window reads reset at HH:MM, at 0%', async () => {
  vi.setSystemTime(NOW)
  const reset = { utilization: 0, resets_at: at(-55), state: 'allowed', reset: true }
  await open('/', withUsage([acct(1, 'me@x.io', true, reset)]))
  expect(lines()[1]).toBe('reset at 09:05 · allowed')
  expect(usageLink().querySelector('[data-fill]').style.width).toBe('0%')
})

test('095 AC21: allowed fills accent, near limit warning, limited danger, on a bg-line track, each with its word', async () => {
  vi.setSystemTime(NOW)
  const view = await open('/', withUsage([acct(1, 'me@x.io', true, win(0.85, 'near_limit'), win(1, 'limited'))]))
  const fills = [...usageLink().querySelectorAll('[data-fill]')]
  expect(fills[0].className).toMatch(/(^|\s)bg-warning(\s|$)/)
  expect(fills[1].className).toMatch(/(^|\s)bg-danger(\s|$)/)
  for (const fill of fills) expect(fill.parentElement.className).toMatch(/(^|\s)bg-line(\s|$)/)
  expect(lines().slice(1)).toEqual(['resets in 2h 10m · near limit', 'resets in 2h 10m · limited'])
  view.unmount()

  await open('/', withUsage([acct(1, 'me@x.io', true)]))
  expect(usageLink().querySelector('[data-fill]').className).toMatch(/(^|\s)bg-accent(\s|$)/)
})

test('095 AC22: with 2–3 accounts each other one is a line with its worst window; with 4+ they collapse to one', async () => {
  vi.setSystemTime(NOW)
  const two = acct(2, 'two@x.io', false, win(0.3), win(0.64))
  const three = acct(3, 'three@x.io', false, win(0.9, 'near_limit'), win(0.2))
  const view = await open('/', withUsage([acct(1, 'me@x.io', true), two, three]))
  expect(lines().slice(3)).toEqual(['two@x.io · 7d 64% · allowed', 'three@x.io · 5h 90% · near limit'])
  view.unmount()

  await open('/', withUsage([two, acct(1, 'me@x.io', true), three, acct(4, 'four', false, win(0.1), win(0.95, 'limited'))]))
  expect(lines()[0]).toBe('me@x.ioactive')
  expect(lines().slice(3)).toEqual(['3 other accounts · worst 7d 95%'])
})

test('095 AC23: no snapshot shows the no-data text, expanded or as a line; no accounts, no block', async () => {
  const view = await open('/', withUsage([noData(1, 'me@x.io', true), noData(2, 'two')]))
  expect(lines()).toEqual(['me@x.ioactive', 'no usage data yet, run a task', 'two · no usage data yet, run a task'])
  expect(usageLink().querySelector('[data-fill]')).toBeNull()
  view.unmount()

  const empty = await open('/', withUsage([]))
  expect(usageLink()).toBeNull()
  empty.unmount()

  await open('/') // a sidebar body with no usage field at all
  expect(usageLink()).toBeNull()
})

test('095 AC24: the bottom nav is Dashboard, Usage, Agents, fctl reference', async () => {
  await open('/', withUsage([acct(1, 'me@x.io', true)]))
  const nav = [...sidebar().getByRole('link', { name: 'Dashboard' }).closest('ul').querySelectorAll('a')]
  expect(nav.map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
    ['Dashboard', '/'],
    ['Usage', '/usage'],
    ['Agents', '/agents'],
    ['fctl reference', '/docs/fctl'],
  ])
})
