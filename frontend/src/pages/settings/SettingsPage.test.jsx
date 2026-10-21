import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { cls, expectSkeleton, mockFetch, renderAt } from '../../test/render.jsx'

afterEach(() => vi.restoreAllMocks())

const PRO = { auth_method: 'claude.ai', plan: 'pro', runs_enabled: true, email: 'artem@example.com' }
const OFF = { auth_method: null, plan: null, runs_enabled: false, email: null }
const SIGN_IN = 'https://claude.ai/oauth/authorize?code=true&state=abc'
const LOGIN = 'POST /api/auth/login'
const CODE = 'POST /api/auth/login/code'
const LOGOUT = 'POST /api/auth/logout'
const DISCONNECT_TEXT =
  'This signs the app out of Claude with claude auth logout. Runs stay disabled until you log in again. Outside Docker, ' +
  'this is also your own claude login on this machine.'

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

/** Disconnect, confirmed in its dialog; resolves once the section offers Log in with Claude again. */
async function disconnect(section) {
  fireEvent.click(within(section).getByRole('button', { name: 'Disconnect' }))
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Disconnect' }))
  return within(section).findByRole('button', { name: 'Log in with Claude' })
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

test('AC24, 046 FE14: a skeleton until /api/auth answers, then its error in an alert', async () => {
  mockFetch({ 'GET /api/auth': [500, { detail: 'boom' }] })
  renderAt('/settings')
  expectSkeleton(screen.getByRole('status'))
  expect((await screen.findByRole('alert')).textContent).toBe('boom')
  expect(screen.queryByRole('status')).toBeNull()
  expect(screen.queryByRole('region', { name: 'Claude login' })).toBeNull()
})

test('FE1: a claude.ai login shows Disconnect in the Claude login region; with runs disabled there is none', async () => {
  const { section, unmount } = await open(PRO)
  expect(within(section).getByRole('button', { name: 'Disconnect' })).toBeTruthy()
  unmount()
  const off = await open(OFF)
  expect(within(off.section).getByRole('button', { name: 'Log in with Claude' })).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Disconnect' })).toBeNull()
})

test('FE2: Disconnect opens a modal dialog naming the account, with the Q5 text, Cancel first and focused; nothing is posted', async () => {
  const showModal = vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function showModal() {
    this.open = true
    this.querySelector('button, a, input, [tabindex]').focus() // the dialog focusing steps: its first focusable element
  })
  for (const [auth, name] of [[PRO, 'Disconnect artem@example.com?'], [{ ...PRO, email: null }, 'Disconnect Claude?']]) {
    const { fetch, section, unmount } = await open(auth)
    expect(screen.queryByRole('dialog')).toBeNull()
    fireEvent.click(within(section).getByRole('button', { name: 'Disconnect' }))
    expect(showModal).toHaveBeenCalledOnce()
    const dialog = screen.getByRole('dialog', { name })
    expect(dialog.tagName).toBe('DIALOG')
    expect(document.getElementById(dialog.getAttribute('aria-describedby')).textContent).toBe(DISCONNECT_TEXT)
    expect(within(dialog).getAllByRole('button').map((b) => b.textContent)).toEqual(['Cancel', 'Disconnect'])
    expect(document.activeElement).toBe(within(dialog).getByRole('button', { name: 'Cancel' }))
    const confirm = within(dialog).getByRole('button', { name: 'Disconnect' })
    expect(confirm.className).toMatch(cls('bg-danger'))
    expect(confirm.className).toMatch(cls('text-surface'))
    expect(calls(fetch, LOGOUT)).toEqual([])
    showModal.mockClear()
    unmount()
  }
})

test('FE3: Cancel, or Esc, closes the dialog with no request; the login and Disconnect stay, and focus returns to it', async () => {
  const { fetch, section } = await open(PRO)
  const opener = within(section).getByRole('button', { name: 'Disconnect' })
  fireEvent.click(opener)
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(opener)
  fireEvent.click(opener)
  const dialog = screen.getByRole('dialog', { name: 'Disconnect artem@example.com?' })
  act(() => dialog.close()) // what Esc does after its cancel event
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(opener)
  expect(fetch.mock.calls.filter(([, init]) => init?.method && init.method !== 'GET')).toEqual([])
  expect(row('Plan')).toBe('Pro')
  expect(within(section).getByRole('button', { name: 'Disconnect' })).toBe(opener)
})

test("FE4: the dialog's Disconnect posts once; on 200 the dialog closes, the section is signed out, and focus is on Log in with Claude", async () => {
  const { fetch, section } = await open(PRO, { [LOGOUT]: [200, OFF] })
  fireEvent.click(within(section).getByRole('button', { name: 'Disconnect' }))
  const dialog = screen.getByRole('dialog')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Disconnect' }))
  const login = await within(section).findByRole('button', { name: 'Log in with Claude' })
  expect(dialog.open).toBe(false)
  expect(screen.queryByRole('dialog')).toBeNull()
  const posts = calls(fetch, LOGOUT)
  expect(posts).toHaveLength(1)
  expect(posts[0][1].headers['X-Requested-By']).toBe('fctl')
  expect(posts[0][1].body).toBeUndefined()
  for (const name of ['Auth method', 'Plan', 'Account']) expect(row(name)).toBe('—')
  expect(within(section).getByText('Not signed in with a Claude subscription — runs disabled')).toBeTruthy()
  expect(within(section).queryByText('Runs enabled')).toBeNull()
  expect(screen.queryByRole('button', { name: 'Disconnect' })).toBeNull()
  expect(document.activeElement).toBe(login)
})

test('FE5: a 409 or a 500 shows its detail inside the dialog, which stays open over the signed-in login', async () => {
  for (const [status, detail] of [[409, 'a run is active'], [500, 'claude auth logout failed: Error: keychain locked']]) {
    const { section, unmount } = await open(PRO, { [LOGOUT]: [status, { detail }] })
    fireEvent.click(within(section).getByRole('button', { name: 'Disconnect' }))
    const dialog = screen.getByRole('dialog', { name: 'Disconnect artem@example.com?' })
    const confirm = within(dialog).getByRole('button', { name: 'Disconnect' })
    fireEvent.click(confirm)
    expect((await within(dialog).findByRole('alert')).textContent).toBe(detail)
    await waitFor(() => expect(confirm.disabled).toBe(false))
    expect(dialog.open).toBe(true)
    expect(row('Plan')).toBe('Pro')
    expect(row('Account')).toBe('artem@example.com')
    expect(within(section).getByText('Runs enabled')).toBeTruthy()
    expect(within(section).getByRole('button', { name: 'Log in again' })).toBeTruthy()
    unmount()
  }
})

test('FE6: after a login on the page, a Disconnect removes its Logged in as status', async () => {
  const { section } = await open(OFF, { [CODE]: [200, PRO], [LOGOUT]: [200, OFF] })
  await startLogin('Log in with Claude')
  fireEvent.change(codeInput(), { target: { value: 'good#state' } })
  fireEvent.click(submitButton())
  expect((await screen.findByRole('status')).textContent).toBe('Logged in as artem@example.com')
  await disconnect(section)
  expect(screen.queryByText('Logged in as artem@example.com')).toBeNull()
  expect(screen.queryByRole('status')).toBeNull()
})

test('FE7: with a login form pending, a Disconnect removes the link, the Code field, and its refusal', async () => {
  const { section } = await open(PRO, { [CODE]: [422, { detail: 'Login failed: Invalid code' }], [LOGOUT]: [200, OFF] })
  await startLogin('Log in again')
  fireEvent.change(codeInput(), { target: { value: 'bad#state' } })
  fireEvent.click(submitButton())
  expect((await within(section).findByRole('alert')).textContent).toBe('Login failed: Invalid code')
  await disconnect(section)
  expect(screen.queryByRole('link', { name: 'Open the Claude sign-in page' })).toBeNull()
  expect(screen.queryByRole('textbox', { name: 'Code' })).toBeNull()
  expect(screen.queryByRole('alert')).toBeNull()
  expect(within(section).queryByRole('button', { name: 'Start over' })).toBeNull()
  expect(within(section).getByRole('button', { name: 'Log in with Claude' })).toBeTruthy()
})

test('round 2 (review-ui, review-ux): Esc while the logout is pending, then its 200, still signs the page out', async () => {
  const { fetch, section } = await open(PRO)
  const answer = fetch.getMockImplementation()
  let reply
  fetch.mockImplementation((url, init) =>
    url === '/api/auth/logout' ? new Promise((resolve) => (reply = resolve)) : answer(url, init),
  )
  fireEvent.click(within(section).getByRole('button', { name: 'Disconnect' }))
  const dialog = screen.getByRole('dialog')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Disconnect' }))
  await waitFor(() => expect(calls(fetch, LOGOUT)).toHaveLength(1))
  act(() => dialog.close()) // Esc, mid-request: the dialog unmounts
  expect(screen.queryByRole('dialog')).toBeNull()
  await act(async () => reply(new Response(JSON.stringify(OFF), { status: 200 })))
  const login = await within(section).findByRole('button', { name: 'Log in with Claude' })
  expect(row('Auth method')).toBe('—')
  expect(screen.queryByRole('button', { name: 'Disconnect' })).toBeNull()
  expect(document.activeElement).toBe(login)
})
