import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { expect, test } from 'vitest'
import { mockFetch, renderAt } from '../../test/render.jsx'

const PRO = { auth_method: 'claude.ai', plan: 'pro', runs_enabled: true, email: 'artem@example.com' }
const OFF = { auth_method: null, plan: null, runs_enabled: false, email: null }
const SIGN_IN = 'https://claude.ai/oauth/authorize?code=true&state=abc'
const LOGIN = 'POST /api/auth/login'
const CODE = 'POST /api/auth/login/code'

/** Renders /settings with /api/auth answering `auth`, and waits for the Claude login section. */
async function open(auth, responses = {}) {
  const fetch = mockFetch({ 'GET /api/auth': [200, auth], [LOGIN]: [200, { url: SIGN_IN }], ...responses })
  const view = renderAt('/settings')
  const section = await screen.findByRole('region', { name: 'Claude login' })
  return { fetch, section, ...view }
}
/** The fetch calls to "METHOD url", as [url, init]. */
const calls = (fetch, key) => fetch.mock.calls.filter(([url, init = {}]) => `${init.method ?? 'GET'} ${url}` === key)
/** The <dd> beside the <dt> named `name`. */
const row = (name) => screen.getByText(name, { selector: 'dt' }).nextElementSibling.textContent
const codeInput = () => screen.getByRole('textbox', { name: 'Code' })
const submitButton = () => screen.getByRole('button', { name: 'Submit code' })

async function startLogin(name) {
  fireEvent.click(screen.getByRole('button', { name }))
  await screen.findByRole('link', { name: 'Open the Claude sign-in page' })
}

test('AC19: a claude.ai pro login shows its method, plan, account, and Log in again, with no textbox', async () => {
  const { section } = await open(PRO)
  expect(screen.getByRole('heading', { level: 1, name: 'Settings' })).toBeTruthy()
  expect(document.title).toBe('Settings · Claude Factories')
  expect(row('Auth method')).toBe('claude.ai')
  expect(row('Plan')).toBe('Pro')
  expect(row('Account')).toBe('artem@example.com')
  expect(within(section).getByText('Runs enabled')).toBeTruthy()
  expect(within(section).getByRole('button', { name: 'Log in again' })).toBeTruthy()
  expect(screen.queryByRole('textbox')).toBeNull()
})

test('AC19: plan null reads subscription and email null reads —', async () => {
  await open({ ...PRO, plan: null, email: null })
  expect(row('Plan')).toBe('subscription')
  expect(row('Account')).toBe('—')
})

test('AC20: runs disabled says so and offers Log in with Claude, with no API key field', async () => {
  const { section } = await open(OFF)
  expect(within(section).getByText('Not signed in with a Claude subscription — runs disabled')).toBeTruthy()
  expect(within(section).getByRole('button', { name: 'Log in with Claude' })).toBeTruthy()
  expect(screen.queryByRole('textbox')).toBeNull()
})

test('AC21: Log in posts once and shows the sign-in link, the Code field, and Start over', async () => {
  for (const [auth, name] of [[OFF, 'Log in with Claude'], [PRO, 'Log in again']]) {
    const { fetch, section, unmount } = await open(auth)
    await startLogin(name)
    const posts = calls(fetch, LOGIN)
    expect(posts).toHaveLength(1)
    expect(posts[0][1].headers['X-Requested-By']).toBe('fctl')
    const link = screen.getByRole('link', { name: 'Open the Claude sign-in page' })
    expect(link.getAttribute('href')).toBe(SIGN_IN)
    expect(link.getAttribute('target')).toBe('_blank')
    expect(link.getAttribute('rel')).toBe('noopener noreferrer')
    expect(submitButton().disabled).toBe(true)
    fireEvent.change(codeInput(), { target: { value: '   ' } })
    expect(submitButton().disabled).toBe(true)
    fireEvent.change(codeInput(), { target: { value: 'good#state' } })
    expect(submitButton().disabled).toBe(false)
    expect(within(section).getByRole('button', { name: 'Start over' })).toBeTruthy()
    expect(within(section).queryByRole('button', { name })).toBeNull()
    unmount()
  }
})

test('AC22: a code is sent trimmed; on 200 the page shows the new login and drops the form', async () => {
  const { fetch } = await open(OFF, { [CODE]: [200, PRO] })
  await startLogin('Log in with Claude')
  fireEvent.change(codeInput(), { target: { value: ' good#state ' } })
  fireEvent.click(submitButton())
  expect((await screen.findByRole('status')).textContent).toBe('Logged in as artem@example.com')
  const sent = calls(fetch, CODE)
  expect(sent).toHaveLength(1)
  expect(JSON.parse(sent[0][1].body)).toEqual({ code: 'good#state' })
  expect(row('Plan')).toBe('Pro')
  expect(screen.getByText('Runs enabled')).toBeTruthy()
  expect(screen.queryByRole('textbox')).toBeNull()
  expect(screen.getByRole('button', { name: 'Log in again' })).toBeTruthy()
})

test('AC22: Enter submits too, and a null email reads Logged in', async () => {
  const { fetch } = await open(OFF, { [CODE]: [200, { ...PRO, email: null }] })
  await startLogin('Log in with Claude')
  fireEvent.change(codeInput(), { target: { value: 'good#state' } })
  fireEvent.submit(codeInput().form) // jsdom has no implicit submission; Enter in a form's field does this
  expect((await screen.findByRole('status')).textContent).toBe('Logged in')
  expect(calls(fetch, CODE)).toHaveLength(1)
})

test('AC23: a refused login start shows its detail in an alert', async () => {
  const detail = 'claude auth login printed no sign-in URL: Error: managed settings forbid this'
  await open(OFF, { [LOGIN]: [500, { detail }] })
  fireEvent.click(screen.getByRole('button', { name: 'Log in with Claude' }))
  expect((await screen.findByRole('alert')).textContent).toBe(detail)
  expect(screen.queryByRole('textbox')).toBeNull()
})

test('AC23: a refused code shows its detail, and the form and typed code stay', async () => {
  for (const [status, detail] of [[409, 'no login in progress'], [422, 'Login failed: Invalid code']]) {
    const { unmount } = await open(OFF, { [CODE]: [status, { detail }] })
    await startLogin('Log in with Claude')
    fireEvent.change(codeInput(), { target: { value: 'good#state' } })
    fireEvent.click(submitButton())
    expect((await screen.findByRole('alert')).textContent).toBe(detail)
    expect(codeInput().value).toBe('good#state')
    await waitFor(() => expect(submitButton().disabled).toBe(false))
    expect(screen.queryByRole('status')).toBeNull()
    unmount()
  }
})

test('AC24: Loading… until /api/auth answers, then its error in an alert', async () => {
  mockFetch({ 'GET /api/auth': [500, { detail: 'boom' }] })
  renderAt('/settings')
  expect(screen.getByText('Loading…')).toBeTruthy()
  expect((await screen.findByRole('alert')).textContent).toBe('boom')
  expect(screen.queryByRole('region', { name: 'Claude login' })).toBeNull()
})
