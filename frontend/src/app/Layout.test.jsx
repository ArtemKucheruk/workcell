import { act, screen, waitFor, within } from '@testing-library/react'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
import { expect, test, vi } from 'vitest'
import { fetched, mockFetch, renderAt } from '../test/render.jsx'

const EMPTY_DASHBOARD = {
  tiles: { backlog: 'Backlog' }, counts: { backlog: 0 }, show: '', listed: null,
  open_tasks: [], done: [], workspaces: [],
}
const dashboard = (auth) => ({
  'GET /api/auth': auth,
  'GET /api/pages/dashboard': [200, EMPTY_DASHBOARD],
})

test('AC14: a pro subscription shows Claude: Pro ✓', async () => {
  mockFetch(dashboard([200, { auth_method: 'claude.ai', plan: 'pro', runs_enabled: true }]))
  renderAt('/')
  expect(await within(screen.getByRole('banner')).findByText('Claude: Pro ✓')).toBeTruthy()
})

test('AC14: plan null with runs enabled reads like the Jinja badge', async () => {
  mockFetch(dashboard([200, { auth_method: 'claude.ai', plan: null, runs_enabled: true }]))
  renderAt('/')
  expect(await screen.findByText('Claude: subscription ✓')).toBeTruthy()
})

test('AC15: runs disabled shows the red API key badge', async () => {
  mockFetch(dashboard([200, { auth_method: null, plan: null, runs_enabled: false }]))
  renderAt('/')
  const badge = await screen.findByText('API key — runs disabled')
  expect(badge.className).toMatch(/(^|\s)text-danger(\s|$)/)
})

test('AC16: a failed /api/auth shows no badge and the page still renders', async () => {
  for (const auth of [[500, { detail: 'boom' }], new TypeError('Failed to fetch')]) {
    const fetch = mockFetch(dashboard(auth))
    const { unmount } = renderAt('/')
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeTruthy()
    await waitFor(() => expect(fetched(fetch)).toContain('/api/auth'))
    expect(screen.queryByText(/Claude:|API key/)).toBeNull()
    unmount()
  }
})

test('AC17: the header links Claude Factories to / on both pages', async () => {
  mockFetch({
    ...dashboard([500, {}]),
    'GET /api/pages/workspaces/2': [200, { workspace: { id: 2, name: 'work' }, projects: [] }],
  })
  for (const path of ['/', '/workspaces/2']) {
    const { unmount } = renderAt(path)
    const link = within(screen.getByRole('banner')).getByRole('link', { name: 'Claude Factories' })
    expect(link.getAttribute('href')).toBe('/')
    unmount()
  }
})

test('029 AC21: every page header links fctl reference to /docs/fctl', async () => {
  mockFetch({
    ...dashboard([500, {}]),
    'GET /api/pages/workspaces/2': [200, { workspace: { id: 2, name: 'work' }, projects: [] }],
    'GET /api/docs/fctl': [200, { body_html: '', headings: [] }],
  })
  for (const path of ['/', '/workspaces/2', '/docs/fctl']) {
    const { unmount } = renderAt(path)
    const link = within(screen.getByRole('banner')).getByRole('link', { name: 'fctl reference' })
    expect(link.getAttribute('href')).toBe('/docs/fctl')
    unmount()
  }
})

test('AC18: an unknown route shows Page not found with a link home, and loads no page view-model', async () => {
  const fetch = mockFetch({ 'GET /api/auth': [500, {}] })
  renderAt('/nope')
  expect(screen.getByRole('heading', { name: 'Page not found' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Go to the dashboard' }).getAttribute('href')).toBe('/')
  await waitFor(() => expect(fetched(fetch)).toContain('/api/auth'))
  expect(fetched(fetch).filter((url) => url.startsWith('/api/pages/'))).toEqual([])
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

test('039 AC17: the badge links to /settings, and the runs-disabled one stays red', async () => {
  mockFetch(dashboard([200, PRO]))
  const { unmount } = renderAt('/')
  const pro = await within(screen.getByRole('banner')).findByRole('link', { name: 'Claude: Pro ✓' })
  expect(pro.getAttribute('href')).toBe('/settings')
  unmount()
  mockFetch(dashboard([200, OFF]))
  renderAt('/')
  const off = await within(screen.getByRole('banner')).findByRole('link', { name: 'API key — runs disabled' })
  expect(off.getAttribute('href')).toBe('/settings')
  expect(off.className).toMatch(/(^|\s)text-danger(\s|$)/)
})

test('039 AC18: the header re-fetches /api/auth every 3 s and the badge follows it', async () => {
  vi.useFakeTimers()
  try {
    const responses = dashboard([200, OFF])
    const fetch = mockFetch(responses)
    const advance = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))
    const auths = () => fetched(fetch).filter((url) => url === '/api/auth').length
    renderAt('/')
    await advance(0)
    const banner = within(screen.getByRole('banner'))
    expect(banner.getByText('API key — runs disabled')).toBeTruthy()
    responses['GET /api/auth'] = [200, PRO]
    await advance(2999)
    expect(auths()).toBe(1)
    await advance(1)
    expect(auths()).toBe(2)
    expect(banner.getByText('Claude: Pro ✓')).toBeTruthy()
    expect(banner.queryByText('API key — runs disabled')).toBeNull()
  } finally {
    vi.useRealTimers()
  }
})
