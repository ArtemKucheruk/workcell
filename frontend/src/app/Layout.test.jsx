import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { fetched, mockFetch, renderAt } from '../test/render.jsx'

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

/** 041's GET /api/pages/sidebar, one workspace with one project. */
const SIDEBAR = {
  workspaces: [{ id: 2, name: 'personal', projects: [{ id: 3, name: 'api', review: 0, running: 0, escalated: 0 }] }],
  current: null,
}
const nav = () => screen.getByRole('navigation', { name: 'Sidebar' })
const sidebar = () => within(nav())
const sidebarCalls = (fetch) => fetched(fetch).filter((url) => url.startsWith('/api/pages/sidebar'))
const settle = () => act(() => new Promise((resolve) => setTimeout(resolve, 20)))

const EMPTY_DASHBOARD = {
  tiles: { backlog: 'Backlog' }, counts: { backlog: 0 }, show: '', listed: null,
  waiting: [], escalated: [], open_tasks: [], done: [],
}
const dashboard = (auth) => ({
  'GET /api/auth': auth,
  'GET /api/pages/dashboard': [200, EMPTY_DASHBOARD],
})

test('FE2 (AC14): a pro subscription shows Claude: Pro ✓ in the sidebar', async () => {
  mockFetch(dashboard([200, { auth_method: 'claude.ai', plan: 'pro', runs_enabled: true }]))
  renderAt('/')
  expect(await sidebar().findByText('Claude: Pro ✓')).toBeTruthy()
})

test('FE2 (AC14): plan null with runs enabled reads like the Jinja badge', async () => {
  mockFetch(dashboard([200, { auth_method: 'claude.ai', plan: null, runs_enabled: true }]))
  renderAt('/')
  expect(await sidebar().findByText('Claude: subscription ✓')).toBeTruthy()
})

test('FE2 (AC15): runs disabled shows the red Not signed in badge', async () => {
  mockFetch(dashboard([200, { auth_method: null, plan: null, runs_enabled: false }]))
  renderAt('/')
  const badge = await sidebar().findByText('Not signed in — runs disabled')
  expect(badge.className).toMatch(/(^|\s)text-danger(\s|$)/)
})

test('FE2 (AC16): a failed /api/auth shows no badge and the page still renders', async () => {
  for (const auth of [[500, { detail: 'boom' }], new TypeError('Failed to fetch')]) {
    const fetch = mockFetch(dashboard(auth))
    const { unmount } = renderAt('/')
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeTruthy()
    await waitFor(() => expect(fetched(fetch)).toContain('/api/auth'))
    expect(screen.queryByText(/Claude:|runs disabled/)).toBeNull()
    expect(sidebar().getByRole('link', { name: 'Dashboard' })).toBeTruthy()
    unmount()
  }
})

test('FE1 (AC17, 029 AC21): the sidebar holds the app name, the workspace area, Dashboard, fctl reference, then the badge', async () => {
  mockFetch({
    ...dashboard([200, PRO]),
    'GET /api/pages/workspaces/2': [200, { workspace: { id: 2, name: 'work' }, projects: [] }],
    'GET /api/docs/fctl': [200, { body_html: '', headings: [] }],
    'GET /api/pages/sidebar': [200, SIDEBAR],
  })
  for (const path of ['/', '/workspaces/2', '/docs/fctl', '/nope']) {
    const { unmount } = renderAt(path)
    const badge = await sidebar().findByRole('link', { name: 'Claude: Pro ✓' })
    const workspace = await sidebar().findByRole('combobox', { name: 'Workspace' })
    const link = (name) => sidebar().getByRole('link', { name })
    expect(link('Claude Factories').getAttribute('href')).toBe('/')
    expect(link('Dashboard').getAttribute('href')).toBe('/')
    expect(link('fctl reference').getAttribute('href')).toBe('/docs/fctl')
    const order = [link('Claude Factories'), workspace, link('Dashboard'), link('fctl reference'), badge]
    for (let i = 1; i < order.length; i++) {
      expect(order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    }
    // the old top header is gone: these links are only in the sidebar
    for (const name of ['Claude Factories', 'Dashboard', 'fctl reference']) {
      expect(screen.getAllByRole('link', { name })).toEqual([link(name)])
    }
    expect(screen.queryByRole('banner')).toBeNull()
    unmount()
  }
})

test('AC18: an unknown route shows Page not found with a link home, and loads no page view-model but the sidebar', async () => {
  const fetch = mockFetch({ 'GET /api/auth': [500, {}] })
  renderAt('/nope')
  expect(screen.getByRole('heading', { name: 'Page not found' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Go to the dashboard' }).getAttribute('href')).toBe('/')
  await waitFor(() => expect(fetched(fetch)).toContain('/api/auth'))
  expect(fetched(fetch).filter((url) => url.startsWith('/api/pages/') && url !== '/api/pages/sidebar')).toEqual([])
})

test('AC19: the page declares light and dark, and dark: follows the system', () => {
  // jsdom's URL isn't Node's, so fs gets a path
  const read = (rel) => fs.readFileSync(fileURLToPath(new URL(rel, import.meta.url).href), 'utf8')
  const html = read('../../index.html')
  const css = read('../index.css')
  expect(html).toContain('<meta name="color-scheme" content="light dark">')
  expect(css).toContain('@import "tailwindcss";')
  expect(css).not.toMatch(/@(custom-)?variant\s+dark/)
})

const PRO = { auth_method: 'claude.ai', plan: 'pro', runs_enabled: true, email: null }
const OFF = { auth_method: null, plan: null, runs_enabled: false, email: null }

test('FE2 (039 AC17): the badge links to /settings, and the runs-disabled one stays red', async () => {
  mockFetch(dashboard([200, PRO]))
  const { unmount } = renderAt('/')
  const pro = await sidebar().findByRole('link', { name: 'Claude: Pro ✓' })
  expect(pro.getAttribute('href')).toBe('/settings')
  unmount()
  mockFetch(dashboard([200, OFF]))
  renderAt('/')
  const off = await sidebar().findByRole('link', { name: 'Not signed in — runs disabled' })
  expect(off.getAttribute('href')).toBe('/settings')
  expect(off.className).toMatch(/(^|\s)text-danger(\s|$)/)
})

test('FE2 (039 AC18): the sidebar re-fetches /api/auth every 3 s and the badge follows it', async () => {
  vi.useFakeTimers()
  try {
    const responses = dashboard([200, OFF])
    const fetch = mockFetch(responses)
    const advance = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))
    const auths = () => fetched(fetch).filter((url) => url === '/api/auth').length
    renderAt('/')
    await advance(0)
    const side = sidebar()
    expect(side.getByText('Not signed in — runs disabled')).toBeTruthy()
    responses['GET /api/auth'] = [200, PRO]
    await advance(2999)
    expect(auths()).toBe(1)
    await advance(1)
    expect(auths()).toBe(2)
    expect(side.getByText('Claude: Pro ✓')).toBeTruthy()
    expect(side.queryByText('Not signed in — runs disabled')).toBeNull()
  } finally {
    vi.useRealTimers()
  }
})

test('FE3: each route fetches the sidebar once, with ?task= or ?transcript= only from an all-digit id', async () => {
  for (const [path, url] of [
    ['/tasks/12', '/api/pages/sidebar?task=12'],
    ['/tasks/12/review', '/api/pages/sidebar?task=12'],
    ['/transcripts/5', '/api/pages/sidebar?transcript=5'],
    ['/', '/api/pages/sidebar'],
    ['/projects/3', '/api/pages/sidebar'],
    ['/tasks/abc', '/api/pages/sidebar'],
  ]) {
    const fetch = mockFetch({ [`GET ${url}`]: [200, SIDEBAR] })
    const { unmount } = renderAt(path)
    // anything but `url` is a 404, which shows no combobox
    expect(await sidebar().findByRole('combobox', { name: 'Workspace' })).toBeTruthy()
    await settle()
    expect(sidebarCalls(fetch)).toEqual([url])
    unmount()
  }
})

test('FE4: a click on a sidebar link, or a ?path= change on the code page, sends one more sidebar request', async () => {
  const fetch = mockFetch({
    'GET /api/pages/sidebar': [200, SIDEBAR],
    'GET /api/docs/fctl': [200, { body_html: '', headings: [] }],
  })
  const { router, unmount } = renderAt('/')
  await sidebar().findByRole('combobox', { name: 'Workspace' })
  expect(sidebarCalls(fetch)).toHaveLength(1)
  fireEvent.click(sidebar().getByRole('link', { name: 'fctl reference' }))
  await waitFor(() => expect(router.state.location.pathname).toBe('/docs/fctl'))
  await settle()
  expect(sidebarCalls(fetch)).toEqual(['/api/pages/sidebar', '/api/pages/sidebar'])
  unmount()

  const code = mockFetch({ 'GET /api/pages/sidebar': [200, SIDEBAR] })
  const view = renderAt('/projects/3/code')
  await sidebar().findByRole('combobox', { name: 'Workspace' })
  await act(() => view.router.navigate('/projects/3/code?path=src%2Fa.py'))
  await settle()
  expect(sidebarCalls(code)).toEqual(['/api/pages/sidebar', '/api/pages/sidebar'])
})

test('FE4: with no navigation, 10 s sends no sidebar request: it is not polled', async () => {
  vi.useFakeTimers()
  const fetch = mockFetch({ ...dashboard([200, PRO]), 'GET /api/pages/sidebar': [200, SIDEBAR] })
  renderAt('/')
  await act(() => vi.advanceTimersByTimeAsync(0))
  expect(sidebarCalls(fetch)).toHaveLength(1)
  await act(() => vi.advanceTimersByTimeAsync(10_000))
  expect(sidebarCalls(fetch)).toHaveLength(1)
  expect(fetched(fetch).filter((url) => url === '/api/auth').length).toBeGreaterThan(1) // the clock did run
})

/** Renders `path` and opens the drawer; returns the dialog, the Menu button, and the router. */
async function openDrawer(path = '/nope') {
  mockFetch({
    'GET /api/pages/sidebar': [200, SIDEBAR],
    'GET /api/docs/fctl': [200, { body_html: '', headings: [] }],
  })
  const { router } = renderAt(path)
  await sidebar().findByRole('combobox', { name: 'Workspace' })
  const menu = screen.getByRole('button', { name: 'Menu' })
  fireEvent.click(menu)
  const dialog = screen.getByRole('dialog', { name: 'Menu' })
  await within(dialog).findByRole('combobox', { name: 'Workspace' })
  return { dialog, menu, router }
}

test('FE17: Menu opens a <dialog> drawer through showModal, holding the sidebar; the column is hidden below md', async () => {
  const showModal = vi.spyOn(HTMLDialogElement.prototype, 'showModal')
  mockFetch({ 'GET /api/pages/sidebar': [200, SIDEBAR] })
  renderAt('/nope')
  const menu = screen.getByRole('button', { name: 'Menu' })
  expect(menu.getAttribute('aria-haspopup')).toBe('dialog')
  expect(menu.className).toMatch(/(^|\s)md:hidden(\s|$)/)
  const column = nav().parentElement
  expect(column.className).toMatch(/(^|\s)hidden(\s|$)/)
  expect(column.className).toMatch(/(^|\s)md:(block|flex|grid)(\s|$)/)
  expect(screen.queryByRole('dialog')).toBeNull()
  fireEvent.click(menu)
  expect(showModal).toHaveBeenCalledOnce()
  const dialog = screen.getByRole('dialog', { name: 'Menu' })
  expect(dialog.tagName).toBe('DIALOG')
  const drawer = within(within(dialog).getByRole('navigation', { name: 'Sidebar' }))
  expect(await drawer.findByRole('combobox', { name: 'Workspace' })).toBeTruthy()
  expect(drawer.getByRole('link', { name: 'Claude Factories' }).getAttribute('href')).toBe('/')
  expect(drawer.getByRole('link', { name: 'fctl reference' }).getAttribute('href')).toBe('/docs/fctl')
})

test('FE18: the close event that Esc raises closes the drawer and leaves focus on Menu', async () => {
  const { dialog, menu } = await openDrawer()
  within(dialog).getByRole('link', { name: 'Dashboard' }).focus()
  act(() => dialog.close())
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(menu)
  expect(screen.getAllByRole('navigation', { name: 'Sidebar' })).toHaveLength(1)
})

test("FE18: a click on the backdrop closes the drawer; a click inside its content doesn't", async () => {
  const { dialog, menu } = await openDrawer()
  fireEvent.click(within(dialog).getByRole('navigation', { name: 'Sidebar' }))
  fireEvent.click(within(dialog).getByRole('combobox', { name: 'Workspace' }))
  expect(dialog.open).toBe(true)
  fireEvent.click(dialog)
  expect(dialog.open).toBe(false)
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(menu)
})

test('FE18: a link in the drawer navigates and closes it', async () => {
  const { dialog, router } = await openDrawer()
  fireEvent.click(within(dialog).getByRole('link', { name: 'fctl reference' }))
  await waitFor(() => expect(router.state.location.pathname).toBe('/docs/fctl'))
  expect(dialog.open).toBe(false)
  expect(screen.queryByRole('dialog')).toBeNull()
})

test('FE19: main drops max-w-6xl on the board, code, and review pages, and keeps mx-auto max-w-6xl elsewhere', () => {
  mockFetch({})
  const main = (path) => {
    const { unmount } = renderAt(path)
    const classes = screen.getByRole('main').className.split(/\s+/)
    unmount()
    return classes
  }
  for (const path of ['/projects/3', '/projects/3/code', '/tasks/12/review']) {
    expect(main(path)).not.toContain('max-w-6xl')
  }
  for (const path of ['/', '/tasks/12', '/settings']) {
    expect(main(path)).toEqual(expect.arrayContaining(['mx-auto', 'max-w-6xl']))
  }
})

test('042 FE36: on Reviews, Context, and Settings the sidebar selects the project, opens it, and marks only its page', async () => {
  const sidebarBody = {
    workspaces: [
      { id: 2, name: 'personal', projects: [{ id: 3, name: 'api', review: 0, running: 0, escalated: 0 }] },
      { id: 5, name: 'work', projects: [{ id: 4, name: 'billing', review: 0, running: 0, escalated: 0 }] },
    ],
    current: null,
  }
  const accent = /(^|\s)text-accent(\s|$)/
  for (const [path, current] of [
    ['/projects/3/reviews?tab=closed', 'Reviews'],
    ['/projects/3/context', 'Context'],
    ['/projects/3/settings', 'Settings'],
    ['/projects/3/scheduler', 'Scheduler'], // 104 AC23
  ]) {
    localStorage.setItem('sidebar.workspace', '5')
    mockFetch({ 'GET /api/pages/sidebar': [200, sidebarBody] })
    const { unmount } = renderAt(path)
    const select = await sidebar().findByRole('combobox', { name: 'Workspace' })
    await waitFor(() => expect(select.selectedOptions[0].textContent).toBe('personal'))
    const button = sidebar().getByRole('button', { name: 'api' })
    expect(button.getAttribute('aria-expanded')).toBe('true')
    const links = within(document.getElementById(button.getAttribute('aria-controls'))).getAllByRole('link')
    expect(links.map((a) => a.textContent)).toEqual(['Board', 'Code', 'Reviews', 'Context', 'Workflows', 'Scheduler', 'Settings'])
    for (const link of links) {
      const on = link.textContent === current
      expect([link.textContent, link.getAttribute('aria-current'), accent.test(link.className)]).toEqual([
        link.textContent, on ? 'page' : null, on,
      ])
    }
    unmount()
  }
})

test('051 FE7: on the Factories list and a designer the sidebar selects project 3\'s workspace over storage and opens project 3', async () => {
  const sidebarBody = {
    workspaces: [
      { id: 2, name: 'personal', projects: [{ id: 3, name: 'api', review: 0, running: 0, escalated: 0 }] },
      { id: 5, name: 'work', projects: [{ id: 4, name: 'billing', review: 0, running: 0, escalated: 0 }] },
    ],
    current: null,
  }
  for (const path of ['/projects/3/factories', '/projects/3/factories/7']) {
    localStorage.setItem('sidebar.workspace', '5')
    const fetch = mockFetch({ 'GET /api/pages/sidebar': [200, sidebarBody] })
    const { unmount } = renderAt(path)
    const select = await sidebar().findByRole('combobox', { name: 'Workspace' })
    await waitFor(() => expect(select.selectedOptions[0].textContent).toBe('personal'))
    expect(sidebar().getByRole('button', { name: 'api' }).getAttribute('aria-expanded')).toBe('true')
    expect(sidebarCalls(fetch)).toEqual(['/api/pages/sidebar']) // no ?task= or ?transcript=
    unmount()
  }
})

test('042 FE37: Reviews, Context, and Settings keep main at mx-auto max-w-6xl', () => {
  mockFetch({})
  for (const path of ['/projects/3/reviews', '/projects/3/context', '/projects/3/settings', '/projects/3/scheduler']) {
    const { unmount } = renderAt(path)
    expect(screen.getByRole('main').className.split(/\s+/)).toEqual(expect.arrayContaining(['mx-auto', 'max-w-6xl']))
    unmount()
  }
})

test('050 FE18: autoInit runs once the route\'s page has mounted, and again on each navigation while its view-model is pending', async () => {
  const at = [] // what main showed at each call
  const autoInit = vi.fn(() => at.push(document.querySelector('main').innerHTML))
  vi.stubGlobal('HSStaticMethods', { autoInit })
  vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {}))) // nothing ever loads, so usePoll never calls it
  const { router } = renderAt('/')
  await screen.findByRole('status') // the dashboard's skeleton
  expect(autoInit).toHaveBeenCalledTimes(1)
  expect(at[0]).toBe(document.querySelector('main').innerHTML)
  await act(() => router.navigate('/projects/3'))
  expect(autoInit).toHaveBeenCalledTimes(2)
  expect(at[1]).toBe(document.querySelector('main').innerHTML)
  expect(at[1]).not.toBe(at[0]) // the board's skeleton, not the dashboard's
  await act(() => router.navigate('/projects/3?x=1'))
  expect(autoInit).toHaveBeenCalledTimes(3)
})

test('049 FE24: on /workspaces/5/settings the sidebar selects workspace 5 over storage, as on /workspaces/5, and main keeps its max width', async () => {
  const two = {
    workspaces: [SIDEBAR.workspaces[0], { id: 5, name: 'work', projects: [] }],
    current: null,
  }
  for (const path of ['/workspaces/5', '/workspaces/5/settings']) {
    localStorage.setItem('sidebar.workspace', '2')
    mockFetch({ 'GET /api/pages/sidebar': [200, two] })
    const { unmount } = renderAt(path)
    const select = await sidebar().findByRole('combobox', { name: 'Workspace' })
    await waitFor(() => expect(select.selectedOptions[0].textContent).toBe('work'))
    expect(localStorage.getItem('sidebar.workspace')).toBe('5')
    expect(screen.getByRole('main').className.split(/\s+/)).toEqual(expect.arrayContaining(['mx-auto', 'max-w-6xl']))
    unmount()
  }
})
