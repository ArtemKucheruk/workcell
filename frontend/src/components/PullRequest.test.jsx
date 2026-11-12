import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { fetched, mockFetch } from '../test/render.jsx'
import { MERGE_TEXT, PR_POLL, PullRequest } from './PullRequest.jsx'

const URL = 'https://github.com/o/r/pull/71'
const STATE = '/api/tasks/12/pr'
const MERGE = '/api/tasks/12/pr/merge'
const NOTES = ['Fast-forwarded main to origin/main.', 'Removed the worktree /w.', 'Deleted the local branch b.']
const noPr = (extra = {}) => ({ url: null, number: null, can_create: false, hint: 'Approve it first.', ...extra })
const withPr = { url: URL, number: 71, can_create: false, hint: null }
const prState = (state, checks = { passed: 2, failed: 1, pending: 0 }) => [200, { number: 71, url: URL, state, checks }]

afterEach(() => {
  vi.useRealTimers()
})

function show(pr, responses = {}) {
  const fetch = mockFetch(responses)
  const onChange = vi.fn()
  render(<PullRequest taskId={12} pr={pr} onChange={onChange} />)
  return { fetch, onChange, responses }
}

const button = (name) => screen.getByRole('button', { name })
const posts = (fetch, url) => fetch.mock.calls.filter(([u, init]) => u === url && init?.method === 'POST')
const states = (fetch) => fetched(fetch).filter((u) => u === STATE).length
const advance = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))

// --- Create PR ----------------------------------------------------------------------------

test('AC39: with can_create false and no url, Create PR is disabled with its hint beside it; no state is fetched', () => {
  for (const hint of ['Approve it first.', 'The worktree is gone.', 'Nothing to commit beyond main.']) {
    const { fetch } = show(noPr({ hint }))
    const create = button('Create PR')
    expect(create.disabled).toBe(true)
    expect(document.getElementById(create.getAttribute('aria-describedby')).textContent).toBe(hint)
    expect(fetch).not.toHaveBeenCalled()
    document.body.innerHTML = ''
  }
})

test('AC40: an enabled Create PR posts /pr with X-Requested-By, then refetches the page', async () => {
  const { fetch, onChange } = show(noPr({ can_create: true, hint: null }), {
    [`POST ${STATE}`]: [200, { number: 71, url: URL, reused: false }],
  })
  const create = button('Create PR')
  expect(create.disabled).toBe(false)
  expect(create.getAttribute('aria-describedby')).toBeNull()
  fireEvent.click(create)
  await waitFor(() => expect(onChange).toHaveBeenCalledTimes(1))
  const [call] = posts(fetch, STATE)
  expect(call[1].headers['X-Requested-By']).toBe('fctl')
})

test('AC40: a refusal shows its detail in an alert beside the buttons, and Create PR is enabled again', async () => {
  const detail = 'git push was rejected: ! [rejected]        b -> b (fetch first)'
  const { onChange } = show(noPr({ can_create: true, hint: null }), { [`POST ${STATE}`]: [409, { detail }] })
  fireEvent.click(button('Create PR'))
  expect((await screen.findByRole('alert')).textContent).toBe(detail)
  await waitFor(() => expect(button('Create PR').disabled).toBe(false))
  expect(onChange).not.toHaveBeenCalled()
})

// --- The PR line --------------------------------------------------------------------------

test('AC41: the PR link opens in a new tab and says so; the state is text beside an icon; checks are text', async () => {
  show(withPr, { [`GET ${STATE}`]: prState('OPEN') })
  const link = screen.getByRole('link', { name: /^PR #71 ?\(opens in a new tab\)$/ }) // jsdom drops the sr-only space
  expect(link.textContent).toBe('PR #71 (opens in a new tab)')
  expect([link.getAttribute('href'), link.getAttribute('target'), link.getAttribute('rel')]).toEqual([URL, '_blank', 'noreferrer'])
  const line = await screen.findByText(/checks: 2 passed, 1 failed, 0 pending/)
  expect(line.parentElement.textContent).toBe('● Open · checks: 2 passed, 1 failed, 0 pending')
  expect(line.parentElement.querySelector('[aria-hidden="true"]').textContent).toBe('●')
})

test('AC41: Merged, Closed, and no checks read as text', async () => {
  for (const [state, text] of [['MERGED', '✓ Merged · no checks'], ['CLOSED', '✕ Closed · no checks']]) {
    show(withPr, { [`GET ${STATE}`]: prState(state, { passed: 0, failed: 0, pending: 0 }) })
    const checks = await screen.findByText(/no checks/)
    expect(checks.parentElement.textContent).toBe(text)
    document.body.innerHTML = ''
  }
})

test('AC41: the state is polled every 10 s while OPEN, and polling stops once it is MERGED', async () => {
  vi.useFakeTimers()
  const { fetch, responses } = show(withPr, { [`GET ${STATE}`]: prState('OPEN') })
  await advance(0)
  expect(states(fetch)).toBe(1)
  await advance(PR_POLL - 1)
  expect(states(fetch)).toBe(1)
  await advance(1)
  expect(states(fetch)).toBe(2)
  responses[`GET ${STATE}`] = prState('MERGED')
  await advance(PR_POLL)
  expect(states(fetch)).toBe(3)
  expect(screen.getByText('Merged.')).toBeTruthy()
  await advance(PR_POLL * 5)
  expect(states(fetch)).toBe(3)
})

test('AC41: a failed state load keeps polling, since the state is not known yet', async () => {
  vi.useFakeTimers()
  const { fetch, responses } = show(withPr, { [`GET ${STATE}`]: [409, { detail: 'gh is not logged in: run gh auth login' }] })
  await advance(0)
  expect(screen.getByText('PR state: gh is not logged in: run gh auth login')).toBeTruthy()
  responses[`GET ${STATE}`] = prState('OPEN')
  await advance(PR_POLL)
  expect(states(fetch)).toBe(2)
  expect(screen.queryByText(/PR state:/)).toBeNull()
})

// --- Merge PR -----------------------------------------------------------------------------

test('AC42: Merge PR is enabled only while OPEN; otherwise disabled with its hint', async () => {
  const cases = [[null, 'Loading PR state…'], ['MERGED', 'Merged.'], ['CLOSED', 'Closed on GitHub.']]
  for (const [state, hint] of cases) {
    show(withPr, state ? { [`GET ${STATE}`]: prState(state) } : { [`GET ${STATE}`]: new TypeError('Failed to fetch') })
    if (state) await screen.findByText(/checks:/)
    else await screen.findByText(/PR state:/)
    const merge = button('Merge PR')
    expect(merge.disabled).toBe(true)
    expect(document.getElementById(merge.getAttribute('aria-describedby')).textContent).toBe(hint)
    document.body.innerHTML = ''
  }
  show(withPr, { [`GET ${STATE}`]: prState('OPEN') })
  await screen.findByText(/checks:/)
  expect(button('Merge PR').disabled).toBe(false)
  expect(button('Merge PR').getAttribute('aria-describedby')).toBeNull()
  expect(screen.queryByText('Loading PR state…')).toBeNull()
})

async function openDialog(responses = {}) {
  const view = show(withPr, { [`GET ${STATE}`]: prState('OPEN'), ...responses })
  await screen.findByText(/checks:/)
  fireEvent.click(button('Merge PR'))
  return { ...view, dialog: screen.getByRole('dialog') }
}

test('AC43: Merge PR opens the native dialog, titled Merge PR #71?, saying what it does', async () => {
  const { dialog } = await openDialog()
  expect(dialog.tagName).toBe('DIALOG')
  expect(dialog.open).toBe(true)
  expect(within(dialog).getByRole('heading').textContent).toBe('Merge PR #71?')
  expect(MERGE_TEXT).toMatch(/merge commit/)
  expect(MERGE_TEXT).toMatch(/fast-forwards main if that is safe/)
  expect(MERGE_TEXT).toMatch(/the worktree, the local branch, and the remote branch/)
  expect(within(dialog).getByText(MERGE_TEXT)).toBeTruthy()
  expect(within(dialog).getByRole('button', { name: 'Merge PR' })).toBeTruthy()
})

test('AC43: Cancel and Esc close the dialog without a request', async () => {
  const { fetch, dialog } = await openDialog()
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  fireEvent.click(button('Merge PR'))
  act(() => screen.getByRole('dialog').close()) // the close event Esc raises
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(posts(fetch, MERGE)).toEqual([])
})

test('AC44: confirming posts /pr/merge, closes the dialog, lists the notes in a status region, and refetches', async () => {
  const { fetch, onChange, dialog, responses } = await openDialog({
    [`POST ${MERGE}`]: [200, { number: 71, state: 'MERGED', notes: NOTES }],
  })
  responses[`GET ${STATE}`] = prState('MERGED')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Merge PR' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  const [call] = posts(fetch, MERGE)
  expect(call[1].headers['X-Requested-By']).toBe('fctl')
  const status = screen.getAllByRole('status').find((el) => el.querySelector('li'))
  expect([...status.querySelectorAll('li')].map((li) => li.textContent)).toEqual(NOTES)
  expect(onChange).toHaveBeenCalledTimes(1)
  await waitFor(() => expect(button('Merge PR').disabled).toBe(true))
  expect(screen.getByText('Merged.')).toBeTruthy()
})

test('AC44: a refused merge shows inside the dialog, which stays open', async () => {
  const detail = 'X Pull request o/r#71 is not mergeable: the base branch policy prohibits the merge.'
  const { onChange, dialog } = await openDialog({ [`POST ${MERGE}`]: [409, { detail }] })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Merge PR' }))
  expect((await within(dialog).findByRole('alert')).textContent).toBe(detail)
  expect(dialog.open).toBe(true)
  expect(onChange).not.toHaveBeenCalled()
})
