import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { expectOfflineBanner, expectSkeleton, fetched, fullText, mockFetch, renderAt } from '../../test/render.jsx'
import { optionLabels, pick as pickValue } from '../../test/select.js'

const BOARD = '/api/pages/projects/3'
const LIST = '/api/projects/3/schedules'
const FACTORIES = '/api/projects/3/factories'
const PROJECT = { id: 3, name: 'api-server', workspace_id: 2, workspace: 'personal' }
const ACCOUNTS = [
  { id: 1, label: 'a@x', active: true, five_hour: null, seven_day: null },
  { id: 2, label: 'b@y', active: false, five_hour: null, seven_day: null },
]
const board = () => ({
  project: PROJECT, factory: 'ready', hint: null, can_run: true, workspaces: [],
  columns: { backlog: [], in_progress: [], review: [], done: [] },
  runs_enabled: true, runs_active: 0, max_concurrent_runs: 2, accounts: ACCOUNTS, auto: { account_id: 1, label: 'a@x' },
})
const factory = (id, name, kind = 'automation') => ({
  id, name, kind, nodes: 7, created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z',
})
const FACTORY_LIST = [factory(7, 'default', 'workflow'), factory(11, 'Nightly'), factory(9, 'Security audit'),
  factory(10, 'Test coverage')]
// now is 2026-10-20 12:00 in Tokyo (UTC+9), 03:00Z
const AUDIT = {
  id: 4, factory_id: 9, automation: 'Security audit', cron: '0 9 * * 1', summary: 'Weekly on Monday at 09:00',
  enabled: true, account_id: null, account: null, next_run_at: '2026-10-20T03:05:00Z',
  last_run: { id: 43, status: 'succeeded', started_at: '2026-10-20T02:55:00Z' }, last_skip: null, last_skip_at: null,
}
const COVERAGE = {
  id: 5, factory_id: 10, automation: 'Test coverage', cron: '*/15 9-17 * * 1-5', summary: 'Custom: */15 9-17 * * 1-5',
  enabled: false, account_id: 2, account: 'b@y', next_run_at: null, last_run: null,
  last_skip: 'run #41 of Test coverage is still running', last_skip_at: '2026-10-20T02:00:00Z',
}

beforeEach(() => {
  vi.stubEnv('TZ', 'Asia/Tokyo')
  vi.setSystemTime(new Date('2026-10-20T12:00:00+09:00'))
})
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
})

/** Renders /projects/3/scheduler with `list` as the schedules' reply; waits for the h1. */
async function open(list = [200, [AUDIT, COVERAGE]], more = {}) {
  const responses = {
    [`GET ${BOARD}`]: [200, board()], [`GET ${LIST}`]: list, [`GET ${FACTORIES}`]: [200, FACTORY_LIST], ...more,
  }
  const fetch = mockFetch(responses)
  const view = renderAt('/projects/3/scheduler')
  await screen.findByRole('heading', { level: 1, name: 'Scheduler' })
  return { fetch, responses, ...view }
}

const rows = () => screen.getAllByRole('row').slice(1) // the header row first
const cells = (tr) => within(tr).getAllByRole('cell')
const calls = (fetch, method, url) => fetch.mock.calls.filter(([u, init]) => u === url && (init?.method ?? 'GET') === method)
const sent = (fetch, method, url) => calls(fetch, method, url).map(([, init]) => JSON.parse(init.body))
const form = () => document.getElementById('schedule-form')
const inForm = () => within(form())
const pick = (name, value) => pickValue(inForm().getByRole('combobox', { name, hidden: true }), value)
const options = (name) => optionLabels(inForm().getByRole('combobox', { name, hidden: true }))
const submit = (label = 'Create') => fireEvent.click(inForm().getByRole('button', { name: label, hidden: true }))
const timeInput = () => form().querySelector('input[type="time"]')

test('104 AC24: loads the header, the schedules, and the factories; one row per schedule in the API order', async () => {
  const { fetch } = await open()
  expect(fetched(fetch).filter((u) => u !== '/api/auth' && !u.startsWith('/api/pages/sidebar')).sort()).toEqual(
    [BOARD, FACTORIES, LIST].sort(),
  )
  expect(screen.getByRole('heading', { level: 1, name: 'api-server · personal' })).toBeTruthy()
  await waitFor(() => expect(document.title).toBe('api-server · Scheduler · Workcell'))
  const [audit, coverage] = rows()
  expect(rows()).toHaveLength(2)

  const [name, summary, next, last, account] = cells(audit)
  expect(within(name).getByRole('link', { name: 'Security audit' }).getAttribute('href')).toBe('/projects/3/factories/9/runs')
  expect(summary.textContent).toBe('Weekly on Monday at 09:00')
  const nextTime = next.querySelector('time')
  expect([nextTime.textContent, nextTime.getAttribute('title')]).toEqual(['in 5m', '2026-10-20 12:05'])
  expect(within(last).getByRole('link', { name: 'run #43' }).getAttribute('href')).toBe('/projects/3/factories/9/runs?run=43')
  expect(last.textContent).toBe('run #43succeeded5m ago')
  expect(account.textContent).toBe('Auto')

  const [cName, , cNext, cLast, cAccount] = cells(coverage)
  expect(within(cName).getByRole('link', { name: 'Test coverage' }).getAttribute('href')).toBe('/projects/3/factories/10/runs')
  expect(cNext.textContent).toBe('Paused')
  expect(within(cLast).getByText('No runs yet')).toBeTruthy()
  expect(within(cLast).getByText(fullText('Skipped 1h ago: run #41 of Test coverage is still running'))).toBeTruthy()
  expect(cAccount.textContent).toBe('b@y')
})

test('104 AC25: Pause and Resume send PATCH enabled, then reload; their state is in the text; a refusal is the alert', async () => {
  const { fetch, responses } = await open(undefined, {
    'PATCH /api/schedules/4': [200, { ...AUDIT, enabled: false }],
    'PATCH /api/schedules/5': [409, { detail: 'schedule #5 not found' }],
  })
  const pause = screen.getByRole('button', { name: 'Pause Security audit' })
  const resume = screen.getByRole('button', { name: 'Resume Test coverage' })
  expect([pause.textContent, resume.textContent]).toEqual(['Pause', 'Resume'])
  const before = calls(fetch, 'GET', LIST).length
  responses[`GET ${LIST}`] = [200, [{ ...AUDIT, enabled: false, next_run_at: null }, COVERAGE]]
  fireEvent.click(pause)
  await waitFor(() => expect(screen.getByRole('button', { name: 'Resume Security audit' })).toBeTruthy())
  expect(sent(fetch, 'PATCH', '/api/schedules/4')).toEqual([{ enabled: false }])
  expect(calls(fetch, 'GET', LIST).length).toBeGreaterThan(before)
  expect(cells(rows()[0])[2].textContent).toBe('Paused')
  fireEvent.click(screen.getByRole('button', { name: 'Resume Test coverage' }))
  expect((await screen.findByRole('alert')).textContent).toBe('schedule #5 not found')
  expect(sent(fetch, 'PATCH', '/api/schedules/5')).toEqual([{ enabled: true }])
})

test('104 AC26: + Schedule automation offers the unscheduled automations, the presets, and Auto first; Create posts the cron', async () => {
  const created = { ...AUDIT, id: 6, factory_id: 11, automation: 'Nightly' }
  const { fetch, responses } = await open(undefined, { [`POST ${LIST}`]: [201, created] })
  const add = screen.getByRole('button', { name: '+ Schedule automation' })
  expect(add.getAttribute('popovertarget')).toBe('schedule-form')
  fireEvent.click(add)
  expect(options('Automation')).toEqual(['Nightly']) // no workflow, nothing already scheduled
  expect(options('Repeat')).toEqual(['Hourly', 'Daily at', 'Weekly on … at', 'Custom cron'])
  expect(options('Account')).toEqual(['Auto', 'a@x', 'b@y'])
  expect(inForm().getByRole('combobox', { name: 'Account', hidden: true }).value).toBe('')

  /** Create, then wait until it has posted and the list has reloaded (the button is disabled meanwhile). */
  const create = async () => {
    const [posts, gets] = [calls(fetch, 'POST', LIST).length, calls(fetch, 'GET', LIST).length]
    submit()
    await waitFor(() => expect(calls(fetch, 'POST', LIST)).toHaveLength(posts + 1))
    await waitFor(() => expect(calls(fetch, 'GET', LIST).length).toBeGreaterThan(gets)) // on 201 the list reloads
    await waitFor(() => expect(inForm().getByRole('button', { name: 'Create', hidden: true }).disabled).toBe(false))
  }
  pick('Repeat', 'hourly')
  expect(timeInput()).toBeNull()
  await create()
  pick('Repeat', 'daily')
  expect(timeInput().value).toBe('09:00')
  await create()
  pick('Repeat', 'weekly')
  expect(options('Weekday')).toEqual(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])
  fireEvent.change(timeInput(), { target: { value: '07:30' } })
  pick('Weekday', '0')
  pick('Account', '2')
  await create()
  pick('Repeat', 'custom')
  fireEvent.change(inForm().getByRole('textbox', { name: /^Cron/, hidden: true }), { target: { value: '*/15 9-17 * * 1-5' } })
  responses[`GET ${LIST}`] = [200, [AUDIT, COVERAGE, created]]
  await create()
  await waitFor(() => expect(rows()).toHaveLength(3))
  expect(sent(fetch, 'POST', LIST)).toEqual([
    { factory_id: 11, cron: '0 * * * *' },
    { factory_id: 11, cron: '0 9 * * *' },
    { factory_id: 11, cron: '30 7 * * 0', account_id: 2 },
    { factory_id: 11, cron: '*/15 9-17 * * 1-5', account_id: 2 },
  ])
})

test('104 AC26: Weekly on Monday at 09:00 is 0 9 * * 1; a refusal shows inside the form, which keeps its values', async () => {
  const { fetch } = await open(undefined, { [`POST ${LIST}`]: [422, { detail: 'cron 0 0 30 2 * never runs' }] })
  fireEvent.click(screen.getByRole('button', { name: '+ Schedule automation' }))
  pick('Repeat', 'weekly')
  submit()
  expect((await inForm().findByRole('alert', { hidden: true })).textContent).toBe('cron 0 0 30 2 * never runs')
  expect(sent(fetch, 'POST', LIST)).toEqual([{ factory_id: 11, cron: '0 9 * * 1' }])
  expect(inForm().getByRole('combobox', { name: 'Repeat', hidden: true }).value).toBe('weekly')
  expect(inForm().getByRole('combobox', { name: 'Weekday', hidden: true }).value).toBe('1')
  expect(screen.queryAllByRole('alert').filter((a) => !form().contains(a))).toEqual([])
})

test('104 AC26: with every automation scheduled the button is disabled and says why', async () => {
  const all = [AUDIT, COVERAGE, { ...COVERAGE, id: 6, factory_id: 11, automation: 'Nightly' }]
  await open([200, all])
  const add = screen.getByRole('button', { name: '+ Schedule automation' })
  expect([add.disabled, add.title]).toEqual([true, 'Every automation has a schedule'])
})

test('104 AC27: Edit opens the form with the automation fixed and the preset from the cron; Save sends PATCH', async () => {
  const { fetch } = await open(undefined, {
    'PATCH /api/schedules/4': [200, AUDIT],
    'PATCH /api/schedules/5': [200, COVERAGE],
  })
  const edit = screen.getByRole('button', { name: 'Edit schedule of Security audit' })
  expect(edit.getAttribute('popovertarget')).toBe('schedule-form')
  fireEvent.click(edit)
  const automation = inForm().getByRole('combobox', { name: 'Automation', hidden: true })
  expect([automation.disabled, automation.textContent]).toEqual([true, 'Security audit'])
  expect(inForm().getByRole('combobox', { name: 'Repeat', hidden: true }).value).toBe('weekly')
  expect(inForm().getByRole('combobox', { name: 'Weekday', hidden: true }).value).toBe('1')
  expect(timeInput().value).toBe('09:00')
  fireEvent.change(timeInput(), { target: { value: '10:15' } })
  pick('Account', '1')
  submit('Save')
  await waitFor(() => expect(sent(fetch, 'PATCH', '/api/schedules/4')).toEqual([{ cron: '15 10 * * 1', account_id: 1 }]))

  fireEvent.click(screen.getByRole('button', { name: 'Edit schedule of Test coverage' }))
  expect(inForm().getByRole('combobox', { name: 'Repeat', hidden: true }).value).toBe('custom')
  expect(inForm().getByRole('textbox', { name: /^Cron/, hidden: true }).value).toBe('*/15 9-17 * * 1-5')
  expect(inForm().getByRole('combobox', { name: 'Account', hidden: true }).value).toBe('2')
  pick('Account', '')
  submit('Save')
  await waitFor(() =>
    expect(sent(fetch, 'PATCH', '/api/schedules/5')).toEqual([{ cron: '*/15 9-17 * * 1-5', account_id: null }]),
  )
})

test('104 AC27: Hourly and Daily crons open as their presets, other shapes as Custom', async () => {
  const of = (id, cron) => ({ ...COVERAGE, id, factory_id: id, automation: `a${id}`, cron })
  await open([200, [of(20, '0 * * * *'), of(21, '30 7 * * *'), of(22, '5 * * * *'), of(23, '0 9 * * 7')]])
  const repeatOf = (name) => {
    fireEvent.click(screen.getByRole('button', { name: `Edit schedule of ${name}` }))
    return [inForm().getByRole('combobox', { name: 'Repeat', hidden: true }).value, timeInput()?.value ?? null]
  }
  expect(repeatOf('a20')).toEqual(['hourly', null])
  expect(repeatOf('a21')).toEqual(['daily', '07:30'])
  expect(repeatOf('a22')).toEqual(['custom', null]) // Hourly has no minute field
  expect(repeatOf('a23')).toEqual(['weekly', '09:00'])
  expect(inForm().getByRole('combobox', { name: 'Weekday', hidden: true }).value).toBe('0') // 7 reads Sunday
})

test('104 AC28: Delete opens the shared dialog; DELETE, then the list reloads', async () => {
  const { fetch, responses } = await open(undefined, { 'DELETE /api/schedules/4': [204] })
  fireEvent.click(screen.getByRole('button', { name: 'Delete schedule of Security audit' }))
  const dialog = screen.getByRole('dialog', { name: 'Delete schedule of Security audit?' })
  expect(within(dialog).getByText('This removes the schedule. The automation and its runs stay.')).toBeTruthy()
  responses[`GET ${LIST}`] = [200, [COVERAGE]]
  fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
  await waitFor(() => expect(rows()).toHaveLength(1))
  expect(calls(fetch, 'DELETE', '/api/schedules/4')).toHaveLength(1)
  expect(screen.queryByRole('dialog')).toBeNull()
})

test('104 AC29: no schedules reads so; with no automations it also points at Workflows', async () => {
  const view = await open([200, []])
  expect(screen.getByText('No scheduled automations.')).toBeTruthy()
  expect(screen.queryByText(fullText('Create an automation on Workflows first.'))).toBeNull()
  view.unmount()
  await open([200, []], { [`GET ${FACTORIES}`]: [200, [factory(7, 'default', 'workflow')]] })
  expect(screen.getByText('No scheduled automations.')).toBeTruthy()
  const hint = screen.getByText(fullText('Create an automation on Workflows first.'))
  expect(within(hint).getByRole('link', { name: 'Workflows' }).getAttribute('href')).toBe('/projects/3/factories')
  const add = screen.getByRole('button', { name: '+ Schedule automation' })
  expect(add.disabled).toBe(true)
})

test('104 AC30: the skeleton first, the alert on a failed first load, then a 3 s poll with the offline banner', async () => {
  vi.useFakeTimers({ now: new Date('2026-10-20T12:00:00+09:00') })
  vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
  const pending = renderAt('/projects/3/scheduler')
  expectSkeleton(screen.getByRole('status'))
  pending.unmount()

  const failing = mockFetch({
    [`GET ${BOARD}`]: [200, board()], [`GET ${FACTORIES}`]: [200, FACTORY_LIST],
    [`GET ${LIST}`]: [502, { detail: 'Backend unreachable at http://127.0.0.1:4545' }],
  })
  const failed = renderAt('/projects/3/scheduler')
  await act(() => vi.advanceTimersByTimeAsync(0))
  expect(screen.getByRole('alert').textContent).toBe('Backend unreachable at http://127.0.0.1:4545')
  expect(failing).toHaveBeenCalled()
  failed.unmount()

  const responses = {
    [`GET ${BOARD}`]: [200, board()], [`GET ${FACTORIES}`]: [200, FACTORY_LIST], [`GET ${LIST}`]: [200, [AUDIT]],
  }
  const fetch = mockFetch(responses)
  renderAt('/projects/3/scheduler')
  await act(() => vi.advanceTimersByTimeAsync(0))
  expect(screen.getByRole('heading', { level: 1, name: 'Scheduler' })).toBeTruthy()
  const count = (url) => fetched(fetch).filter((u) => u === url).length
  await act(() => vi.advanceTimersByTimeAsync(3000))
  await act(() => vi.advanceTimersByTimeAsync(3000))
  expect([count(LIST), count(BOARD), count(FACTORIES)]).toEqual([3, 1, 1])
  await expectOfflineBanner(responses, `GET ${LIST}`, () => expect(rows()).toHaveLength(1))
})
