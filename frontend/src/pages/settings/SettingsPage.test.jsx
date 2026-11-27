import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { cls, expectSkeleton, mockFetch, renderAt } from '../../test/render.jsx'

afterEach(() => vi.restoreAllMocks())

const ONE = {
  id: 1,
  config_dir: '/home/me/.claude',
  active: true,
  signed_in: true,
  auth_method: 'claude.ai',
  plan: 'pro',
  email: 'artem@example.com',
}
const TWO = {
  id: 2,
  config_dir: '/home/me/.workcell/claude-accounts/k3j2h1x9',
  active: false,
  signed_in: false,
  auth_method: null,
  plan: null,
  email: null,
}
const THREE = {
  id: 3,
  config_dir: '/home/me/.workcell/claude-accounts/p9q8r7s6',
  active: false,
  signed_in: true,
  auth_method: 'claude.ai',
  plan: 'max',
  email: 'second@example.com',
}
const AUTH = { auth_method: 'claude.ai', plan: 'pro', runs_enabled: true, email: 'artem@example.com' }
const SIGN_IN = 'https://claude.ai/oauth/authorize?code=true&state=abc'
const ACCOUNTS = 'GET /api/auth/accounts'
const LOGIN = 'POST /api/auth/login'
const CODE = 'POST /api/auth/login/code'
const ACTIVATE_2 = 'POST /api/auth/accounts/2/activate'
const DELETE_2 = 'DELETE /api/auth/accounts/2'
const SETTINGS = 'GET /api/settings'
const PUT_SETTINGS = 'PUT /api/settings'
const DISCONNECT_TEXT =
  'This signs the account out with claude auth logout and removes it from the app, with its config folder if the app ' +
  'created it.'
const ACTIVE_TEXT = ' Runs stay disabled until you make another account preferred.' // 097 Q8

/**
 * Renders /settings with the accounts list answering `accounts`, and waits for the Claude accounts region. `responses`
 * is read on every call, so a test can change an answer between clicks.
 */
async function open(accounts, extra = {}) {
  const responses = {
    'GET /api/auth': [200, AUTH],
    [ACCOUNTS]: [200, accounts],
    [LOGIN]: [200, { url: SIGN_IN, account_id: 3 }],
    [SETTINGS]: [200, { max_concurrent_runs: 2 }],
    ...extra,
  }
  const fetch = mockFetch(responses)
  const view = renderAt('/settings')
  const section = await screen.findByRole('region', { name: 'Claude accounts' })
  return { fetch, responses, section, ...view }
}
/** The fetch calls to "METHOD url", as [url, init]. */
const calls = (fetch, key) => fetch.mock.calls.filter(([url, init = {}]) => `${init.method ?? 'GET'} ${url}` === key)
const sent = (call) => (call[1].body === undefined ? undefined : JSON.parse(call[1].body))
const items = (section) => within(section).getAllByRole('listitem')
/** The <dd> beside the <dt> named `name`, in `item`. */
const dd = (item, name) => within(item).getByText(name, { selector: 'dt' }).nextElementSibling
const row = (item, name) => dd(item, name).textContent
const buttons = (item) => within(item).getAllByRole('button').map((b) => b.textContent)
const pill = (item) => within(item).queryByText('preferred', { exact: true }) // 097 Q8: the active account's marker
const codeInput = () => screen.getByRole('textbox', { name: 'Code' })
const submitButton = () => screen.getByRole('button', { name: 'Submit code' })
const signInLink = () => screen.queryByRole('link', { name: 'Open the Claude sign-in page' })
const follows = (a, b) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)

/** Clicks `button`, then waits for the sign-in link. */
async function startLogin(button) {
  fireEvent.click(button)
  await screen.findByRole('link', { name: 'Open the Claude sign-in page' })
}

test('FE1: the list loads once, one item per account in order, with its email, pill, plan, method, and folder', async () => {
  const { fetch, section } = await open([ONE, TWO])
  expect(screen.getByRole('heading', { level: 1, name: 'Settings' })).toBeTruthy()
  expect(document.title).toBe('Settings · Workcell')
  expect(calls(fetch, ACCOUNTS)).toHaveLength(1)
  const [one, two] = items(section)
  expect(items(section)).toHaveLength(2)

  expect(within(one).getByRole('heading', { name: 'artem@example.com' })).toBeTruthy()
  expect(pill(one).className).toMatch(cls('border-accent'))
  expect(pill(one).className).toMatch(cls('text-accent'))
  expect(row(one, 'Plan')).toBe('Pro')
  expect(row(one, 'Auth method')).toBe('claude.ai')
  expect(row(one, 'Folder')).toBe('/home/me/.claude')
  expect(dd(one, 'Folder').className).toMatch(cls('font-mono'))
  expect(dd(one, 'Folder').className).toMatch(cls('text-muted'))

  expect(within(two).getByRole('heading', { name: 'Not signed in' })).toBeTruthy()
  expect(pill(two)).toBeNull()
  expect(row(two, 'Plan')).toBe('—')
  expect(row(two, 'Auth method')).toBe('—')
  expect(row(two, 'Folder')).toBe(TWO.config_dir)
  expect(screen.queryByRole('textbox')).toBeNull()
})

test('FE1, round 1 review-ui: a signed-in account with no email is titled Not signed in, as Q11 words it', async () => {
  const { section } = await open([{ ...ONE, email: null }])
  const [one] = items(section)
  expect(within(one).getByRole('heading', { name: 'Not signed in' })).toBeTruthy()
  expect(row(one, 'Plan')).toBe('Pro')
  expect(buttons(one)).toEqual(['Log in again', 'Disconnect'])
})

test('FE2: Make active only on inactive items, Log in again or Log in by sign-in, Disconnect on all; + Add account below', async () => {
  const { section } = await open([ONE, TWO, THREE])
  const [one, two, three] = items(section)
  expect(buttons(one)).toEqual(['Log in again', 'Disconnect'])
  expect(buttons(two)).toEqual(['Make preferred','Log in', 'Disconnect'])
  expect(buttons(three)).toEqual(['Make preferred','Log in again', 'Disconnect'])
  const add = within(section).getByRole('button', { name: '+ Add account' })
  expect(follows(within(section).getByRole('list'), add)).toBe(true)
})

test('FE3, round 2 review-ui: below the list and + Add account, whether runs are enabled, from the active account', async () => {
  for (const [accounts, text, red] of [
    [[ONE, TWO], 'Runs enabled', false],
    [[{ ...ONE, active: false }, TWO], 'No preferred account — runs disabled', true],
    [[{ ...ONE, active: false }, { ...TWO, active: true }], 'Not signed in with a Claude subscription — runs disabled', true],
  ]) {
    const { section, unmount } = await open(accounts)
    const line = within(section).getByText(text)
    expect(follows(within(section).getByRole('list'), line)).toBe(true)
    expect(follows(within(section).getByRole('button', { name: '+ Add account' }), line)).toBe(true)
    expect(cls('text-danger').test(line.className)).toBe(red)
    unmount()
  }
})

test('FE4, round 2 review-ui: an empty list says so, then + Add account, then no active account', async () => {
  const { section } = await open([])
  const empty = within(section).getByText('No Claude accounts yet.')
  const add = within(section).getByRole('button', { name: '+ Add account' })
  const line = within(section).getByText('No preferred account — runs disabled')
  expect(within(section).queryAllByRole('listitem')).toEqual([])
  expect(follows(empty, add)).toBe(true)
  expect(follows(add, line)).toBe(true)
  expect(line.className).toMatch(cls('text-danger'))
})

test('FE5: Make active posts once, reloads the list, and moves the pill; focus goes to its login button', async () => {
  const { fetch, responses, section } = await open([ONE, TWO], { [ACTIVATE_2]: [200, { ...AUTH, plan: null, email: null }] })
  responses[ACCOUNTS] = [200, [{ ...ONE, active: false }, { ...TWO, active: true }]]
  fireEvent.click(within(items(section)[1]).getByRole('button', { name: 'Make preferred' }))
  await waitFor(() => expect(pill(items(section)[1])).toBeTruthy())
  const posts = calls(fetch, ACTIVATE_2)
  expect(posts).toHaveLength(1)
  expect(posts[0][1].headers['X-Requested-By']).toBe('fctl')
  expect(calls(fetch, ACCOUNTS)).toHaveLength(2)
  const [one, two] = items(section)
  expect(pill(one)).toBeNull()
  expect(buttons(one)).toEqual(['Make preferred','Log in again', 'Disconnect'])
  expect(buttons(two)).toEqual(['Log in', 'Disconnect'])
  await waitFor(() => expect(document.activeElement).toBe(within(two).getByRole('button', { name: 'Log in' })))
})

test('FE5, round 1 review-ui, review-ux: Make active clears a Logged in as status left by a code', async () => {
  const { responses, section } = await open([ONE], { [CODE]: [200, AUTH], 'POST /api/auth/accounts/1/activate': [200, AUTH] })
  await startLogin(within(section).getByRole('button', { name: '+ Add account' }))
  responses[ACCOUNTS] = [200, [{ ...ONE, active: false }, { ...THREE, active: true }]]
  fireEvent.change(codeInput(), { target: { value: 'good#state' } })
  fireEvent.click(submitButton())
  expect((await within(section).findByRole('status')).textContent).toBe('Logged in as second@example.com')
  responses[ACCOUNTS] = [200, [ONE, THREE]]
  fireEvent.click(within(items(section)[0]).getByRole('button', { name: 'Make preferred' }))
  await waitFor(() => expect(pill(items(section)[0])).toBeTruthy())
  expect(within(section).queryByRole('status')).toBeNull()
})

test('FE5: a refused Make active shows its detail in the region, reloads nothing, and leaves the pill', async () => {
  const { fetch, section } = await open([ONE, TWO], { [ACTIVATE_2]: [409, { detail: 'a run is active' }] })
  fireEvent.click(within(items(section)[1]).getByRole('button', { name: 'Make preferred' }))
  expect((await within(section).findByRole('alert')).textContent).toBe('a run is active')
  expect(calls(fetch, ACCOUNTS)).toHaveLength(1)
  expect(pill(items(section)[0])).toBeTruthy()
  expect(pill(items(section)[1])).toBeNull()
})

test('FE6: + Add account posts with no account_id and shows the sign-in link and the Code field', async () => {
  const { fetch, section } = await open([ONE])
  await startLogin(within(section).getByRole('button', { name: '+ Add account' }))
  const posts = calls(fetch, LOGIN)
  expect(posts).toHaveLength(1)
  expect(posts[0][1].headers['X-Requested-By']).toBe('fctl')
  expect(sent(posts[0])).toBeUndefined()
  const link = signInLink()
  expect(link.getAttribute('href')).toBe(SIGN_IN)
  expect(link.getAttribute('target')).toBe('_blank')
  expect(link.getAttribute('rel')).toBe('noopener noreferrer')
  expect(codeInput()).toBeTruthy()
  expect(within(items(section)[0]).queryByRole('textbox')).toBeNull() // a new account's form isn't in another's item
  expect(submitButton().disabled).toBe(true)
  fireEvent.change(codeInput(), { target: { value: '   ' } })
  expect(submitButton().disabled).toBe(true)
})

test("FE7: Submit code sends the trimmed code and the login's account_id; on 200 the list reloads and the form goes", async () => {
  for (const [three, text] of [[THREE, 'Logged in as second@example.com'], [{ ...THREE, email: null }, 'Logged in']]) {
    const { fetch, responses, section, unmount } = await open([ONE], { [CODE]: [200, AUTH] })
    await startLogin(within(section).getByRole('button', { name: '+ Add account' }))
    responses[ACCOUNTS] = [200, [ONE, three]]
    fireEvent.change(codeInput(), { target: { value: ' good#state ' } })
    fireEvent.submit(codeInput().form) // the button's click, or Enter in the field
    expect((await within(section).findByRole('status')).textContent).toBe(text)
    const codes = calls(fetch, CODE)
    expect(codes).toHaveLength(1)
    expect(codes[0][1].headers['X-Requested-By']).toBe('fctl')
    expect(sent(codes[0])).toEqual({ code: 'good#state', account_id: 3 })
    expect(calls(fetch, ACCOUNTS)).toHaveLength(2)
    expect(items(section)).toHaveLength(2)
    expect(signInLink()).toBeNull()
    expect(screen.queryByRole('textbox')).toBeNull()
    expect(within(section).getByRole('button', { name: '+ Add account' })).toBeTruthy()
    unmount()
  }
})

test('FE7: a refused code shows its detail, and the form and the typed code stay', async () => {
  const { fetch, section } = await open([ONE], { [CODE]: [422, { detail: 'Login failed: Invalid code' }] })
  await startLogin(within(section).getByRole('button', { name: '+ Add account' }))
  fireEvent.change(codeInput(), { target: { value: 'bad#state' } })
  fireEvent.click(submitButton())
  expect((await within(section).findByRole('alert')).textContent).toBe('Login failed: Invalid code')
  expect(codeInput().value).toBe('bad#state')
  expect(signInLink()).toBeTruthy()
  await waitFor(() => expect(submitButton().disabled).toBe(false))
  expect(calls(fetch, ACCOUNTS)).toHaveLength(1)
  expect(within(section).queryByRole('status')).toBeNull()
})

const HINT =
  'The page signs in the claude.ai account your browser is signed into. For a different account, open the link in a ' +
  'private window or sign out of claude.ai first.'
const DUPLICATE =
  'already connected as artem@example.com (account #1); to add a different account, open the sign-in link in a ' +
  'private window or sign out of claude.ai first'

test('110 AC8: the sign-in form has one muted hint line under the sign-in link, on how to add a different account', async () => {
  const { section } = await open([ONE])
  await startLogin(within(section).getByRole('button', { name: '+ Add account' }))
  const hint = screen.getByText(HINT)
  expect(hint.tagName).toBe('P')
  expect(hint.className).toMatch(cls('text-muted'))
  expect(follows(signInLink(), hint)).toBe(true)
  expect(follows(hint, codeInput())).toBe(true)
})

test('110 AC9: a 409 on Submit code shows its detail, closes the form, and reloads the list, with no Logged in line', async () => {
  const { fetch, responses, section } = await open([ONE], { [CODE]: [409, { detail: DUPLICATE }] })
  await startLogin(within(section).getByRole('button', { name: '+ Add account' }))
  responses[ACCOUNTS] = [200, [ONE, TWO]]
  fireEvent.change(codeInput(), { target: { value: 'good#state' } })
  fireEvent.click(submitButton())
  await waitFor(() => expect(calls(fetch, ACCOUNTS)).toHaveLength(2))
  await waitFor(() => expect(items(section)).toHaveLength(2))
  expect(within(section).getByRole('alert').textContent).toBe(DUPLICATE)
  expect(signInLink()).toBeNull()
  expect(screen.queryByRole('textbox', { name: 'Code' })).toBeNull()
  expect(within(section).queryByRole('status')).toBeNull()
})

test("FE8: Log in again sends the item's account_id and becomes Start over, which resends it; an add's Start over resends 3", async () => {
  const { fetch, section } = await open([ONE, TWO], { [LOGIN]: [200, { url: SIGN_IN, account_id: 1 }] })
  const one = items(section)[0]
  await startLogin(within(one).getByRole('button', { name: 'Log in again' }))
  expect(within(one).getByRole('textbox', { name: 'Code' })).toBeTruthy() // the form sits in its account's item
  const again = within(one).getByRole('button', { name: 'Start over' })
  expect(within(section).getAllByRole('button', { name: 'Start over' })).toEqual([again])
  fireEvent.click(again)
  await waitFor(() => expect(calls(fetch, LOGIN)).toHaveLength(2))
  expect(calls(fetch, LOGIN).map(sent)).toEqual([{ account_id: 1 }, { account_id: 1 }])
})

test('FE8: after + Add account answers account_id 3, its Start over sends account_id 3, not a new account', async () => {
  const { fetch, section } = await open([ONE, TWO])
  await startLogin(within(section).getByRole('button', { name: '+ Add account' }))
  expect(within(section).queryByRole('button', { name: '+ Add account' })).toBeNull()
  for (const item of items(section)) expect(within(item).queryByRole('button', { name: 'Start over' })).toBeNull()
  fireEvent.click(within(section).getByRole('button', { name: 'Start over' }))
  await waitFor(() => expect(calls(fetch, LOGIN)).toHaveLength(2))
  expect(calls(fetch, LOGIN).map(sent)).toEqual([undefined, { account_id: 3 }])
})

test('FE8: a refused login start shows its detail in an alert, with no form', async () => {
  const detail = 'claude auth login printed no sign-in URL: Error: managed settings forbid this'
  const { section } = await open([ONE, TWO], { [LOGIN]: [500, { detail }] })
  fireEvent.click(within(items(section)[1]).getByRole('button', { name: 'Log in' }))
  expect((await within(section).findByRole('alert')).textContent).toBe(detail)
  expect(screen.queryByRole('textbox')).toBeNull()
  expect(within(items(section)[1]).getByRole('button', { name: 'Log in' })).toBeTruthy()
})

test('FE9: Disconnect opens a modal dialog naming the account, with the Q11 text, Cancel first and focused; nothing is sent', async () => {
  const showModal = vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function showModal() {
    this.open = true
    this.querySelector('button, a, input, [tabindex]').focus() // the dialog focusing steps: its first focusable element
  })
  const { fetch, section } = await open([ONE, TWO])
  for (const [index, name, text] of [
    [1, 'Disconnect this account?', DISCONNECT_TEXT],
    [0, 'Disconnect artem@example.com?', DISCONNECT_TEXT + ACTIVE_TEXT],
  ]) {
    expect(screen.queryByRole('dialog')).toBeNull()
    fireEvent.click(within(items(section)[index]).getByRole('button', { name: 'Disconnect' }))
    expect(showModal).toHaveBeenCalledOnce()
    const dialog = screen.getByRole('dialog', { name })
    expect(dialog.tagName).toBe('DIALOG')
    expect(document.getElementById(dialog.getAttribute('aria-describedby')).textContent).toBe(text)
    expect(within(dialog).getAllByRole('button').map((b) => b.textContent)).toEqual(['Cancel', 'Disconnect'])
    expect(document.activeElement).toBe(within(dialog).getByRole('button', { name: 'Cancel' }))
    const confirm = within(dialog).getByRole('button', { name: 'Disconnect' })
    expect(confirm.className).toMatch(cls('bg-danger'))
    expect(confirm.className).toMatch(cls('text-surface'))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    showModal.mockClear()
  }
  expect(fetch.mock.calls.filter(([, init]) => init?.method === 'DELETE')).toEqual([])
})

test('FE9: Cancel, or Esc, closes the dialog with no DELETE; the list stays, and focus returns to Disconnect', async () => {
  const { fetch, section } = await open([ONE, TWO])
  const opener = within(items(section)[1]).getByRole('button', { name: 'Disconnect' })
  fireEvent.click(opener)
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(opener)
  fireEvent.click(opener)
  const dialog = screen.getByRole('dialog', { name: 'Disconnect this account?' })
  act(() => dialog.close()) // what Esc does after its cancel event
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(opener)
  expect(fetch.mock.calls.filter(([, init]) => init?.method && init.method !== 'GET')).toEqual([])
  expect(items(section)).toHaveLength(2)
})

test("FE10: the dialog's Disconnect sends one DELETE; on 204 it closes, the list reloads without the item, and focus is on + Add account", async () => {
  const { fetch, responses, section } = await open([ONE, TWO], { [DELETE_2]: [204] })
  responses[ACCOUNTS] = [200, [ONE]]
  fireEvent.click(within(items(section)[1]).getByRole('button', { name: 'Disconnect' }))
  const dialog = screen.getByRole('dialog')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Disconnect' }))
  await waitFor(() => expect(items(section)).toHaveLength(1))
  expect(dialog.open).toBe(false)
  expect(screen.queryByRole('dialog')).toBeNull()
  const deletes = calls(fetch, DELETE_2)
  expect(deletes).toHaveLength(1)
  expect(deletes[0][1].headers['X-Requested-By']).toBe('fctl')
  expect(calls(fetch, ACCOUNTS)).toHaveLength(2)
  expect(within(items(section)[0]).getByRole('heading', { name: 'artem@example.com' })).toBeTruthy()
  await waitFor(() => expect(document.activeElement).toBe(within(section).getByRole('button', { name: '+ Add account' })))
})

test("FE10: Disconnecting the account whose login is pending drops its form; another account's stays (Q12)", async () => {
  const { responses, section } = await open([ONE, TWO], {
    [LOGIN]: [200, { url: SIGN_IN, account_id: 2 }],
    [DELETE_2]: [204],
    'DELETE /api/auth/accounts/1': [204],
  })
  await startLogin(within(items(section)[1]).getByRole('button', { name: 'Log in' }))
  responses[ACCOUNTS] = [200, [TWO]]
  fireEvent.click(within(items(section)[0]).getByRole('button', { name: 'Disconnect' }))
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Disconnect' }))
  await waitFor(() => expect(items(section)).toHaveLength(1))
  expect(within(items(section)[0]).getByRole('textbox', { name: 'Code' })).toBeTruthy()
  responses[ACCOUNTS] = [200, []]
  fireEvent.click(within(items(section)[0]).getByRole('button', { name: 'Disconnect' }))
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Disconnect' }))
  expect(await within(section).findByText('No Claude accounts yet.')).toBeTruthy()
  expect(signInLink()).toBeNull()
  expect(screen.queryByRole('textbox')).toBeNull()
})

test('FE11: a 409 or a 500 shows its detail inside the dialog, which stays open over the unchanged list', async () => {
  for (const [status, detail] of [[409, 'a run is active'], [500, 'claude auth logout failed: Error: keychain locked']]) {
    const { fetch, section, unmount } = await open([ONE, TWO], { [DELETE_2]: [status, { detail }] })
    fireEvent.click(within(items(section)[1]).getByRole('button', { name: 'Disconnect' }))
    const dialog = screen.getByRole('dialog', { name: 'Disconnect this account?' })
    const confirm = within(dialog).getByRole('button', { name: 'Disconnect' })
    fireEvent.click(confirm)
    expect((await within(dialog).findByRole('alert')).textContent).toBe(detail)
    await waitFor(() => expect(confirm.disabled).toBe(false))
    expect(dialog.open).toBe(true)
    expect(calls(fetch, ACCOUNTS)).toHaveLength(1)
    expect(items(section)).toHaveLength(2)
    expect(row(items(section)[1], 'Folder')).toBe(TWO.config_dir)
    unmount()
  }
})

test('FE11, 055 round 2: Esc while the DELETE is pending, then its 204, still reloads the list', async () => {
  const { fetch, responses, section } = await open([ONE, TWO])
  const answer = fetch.getMockImplementation()
  let reply
  fetch.mockImplementation((url, init) =>
    init?.method === 'DELETE' ? new Promise((resolve) => (reply = resolve)) : answer(url, init),
  )
  responses[ACCOUNTS] = [200, [ONE]]
  fireEvent.click(within(items(section)[1]).getByRole('button', { name: 'Disconnect' }))
  const dialog = screen.getByRole('dialog')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Disconnect' }))
  await waitFor(() => expect(calls(fetch, DELETE_2)).toHaveLength(1))
  act(() => dialog.close()) // Esc, mid-request: the dialog unmounts
  expect(screen.queryByRole('dialog')).toBeNull()
  await act(async () => reply(new Response(null, { status: 204 })))
  await waitFor(() => expect(items(section)).toHaveLength(1))
  await waitFor(() => expect(document.activeElement).toBe(within(section).getByRole('button', { name: '+ Add account' })))
})

// --- 096: the Runs section ----------------------------------------------------------------

const runsRegion = () => screen.findByRole('region', { name: 'Runs' })
const capField = () => screen.findByRole('spinbutton', { name: 'Concurrent runs' })

test('096 AC34: a Runs section below Claude accounts holds Concurrent runs (1–10) with the stored value, loaded once', async () => {
  const { fetch, section } = await open([ONE], { [SETTINGS]: [200, { max_concurrent_runs: 4 }] })
  const runs = await runsRegion()
  expect(follows(section, runs)).toBe(true)
  const input = await capField()
  await waitFor(() => expect(input.value).toBe('4'))
  expect([input.type, input.min, input.max]).toEqual(['number', '1', '10'])
  expect(within(runs).getByText('How many runs can go at once, across all projects.').className).toMatch(cls('text-muted'))
  expect(calls(fetch, SETTINGS)).toHaveLength(1)
})

test('096 AC35: Save sends PUT /api/settings with the number, then says Saved in a status line', async () => {
  const { fetch } = await open([ONE], { [PUT_SETTINGS]: [200, { max_concurrent_runs: 3 }] })
  const input = await capField()
  await waitFor(() => expect(input.value).toBe('2'))
  fireEvent.change(input, { target: { value: '3' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  const status = await within(await runsRegion()).findByRole('status')
  expect(status.textContent).toBe('Saved')
  const [put] = calls(fetch, PUT_SETTINGS)
  expect(sent(put)).toEqual({ max_concurrent_runs: 3 })
  expect(put[1].headers['X-Requested-By']).toBe('fctl')
})

test('096 AC36: a refused Save shows the alert and keeps the typed value', async () => {
  await open([ONE], { [PUT_SETTINGS]: [422, { detail: [{ loc: ['body', 'max_concurrent_runs'], msg: 'too big' }] }] })
  const input = await capField()
  await waitFor(() => expect(input.value).toBe('2'))
  fireEvent.change(input, { target: { value: '7' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  const runs = await runsRegion()
  expect((await within(runs).findByRole('alert')).textContent).toContain('max_concurrent_runs: too big')
  expect(input.value).toBe('7')
  expect(within(runs).queryByRole('status')).toBeNull()
})

test('FE12, 046 FE14: a skeleton until the accounts list answers, then its error in an alert', async () => {
  mockFetch({ 'GET /api/auth': [200, AUTH], [ACCOUNTS]: [500, { detail: 'boom' }] })
  renderAt('/settings')
  expectSkeleton(screen.getByRole('status'))
  expect((await screen.findByRole('alert')).textContent).toBe('boom')
  expect(screen.queryByRole('status')).toBeNull()
  expect(screen.queryByRole('region', { name: 'Claude accounts' })).toBeNull()
})
