import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { expectOfflineBanner, fetched, fullText, mockFetch, renderAt } from '../../test/render.jsx'

const PAGE = '/api/pages/tasks/12'
const LOG = (id, after) => `/api/runs/${id}/log?after=${after}`
const HINT = "factory isn't committed on main: Create factory on the project board, then commit it on main"
const ACTIVE = [409, { detail: 'run #41 active' }]
const WORKTREE = '/Users/me/api/.claude/worktrees/12-rate-limit-login'
const PENDING = { security: 'pending', ux: 'pending', ui: 'pending', code: 'pending' }

/** 020's PageTask, with 047's workspace: the spec's fixture task. */
const TASK = {
  id: 12, project_id: 3, project: 'api', workspace_id: 2, workspace: 'personal', title: 'Rate-limit login', status: 'in_progress', stage: 'build',
  branch: 'factory/12-rate-limit-login', worktree_path: WORKTREE,
  description_md: '', description_html: '', spec_md: null, spec_html: '',
}
/** 020's TaskPage view-model, with 094's links; `task` overrides fields of the fixture task. */
const taskPage = (task = {}, extra = {}) => ({
  task: { ...TASK, ...task }, can_run: true, hint: null, run: null, takeover: null, rounds: [], approver: null,
  history: [], transcripts: [], blocked_by: [], blocks: [], project_tasks: [], ...extra,
})
/** RunDetail. */
const run = (id, status, extra = {}) => ({
  id, status, error: null, session_id: `session-${id}`, started_at: '2026-10-18T01:02:00Z', ...extra,
})
/** TaskRound. */
const round = (n, extra = {}) => ({
  n, trigger: 'initial', files: 2, additions: 10, deletions: 1, verdicts: PENDING, posted: {},
  build_md: null, build_html: '', ...extra,
})
/** LogOut. */
const log = (next, ...texts) => [200, { next, lines: texts.map((text) => ({ t: 'text', text })) }]

beforeEach(() => {
  vi.stubEnv('TZ', 'Asia/Tokyo') // UTC+9, as in the board tests
})
afterEach(() => {
  vi.useRealTimers()
})

/** Renders /tasks/12 with `page` as its view-model; mutate `responses` to change later replies. */
async function open(page, more = {}) {
  const responses = { [`GET ${PAGE}`]: [200, page], ...more }
  const fetch = mockFetch(responses)
  const view = renderAt('/tasks/12')
  await screen.findByRole('heading', { level: 1 })
  return { fetch, responses, ...view }
}

/** Renders /tasks/12 under fake timers and lets the first load and log fetch settle. */
async function openFake(responses) {
  vi.useFakeTimers()
  const fetch = mockFetch(responses)
  renderAt('/tasks/12')
  await advance(0)
  return fetch
}

const advance = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))
const loads = (fetch) => fetched(fetch).filter((url) => url === PAGE).length
const logs = (fetch) => fetched(fetch).filter((url) => url.startsWith('/api/runs/'))
const header = () => document.querySelector('main header')
const titleRow = () => screen.getByRole('heading', { level: 1 }).parentElement
const statusLine = () => within(header()).getByText('Review', { selector: 'a' }).parentElement
const section = (name) => screen.getByRole('region', { name })
const rows = () => [...section('Rounds').querySelectorAll('ol > li')]
const runButtons = () => within(titleRow()).queryAllByRole('button').map((b) => b.textContent) // 047 FE6: the title row's
const runStatus = () => within(header()).queryByText(/^run #/)
const panel = () => screen.queryByText(/^Run log · run #/)?.closest('details') ?? null
const logLines = () => [...panel().querySelector('summary + div').children].map((el) => el.textContent)
const sends = (fetch, method, url) => fetch.mock.calls.filter(([u, init]) => u === url && init?.method === method)

/** The one `method url` call: asserts its X-Requested-By. */
function sent(fetch, method, url) {
  const calls = sends(fetch, method, url)
  expect(calls).toHaveLength(1)
  expect(calls[0][1].headers['X-Requested-By']).toBe('fctl')
}

/** Clicks `label`, then expects `method url` to have gone out before the page's second load. */
async function clickAndReload(fetch, label, method, url) {
  fireEvent.click(within(header()).getByRole('button', { name: label }))
  await waitFor(() => expect(loads(fetch)).toBe(2))
  sent(fetch, method, url)
  const urls = fetched(fetch)
  expect(urls.indexOf(url)).toBeLessThan(urls.lastIndexOf(PAGE))
}

// --- Page and header -------------------------------------------------------------------

test('AC1, 047 FE2: /tasks/12 shows the title, the breadcrumb personal › api › #12, the Review link, and the page title', async () => {
  const { fetch } = await open(taskPage())
  expect(fetched(fetch)).toContain(PAGE)
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('#12 Rate-limit login')
  const crumbs = screen.getByRole('navigation', { name: 'Breadcrumb' })
  expect(crumbs.closest('header')).toBe(header())
  expect(crumbs.textContent).toBe('personal › api › #12')
  expect(within(crumbs).getAllByRole('link').map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
    ['personal', '/workspaces/2'], ['api', '/projects/3'],
  ])
  const current = within(crumbs).getByText('#12')
  expect([current.getAttribute('aria-current'), current.closest('a')]).toEqual(['page', null])
  expect(within(header()).getByRole('link', { name: 'Review' }).getAttribute('href')).toBe('/tasks/12/review')
  await waitFor(() => expect(document.title).toBe('#12 Rate-limit login · Claude Factories'))
})

const cls = (name) => new RegExp(`(^|\\s)${name}(\\s|$)`)

test('AC2, 043 FE10: the header shows the status pill, then the stage as its pill or muted text; only escalated is red; no running badge', async () => {
  const cases = [
    ['in_progress', 'build', 'In progress', 'text-accent', ['build', 'text-muted']],
    ['review', 'human_review', 'Review', 'text-warning', ['waiting on you', 'bg-warning']],
    ['review', 'escalated', 'Review', 'text-warning', ['escalated', 'bg-danger']],
    ['backlog', null, 'Backlog', 'text-muted', null],
    ['done', null, 'Done', 'text-success', null],
  ]
  for (const [status, stage, label, tone, after] of cases) {
    // Q4: a running run on the in_progress case, which still gets no ● running in the header
    const running = status === 'in_progress' ? { run: run(41, 'running') } : {}
    const { unmount } = await open(taskPage({ status, stage }, running), { [`GET ${LOG(41, 0)}`]: log(0) })
    const pill = within(header()).getByText(label, { selector: 'span' })
    expect(pill.className).toMatch(cls(tone))
    const state = [...pill.parentElement.children]
    expect(state.map((el) => el.textContent)).toEqual(after ? [label, after[0]] : [label])
    if (after) expect(state[1].className).toMatch(cls(after[1]))
    expect(pill.parentElement.textContent).toBe(after ? `${label} ${after[0]}` : label)
    const red = [...document.querySelectorAll('main [class*="danger"]')]
    expect(red.map((el) => el.textContent)).toEqual(stage === 'escalated' ? ['escalated'] : [])
    expect(header().textContent).not.toContain('●')
    unmount()
  }
})

test('AC3: the branch shows in a <code>; no branch and no run leave the header without one', async () => {
  const withBranch = await open(taskPage())
  expect(within(header()).getByText('factory/12-rate-limit-login').tagName).toBe('CODE')
  withBranch.unmount()
  await open(taskPage({ branch: null }))
  expect(header().querySelector('code')).toBeNull()
})

test('AC4: a title with markup shows as text and adds no script', async () => {
  await open(taskPage({ title: '<script>alert(1)</script>' }))
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('#12 <script>alert(1)</script>')
  expect(document.querySelector('main script')).toBeNull()
})

// --- Description and spec --------------------------------------------------------------

test('AC5: the description renders its HTML; a blank one says No description.', async () => {
  const withText = await open(taskPage({ description_md: 'Max **5**', description_html: '<p>Max <strong>5</strong></p>\n' }))
  expect(section('Description').querySelector('strong').textContent).toBe('5')
  withText.unmount()
  await open(taskPage())
  expect(within(section('Description')).getByText('No description.')).toBeTruthy()
})

test('AC6: the spec renders its HTML outside any <details>; null or blank says No spec yet.', async () => {
  const spec = await open(taskPage({ spec_md: '## Criteria\n\n- 429\n', spec_html: '<h2>Criteria</h2>\n<ul>\n<li>429</li>\n</ul>\n' }))
  const heading = within(section('Spec')).getByRole('heading', { level: 2, name: 'Criteria' })
  const item = within(section('Spec')).getByText('429')
  expect(item.tagName).toBe('LI')
  expect([heading.closest('details'), item.closest('details')]).toEqual([null, null])
  spec.unmount()
  for (const spec_md of [null, '  \n']) {
    const { unmount } = await open(taskPage({ spec_md }))
    expect(within(section('Spec')).getByText('No spec yet.')).toBeTruthy()
    unmount()
  }
})

// --- Rounds ----------------------------------------------------------------------------

test('AC7: rounds show in order as Round n trigger, four chips, and +A −D', async () => {
  await open(taskPage({}, {
    rounds: [
      round(1, { verdicts: { security: 'CHANGES', ux: 'PASS', ui: 'PASS', code: 'PASS' }, additions: 118, deletions: 9 }),
      round(2, { trigger: 'agent', verdicts: { security: 'PASS', ux: 'PASS', ui: 'PASS', code: 'PASS' }, additions: 126, deletions: 9 }),
    ],
  }))
  expect(rows().map((li) => li.querySelector('p').textContent)).toEqual([
    'Round 1 initial sec ✗ ux ✓ ui ✓ code ✓ +118 −9',
    'Round 2 agent sec ✓ ux ✓ ui ✓ code ✓ +126 −9',
  ])
  // 043 FE11: colored as in FE5
  const tones = [...rows()[0].querySelectorAll('[title]')].map((el) => ['text-success', 'text-danger'].find((c) => cls(c).test(el.className)))
  expect(tones).toEqual(['text-danger', 'text-success', 'text-success', 'text-success'])
})

test('AC8, 043 FE11: a verdict with a body is a red popover button whose popover holds the rendered body', async () => {
  const security = { verdict: 'CHANGES', body_md: 'Trusts **X-Forwarded-For**', body_html: '<p>Trusts <strong>X-Forwarded-For</strong></p>\n' }
  await open(taskPage({}, {
    rounds: [round(1, { verdicts: { ...PENDING, security: 'CHANGES' }, posted: { security } })],
  }))
  const chip = within(rows()[0]).getByRole('button', { name: 'sec ✗' })
  expect(chip.getAttribute('type')).toBe('button')
  expect(chip.getAttribute('popovertarget')).toBe('verdict-1-security')
  expect(chip.getAttribute('title')).toBe('security: CHANGES')
  expect(chip.className).toMatch(cls('text-danger'))
  const popover = document.getElementById('verdict-1-security')
  expect(popover.hasAttribute('popover')).toBe(true)
  expect(popover.textContent.startsWith('security · CHANGES')).toBe(true)
  expect(within(popover).getByText('X-Forwarded-For').tagName).toBe('STRONG')
})

test('AC9, 043 FE11: a pending chip, or a posted one with a blank body, is a colored span with a title and no popover', async () => {
  await open(taskPage({}, {
    rounds: [round(1, { verdicts: { ...PENDING, ux: 'PASS' }, posted: { ux: { verdict: 'PASS', body_md: '  \n', body_html: '' } } })],
  }))
  const row = rows()[0]
  for (const [text, title, id, tone] of [['ui ·', 'ui: pending', 'verdict-1-ui', 'text-muted'], ['ux ✓', 'ux: PASS', 'verdict-1-ux', 'text-success']]) {
    const chip = within(row).getByText(text)
    expect(chip.tagName).toBe('SPAN')
    expect(chip.className).toMatch(cls(tone))
    expect(chip.getAttribute('title')).toBe(title)
    expect(chip.hasAttribute('popovertarget')).toBe(false)
    expect(document.getElementById(id)).toBeNull()
  }
  expect(within(row).queryAllByRole('button')).toEqual([])
  expect([...document.querySelectorAll('[popover]')].map((el) => el.id)).toEqual(['export']) // 047: Export's alone
})

test('AC10: a standalone round with nothing posted says no agent review; a factory one shows four pending chips', async () => {
  const standalone = await open(taskPage({ worktree_path: null }, { rounds: [round(1)] }))
  expect(rows()[0].querySelector('p').textContent).toBe('Round 1 initial no agent review +10 −1')
  expect(rows()[0].querySelectorAll('[title]')).toHaveLength(0)
  standalone.unmount()
  await open(taskPage({}, { rounds: [round(1)] }))
  expect(rows()[0].querySelector('p').textContent).toBe('Round 1 initial sec · ux · ui · code · +10 −1')
  expect([...rows()[0].querySelectorAll('[title]')].map((el) => el.getAttribute('title'))).toEqual([
    'security: pending', 'ux: pending', 'ui: pending', 'code: pending',
  ])
})

test('AC11: build notes sit in one closed <details>; null or blank says No build notes.', async () => {
  const notes = await open(taskPage({}, {
    rounds: [round(1, { build_md: 'Token **bucket**', build_html: '<p>Token <strong>bucket</strong></p>\n' })],
  }))
  const details = rows()[0].querySelectorAll('details')
  expect(details).toHaveLength(1)
  expect(details[0].hasAttribute('open')).toBe(false)
  expect(details[0].querySelector('summary').textContent).toBe('Build notes')
  expect(within(details[0]).getByText('bucket').tagName).toBe('STRONG')
  notes.unmount()
  await open(taskPage({}, { rounds: [round(1), round(2, { build_md: ' \n' })] }))
  for (const li of rows()) {
    expect(within(li).getByText('No build notes.')).toBeTruthy()
    expect(li.querySelector('details')).toBeNull()
  }
})

test('AC12: no rounds says No rounds yet.', async () => {
  await open(taskPage())
  expect(within(section('Rounds')).getByText('No rounds yet.')).toBeTruthy()
})

// --- Approver and history --------------------------------------------------------------

test("AC13: the approver's decision shows with its round and rendered body; null shows none", async () => {
  const approved = await open(taskPage({}, {
    approver: { decision: 'APPROVE', n: 2, body_md: 'All **4** PASS', body_html: '<p>All <strong>4</strong> PASS</p>\n' },
  }))
  const block = screen.getByRole('region', { name: 'Approver' })
  expect(block.textContent.startsWith('Approver · APPROVE')).toBe(true)
  expect(block.textContent).toContain('round 2')
  expect(within(block).getByText('4').tagName).toBe('STRONG')
  approved.unmount()
  await open(taskPage())
  expect(screen.queryByText(/Approver ·/)).toBeNull()
})

test('AC14, 046 FE4: the status history is an ordered list of relative times, each with its local time as title, and labels', async () => {
  vi.setSystemTime(new Date('2026-10-18T01:07:00Z'))
  await open(taskPage({}, {
    history: [
      { created_at: '2026-10-18T01:02:00Z', label: 'created · backlog' },
      { created_at: '2026-10-18T01:05:00Z', label: 'in_progress · build' },
    ],
  }))
  const items = [...section('Status history').querySelectorAll('ol > li')]
  expect(items.map((li) => li.textContent)).toEqual(['5m ago created · backlog', '2m ago in_progress · build'])
  expect(items.map((li) => li.querySelector('time').getAttribute('datetime'))).toEqual([
    '2026-10-18T01:02:00Z', '2026-10-18T01:05:00Z',
  ])
  expect(items.map((li) => li.querySelector('time').getAttribute('title'))).toEqual(['2026-10-18 10:02', '2026-10-18 10:05'])
})

test('046 FE5: relative times refresh with the 3 s polls and no timer of their own', async () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-18T01:07:01Z')) // the entry is 5m 1s old
  const fetch = mockFetch({
    [`GET ${PAGE}`]: [200, taskPage({}, { history: [{ created_at: '2026-10-18T01:02:00Z', label: 'created · backlog' }] })],
  })
  renderAt('/tasks/12')
  await advance(0)
  const entry = () => section('Status history').querySelector('li').textContent
  expect(entry()).toBe('5m ago created · backlog')
  // act renders at its end, so step to the last poll before the minute turns (57 s), then past the turn (59 s) to
  // just before the next poll (60 s): nothing but a poll renders the text again
  await advance(57_000)
  await advance(2_500)
  expect(entry()).toBe('5m ago created · backlog')
  await advance(500)
  expect(loads(fetch)).toBe(21)
  expect(entry()).toBe('6m ago created · backlog')
})

// --- Run controls ----------------------------------------------------------------------

test('AC15: a backlog task without a run has only Run, which posts and reloads', async () => {
  const { fetch } = await open(taskPage({ status: 'backlog', stage: null, branch: null }), {
    'POST /api/tasks/12/run': [200, { run_id: 41, session_id: 'session-41', worktree: WORKTREE }],
  })
  expect(runButtons()).toEqual(['Run'])
  expect(runStatus()).toBeNull()
  expect(panel()).toBeNull()
  expect(screen.queryByText(/Take over|to take over/)).toBeNull()
  await clickAndReload(fetch, 'Run', 'POST', '/api/tasks/12/run')
})

test('AC16, 046 FE3: a running run shows Stop and how long ago it started; Stop posts and reloads', async () => {
  vi.setSystemTime(new Date('2026-10-18T01:07:00Z'))
  const { fetch } = await open(taskPage({}, { run: run(41, 'running') }), {
    'POST /api/runs/41/stop': [200, { id: 41, status: 'stopped' }],
    [`GET ${LOG(41, 0)}`]: log(0),
  })
  expect(runButtons()).toEqual(['Stop'])
  expect(within(header()).getByText(fullText('run #41 running · started 5m ago'))).toBeTruthy()
  expect(runStatus().querySelector('time').getAttribute('datetime')).toBe('2026-10-18T01:02:00Z')
  expect(runStatus().querySelector('time').getAttribute('title')).toBe('2026-10-18 10:02')
  await clickAndReload(fetch, 'Stop', 'POST', '/api/runs/41/stop')
})

test('AC17: an ended run on an in_progress task shows Retry and how it ended; Retry posts and reloads', async () => {
  const cases = [
    [{ status: 'failed', error: 'exit code 3' }, 'run #41 failed: exit code 3'],
    [{ status: 'stopped' }, 'run #41 stopped'],
    [{ status: 'succeeded' }, 'run #41 succeeded'],
    [{ status: 'failed', error: null }, 'run #41 failed'],
  ]
  for (const [{ status, ...extra }, text] of cases) {
    const { unmount } = await open(taskPage({}, { run: run(41, status, extra) }))
    expect(runButtons()).toEqual(['Retry'])
    expect(runStatus().textContent).toBe(text)
    unmount()
  }
  const { fetch } = await open(taskPage({}, { run: run(41, 'failed', { error: 'exit code 3' }) }), {
    'POST /api/tasks/12/run': [200, { run_id: 42, session_id: 'session-42', worktree: WORKTREE }],
  })
  await clickAndReload(fetch, 'Retry', 'POST', '/api/tasks/12/run')
})

test('AC18: review and done tasks get no Run or Retry, a running run gets Stop, in_progress without a run gets nothing', async () => {
  for (const [status, stage] of [['review', 'human_review'], ['done', null]]) {
    const { unmount } = await open(taskPage({ status, stage }, { run: run(41, 'succeeded') }))
    expect(runButtons()).toEqual([])
    expect(runStatus().textContent).toBe('run #41 succeeded')
    unmount()
  }
  const review = await open(taskPage({ status: 'review', stage: 'agent_review' }, { run: run(41, 'running') }))
  expect(runButtons()).toEqual(['Stop'])
  review.unmount()
  await open(taskPage())
  expect(runButtons()).toEqual([])
  expect(runStatus()).toBeNull()
})

test('AC19: can_run disables Run and Retry but not Stop; the hint shows beside Run or Retry only', async () => {
  const cases = [
    [{ status: 'backlog', stage: null }, null, 'Run', true],
    [{}, run(41, 'failed'), 'Retry', true],
    [{}, run(41, 'running'), 'Stop', false],
  ]
  for (const [task, latest, label, disabled] of cases) {
    const { unmount } = await open(taskPage(task, { run: latest, can_run: false, hint: HINT }))
    const button = within(header()).getByRole('button', { name: label })
    expect(button.disabled).toBe(disabled)
    const hint = within(header()).queryByText(HINT)
    expect(hint?.parentElement ?? null).toBe(label === 'Stop' ? null : button.parentElement)
    unmount()
  }
  const review = await open(taskPage({ status: 'review', stage: 'human_review' }, { run: run(41, 'succeeded'), can_run: false, hint: HINT }))
  expect(screen.queryByText(HINT)).toBeNull()
  review.unmount()
  await open(taskPage({ status: 'backlog', stage: null }))
  expect(within(header()).getByRole('button', { name: 'Run' }).disabled).toBe(false)
  expect(screen.queryByText(/factory isn't committed/)).toBeNull()
})

test('AC20: a refused Run, Retry, or Stop shows its detail in the header alert; the next success clears it', async () => {
  const cases = [
    [{ status: 'backlog', stage: null }, null, 'Run', '/api/tasks/12/run'],
    [{}, run(41, 'failed'), 'Retry', '/api/tasks/12/run'],
    [{}, run(41, 'running'), 'Stop', '/api/runs/41/stop'],
  ]
  for (const [task, latest, label, url] of cases) {
    const { fetch, responses, unmount } = await open(taskPage(task, { run: latest }), { [`POST ${url}`]: ACTIVE })
    fireEvent.click(within(header()).getByRole('button', { name: label }))
    const alert = await within(header()).findByRole('alert')
    expect(alert.textContent).toBe('run #41 active')
    expect(sends(fetch, 'POST', url)[0][1].headers['X-Requested-By']).toBe('fctl')
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('#12 Rate-limit login')
    expect(loads(fetch)).toBe(1)

    responses[`POST ${url}`] = [200, {}]
    await waitFor(() => expect(within(header()).getByRole('button', { name: label }).disabled).toBe(false))
    fireEvent.click(within(header()).getByRole('button', { name: label }))
    await waitFor(() => expect(loads(fetch)).toBe(2))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(sends(fetch, 'POST', url).map(([, init]) => init.headers['X-Requested-By'])).toEqual(['fctl', 'fctl'])
    unmount()
  }
})

// --- Takeover --------------------------------------------------------------------------

test('AC21: the takeover command shows in a <code>; a running run says to stop it first; otherwise neither', async () => {
  const takeover = `cd ${WORKTREE} && claude --resume session-41`
  const ended = await open(taskPage({}, { run: run(41, 'stopped'), takeover }))
  expect(within(header()).getByText(fullText(`Take over in terminal: ${takeover}`))).toBeTruthy()
  expect(within(header()).getByText(takeover).tagName).toBe('CODE')
  ended.unmount()

  const running = await open(taskPage({}, { run: run(41, 'running') }))
  expect(within(header()).getByText('Stop the run to take over.')).toBeTruthy()
  expect(screen.queryByText(/Take over in terminal/)).toBeNull()
  running.unmount()

  for (const [task, latest] of [[{}, null], [{ worktree_path: null }, run(41, 'running')], [{ worktree_path: null }, run(41, 'stopped')]]) {
    const { unmount } = await open(taskPage(task, { run: latest }))
    expect(screen.queryByText(/Take over in terminal|Stop the run to take over/)).toBeNull()
    unmount()
  }
})

// --- Run log ---------------------------------------------------------------------------

test('AC22: a run has a closed Run log panel that says No output yet.; no run, no panel', async () => {
  const withRun = await open(taskPage({}, { run: run(41, 'stopped') }), { [`GET ${LOG(41, 0)}`]: log(0) })
  await waitFor(() => expect(logs(withRun.fetch)).toEqual([LOG(41, 0)]))
  expect(panel().querySelector('summary').textContent).toBe('Run log · run #41')
  expect(panel().hasAttribute('open')).toBe(false)
  expect(within(panel()).getByText('No output yet.')).toBeTruthy()
  withRun.unmount()
  const { fetch } = await open(taskPage())
  expect(panel()).toBeNull()
  expect(logs(fetch)).toEqual([])
})

test('AC23: a running run tails its log from after=0, then from the cursor 3000 ms after each reply', async () => {
  const fetch = await openFake({
    [`GET ${PAGE}`]: [200, taskPage({}, { run: run(41, 'running') })],
    [`GET ${LOG(41, 0)}`]: [200, { next: 2, lines: [{ t: 'tool', text: 'builder-12 · Bash pytest -q' }, { t: 'text', text: '3 passed' }] }],
    [`GET ${LOG(41, 2)}`]: log(3, 'done'),
  })
  expect(logs(fetch)).toEqual([LOG(41, 0)])
  expect(logLines()).toEqual(['builder-12 · Bash pytest -q', '3 passed'])
  expect(screen.queryByText('No output yet.')).toBeNull()
  await advance(2999)
  expect(logs(fetch)).toEqual([LOG(41, 0)])
  await advance(1)
  expect(logs(fetch)).toEqual([LOG(41, 0), LOG(41, 2)])
  expect(logLines()).toEqual(['builder-12 · Bash pytest -q', '3 passed', 'done'])
})

test('AC24: an ended run fetches its log once', async () => {
  const fetch = await openFake({
    [`GET ${PAGE}`]: [200, taskPage({}, { run: run(41, 'stopped') })],
    [`GET ${LOG(41, 0)}`]: log(1, 'bye'),
  })
  expect(logs(fetch)).toEqual([LOG(41, 0)])
  await advance(30000)
  expect(loads(fetch)).toBeGreaterThan(5)
  expect(logs(fetch)).toEqual([LOG(41, 0)])
  expect(logLines()).toEqual(['bye'])
})

test('AC25: a run that stops gets one more log fetch from its cursor, then none; each line shows once', async () => {
  const responses = {
    [`GET ${PAGE}`]: [200, taskPage({}, { run: run(41, 'running') })],
    [`GET ${LOG(41, 0)}`]: log(2, 'a', 'b'),
    [`GET ${LOG(41, 2)}`]: log(3, 'c'),
    [`GET ${LOG(41, 3)}`]: log(3),
  }
  vi.useFakeTimers()
  const reply = mockFetch(responses)
  // the 3 s log poll's reply lands 100 ms late, so the final fetch the stop triggers overlaps it
  const fetch = vi.fn(async (url, init) => {
    if (url === LOG(41, 2)) await new Promise((resolve) => setTimeout(resolve, 100))
    return reply(url, init)
  })
  vi.stubGlobal('fetch', fetch)
  renderAt('/tasks/12')
  await advance(0)
  expect(logLines()).toEqual(['a', 'b'])
  responses[`GET ${PAGE}`] = [200, taskPage({}, { run: run(41, 'stopped') })]
  await advance(3000)
  expect(runStatus().textContent).toBe('run #41 stopped')
  expect(logs(fetch)).toEqual([LOG(41, 0), LOG(41, 2), LOG(41, 2)]) // the poll, then the final fetch from the cursor
  await advance(30000)
  expect(logs(fetch)).toEqual([LOG(41, 0), LOG(41, 2), LOG(41, 2)])
  expect(logLines()).toEqual(['a', 'b', 'c'])
})

test('AC26: a poll that brings a new run swaps in a fresh log panel for it', async () => {
  const responses = {
    [`GET ${PAGE}`]: [200, taskPage({}, { run: run(41, 'failed') })],
    [`GET ${LOG(41, 0)}`]: log(1, 'old line'),
    [`GET ${LOG(42, 0)}`]: log(1, 'new line'),
  }
  const fetch = await openFake(responses)
  expect(logLines()).toEqual(['old line'])
  responses[`GET ${PAGE}`] = [200, taskPage({}, { run: run(42, 'running') })]
  await advance(3000)
  expect(panel().querySelector('summary').textContent).toBe('Run log · run #42')
  expect(logs(fetch)).toEqual([LOG(41, 0), LOG(42, 0)])
  expect(logLines()).toEqual(['new line'])
  expect(screen.queryByText('old line')).toBeNull()
})

test('AC27: a log line and a run error with markup show as text and add no elements', async () => {
  await open(taskPage({}, { run: run(41, 'failed', { error: '<script>alert(1)</script>' }) }), {
    [`GET ${LOG(41, 0)}`]: log(1, '<img src=x onerror=alert(1)>'),
  })
  expect(await within(panel()).findByText('<img src=x onerror=alert(1)>')).toBeTruthy()
  expect(runStatus().textContent).toBe('run #41 failed: <script>alert(1)</script>')
  expect(document.querySelector('main img, main script')).toBeNull()
})

// --- Polling and states ----------------------------------------------------------------

test('AC28: the page reloads 3000 ms after the last load settles and shows the new view-model', async () => {
  const responses = { [`GET ${PAGE}`]: [200, taskPage()] }
  const fetch = await openFake(responses)
  expect(within(header()).getByText(fullText('In progress build'))).toBeTruthy()
  responses[`GET ${PAGE}`] = [200, taskPage({ stage: 'agent_review' })]
  await advance(2999)
  expect(loads(fetch)).toBe(1)
  await advance(1)
  expect(loads(fetch)).toBe(2)
  expect(within(header()).getByText(fullText('In progress agent_review'))).toBeTruthy()
})

test('AC29: build notes opened with a click stay open across a poll', async () => {
  const security = { verdict: 'CHANGES', body_md: 'Trusts **X-Forwarded-For**', body_html: '<p>Trusts <strong>X-Forwarded-For</strong></p>\n' }
  const page = taskPage({}, {
    rounds: [round(1, { posted: { security }, build_md: 'Token **bucket**', build_html: '<p>Token <strong>bucket</strong></p>\n' })],
  })
  const fetch = await openFake({ [`GET ${PAGE}`]: [200, page] })
  const details = rows()[0].querySelector('details')
  const popover = document.getElementById('verdict-1-security')
  fireEvent.click(details.querySelector('summary'))
  expect(details.open).toBe(true)
  await advance(3000)
  expect(loads(fetch)).toBe(2)
  expect(rows()[0].querySelector('details')).toBe(details)
  expect(details.open).toBe(true)
  expect(document.getElementById('verdict-1-security')).toBe(popover)
})

test("AC30: the API's 404 shows the not-found state with its detail and a link home", async () => {
  mockFetch({ 'GET /api/pages/tasks/99': [404, { detail: 'Task #99 not found' }] })
  renderAt('/tasks/99')
  expect(await screen.findByRole('heading', { name: 'Task #99 not found' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Go to the dashboard' }).getAttribute('href')).toBe('/')
})

test('AC31, 046 FE10, FE12, FE13: a failed first load shows only the alert; a failed poll over the page shows the offline banner until the next success', async () => {
  mockFetch({ [`GET ${PAGE}`]: [500, { detail: 'boom' }] })
  const first = renderAt('/tasks/12')
  expect((await screen.findByRole('alert')).textContent).toBe('boom')
  expect(screen.queryByRole('heading', { level: 1 })).toBeNull()
  first.unmount()

  const responses = { [`GET ${PAGE}`]: [200, taskPage()] }
  await openFake(responses)
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('#12 Rate-limit login')
  await expectOfflineBanner(responses, `GET ${PAGE}`, () => {
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('#12 Rate-limit login')
  })
})

// --- 030: Agents ------------------------------------------------------------------------

/** 030's TranscriptOut. */
const transcript = (id, round, extra = {}) => ({
  id, run_id: 41, round, agent_type: 'builder', name: `builder-${id}`, model: 'claude-opus-4-1', turns: 38,
  input_tokens: 1234, cache_read_tokens: 56789, output_tokens: 2345,
  started_at: '2026-10-17T10:00:00Z', ended_at: '2026-10-17T10:04:12Z', ...extra,
})
const agentRows = (list) => [...list.querySelectorAll('li')]

test('030 AC23: each round lists its agents: label linking to the transcript, model, turns, tokens, duration', async () => {
  const transcripts = [
    transcript(5, 1),
    transcript(6, 2, { name: null, agent_type: 'review-code', started_at: '2026-10-17T09:00:00Z', ended_at: '2026-10-17T10:02:30Z' }),
    transcript(7, 2, { name: null, agent_type: null, model: null, ended_at: '2026-10-17T10:00:12Z' }),
    transcript(8, 1, { ended_at: null }),
  ]
  await open(taskPage({}, { rounds: [round(1), round(2)], transcripts }))
  const [one, two] = rows()
  const first = within(one).getByRole('list', { name: 'Round 1 agents' })
  expect(agentRows(first).map((li) => li.textContent)).toEqual([
    'builder-5 · claude-opus-4-1 · 38 turns · in 1,234 · cache 56,789 · out 2,345 · 4m 12s',
    'builder-8 · claude-opus-4-1 · 38 turns · in 1,234 · cache 56,789 · out 2,345 · —',
  ])
  expect(within(first).getByRole('link', { name: 'builder-5' }).getAttribute('href')).toBe('/transcripts/5')
  const second = within(two).getByRole('list', { name: 'Round 2 agents' })
  expect(agentRows(second).map((li) => li.textContent)).toEqual([
    'review-code · claude-opus-4-1 · 38 turns · in 1,234 · cache 56,789 · out 2,345 · 1h 2m',
    'agent · unknown model · 38 turns · in 1,234 · cache 56,789 · out 2,345 · 12s',
  ])
  expect(within(second).getByRole('link', { name: 'agent' }).getAttribute('href')).toBe('/transcripts/7')
  expect(screen.queryByRole('region', { name: 'Other agents' })).toBeNull()
})

test('030 AC24: null-round transcripts list under Other agents after Rounds with their run; none, no lists', async () => {
  const transcripts = [
    transcript(5, null, { name: null, agent_type: 'orchestrator', run_id: 40 }),
    transcript(6, 1),
    transcript(7, null, { name: null, agent_type: 'spec-writer', run_id: 41 }),
  ]
  const view = await open(taskPage({}, { rounds: [round(1)], transcripts }))
  const other = section('Other agents')
  expect(within(other).getByRole('heading', { level: 2 }).textContent).toBe('Other agents')
  expect(agentRows(other).map((li) => li.textContent)).toEqual([
    'orchestrator · run #40 · claude-opus-4-1 · 38 turns · in 1,234 · cache 56,789 · out 2,345 · 4m 12s',
    'spec-writer · run #41 · claude-opus-4-1 · 38 turns · in 1,234 · cache 56,789 · out 2,345 · 4m 12s',
  ])
  expect(within(other).getByRole('link', { name: 'orchestrator' }).getAttribute('href')).toBe('/transcripts/5')
  expect(section('Rounds').compareDocumentPosition(other) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(agentRows(within(rows()[0]).getByRole('list', { name: 'Round 1 agents' }))).toHaveLength(1)
  view.unmount()

  const none = await open(taskPage({}, { rounds: [round(1)], transcripts: [] }))
  expect(screen.queryByRole('region', { name: 'Other agents' })).toBeNull()
  expect(screen.queryByText('Other agents')).toBeNull()
  expect(screen.queryAllByRole('list', { name: /agents$/ })).toEqual([])
  expect(within(screen.getByRole('main')).queryByText('Agents')).toBeNull() // 053: the sidebar has an Agents link
  none.unmount()
})

test('030 Q4: a transcript whose round has no Round row yet shows under Other agents with its round', async () => {
  await open(taskPage({}, { rounds: [], transcripts: [transcript(5, 1)] }))
  expect(agentRows(section('Other agents')).map((li) => li.textContent)).toEqual([
    'builder-5 · run #41 · round 1 · claude-opus-4-1 · 38 turns · in 1,234 · cache 56,789 · out 2,345 · 4m 12s',
  ])
})

// --- 047: the title row and Export ----------------------------------------------------

test('047 FE6: the title row holds Run, Retry, or Stop, the run status, and the hint; the status line holds none of them', async () => {
  vi.setSystemTime(new Date('2026-10-18T01:07:00Z')) // 046 FE3
  const cases = [
    [{ status: 'backlog', stage: null }, null, 'Run', null],
    [{}, run(41, 'failed', { error: 'exit code 3' }), 'Retry', 'run #41 failed: exit code 3'],
    [{}, run(41, 'running'), 'Stop', 'run #41 running · started 5m ago'],
  ]
  for (const [task, latest, label, status] of cases) {
    const { unmount } = await open(taskPage(task, { run: latest, can_run: false, hint: HINT }), { [`GET ${LOG(41, 0)}`]: log(0) })
    const row = titleRow()
    expect(row.firstElementChild).toBe(screen.getByRole('heading', { level: 1 }))
    expect(within(row).getByRole('button', { name: label })).toBeTruthy()
    if (status) expect(within(row).getByText(fullText(status))).toBeTruthy()
    if (label !== 'Stop') expect(within(row).getByText(HINT)).toBeTruthy()
    const line = statusLine()
    expect(line.contains(row) || row.contains(line)).toBe(false)
    expect(within(line).queryAllByRole('button').map((b) => b.textContent)).toEqual(['Export ▾'])
    expect(within(line).queryByText(/^run #/)).toBeNull()
    expect(within(line).queryByText(HINT)).toBeNull()
    unmount()
  }
})

test('047 FE7: the status line has the pill, stage, branch, Review, and an Export button opening a popover; no box or download', async () => {
  await open(taskPage())
  const line = statusLine()
  expect(within(line).getByText('In progress', { selector: 'span' })).toBeTruthy()
  expect(within(line).getByText('build')).toBeTruthy()
  expect(within(line).getByText('factory/12-rate-limit-login').tagName).toBe('CODE')
  const button = within(line).getByRole('button', { name: 'Export' })
  const target = document.getElementById(button.getAttribute('popovertarget'))
  expect(target.getAttribute('popover')).toBe('auto')
  expect(line.contains(target)).toBe(false)
  expect(line.querySelectorAll('input[type="checkbox"], a[download]')).toHaveLength(0)
})

test('047 FE8, 032 AC46: the Export popover holds Include transcripts and Download; ticking adds ?transcripts=1, unticking drops it', async () => {
  await open(taskPage())
  const popover = document.getElementById(within(header()).getByRole('button', { name: 'Export' }).getAttribute('popovertarget'))
  popover.style.display = 'grid' // jsdom's UA sheet hides it while closed
  const download = () => within(popover).getByRole('link', { name: 'Download' })
  expect(download().hasAttribute('download')).toBe(true)
  expect(download().getAttribute('href')).toBe('/api/tasks/12/export')
  const box = within(popover).getByRole('checkbox', { name: /^Include transcripts/ })
  expect(box.checked).toBe(false)
  expect(box.closest('label').textContent).toBe('Include transcripts (can hold paths, env, and secrets)')
  fireEvent.click(box)
  expect(download().getAttribute('href')).toBe('/api/tasks/12/export?transcripts=1')
  fireEvent.click(box)
  expect(download().getAttribute('href')).toBe('/api/tasks/12/export')
})

test('053 FE11 (Q7): at /tasks/12#run-log the run log <details id="run-log"> renders open and scrolls into view; at /tasks/12 closed', async () => {
  const scroll = vi.fn()
  Element.prototype.scrollIntoView = scroll // jsdom has none
  try {
    const responses = { [`GET ${PAGE}`]: [200, taskPage({}, { run: run(41, 'running') })], [`GET ${LOG(41, 0)}`]: log(0) }
    mockFetch(responses)
    const linked = renderAt('/tasks/12#run-log')
    await screen.findByRole('heading', { level: 1 })
    const details = document.getElementById('run-log')
    expect(details).toBe(panel())
    expect(details.open).toBe(true)
    expect(scroll).toHaveBeenCalledTimes(1)
    expect(scroll.mock.contexts[0]).toBe(details)
    linked.unmount()

    scroll.mockClear()
    await open(taskPage({}, { run: run(41, 'running') }), { [`GET ${LOG(41, 0)}`]: log(0) })
    expect(document.getElementById('run-log')).toBe(panel())
    expect(panel().open).toBe(false)
    expect(scroll).not.toHaveBeenCalled()
  } finally {
    delete Element.prototype.scrollIntoView
  }
})

// --- 094: Blocked by and Blocks -------------------------------------------------------

const dep = (id, title, status) => ({ id, title, status })
/** #12 waits on #9 (done) and #10 (backlog), and #15 waits on #12; the project also has #11 and #14. */
const LINKED = {
  blocked_by: [dep(9, 'Add Redis', 'done'), dep(10, 'Login form', 'backlog')],
  blocks: [dep(15, 'Lockout email', 'backlog')],
  project_tasks: [dep(9, 'Add Redis', 'done'), dep(10, 'Login form', 'backlog'), dep(11, 'Audit log', 'review'),
    dep(14, 'Captcha', 'in_progress'), dep(15, 'Lockout email', 'backlog')],
}
const select = () => within(section('Blocked by')).getByRole('combobox', { name: 'Wait on' })

test('094 AC25: Blocked by follows Description with a row per link (id link, title, status pill, Remove), then Blocks; or their empty texts', async () => {
  const linked = await open(taskPage({}, LINKED))
  const regions = screen.getAllByRole('region').map((el) => el.getAttribute('aria-labelledby')).filter((id) => id?.startsWith('task-'))
  expect(regions.slice(0, 4)).toEqual(['task-description', 'task-blocked-by', 'task-blocks', 'task-spec'])
  const rowsOf = [...section('Blocked by').querySelectorAll('li')]
  expect(rowsOf.map((li) => li.textContent)).toEqual(['#9Add RedisDoneRemove', '#10Login formBacklogRemove'])
  const first = within(rowsOf[0])
  expect(first.getByRole('link', { name: '#9' }).getAttribute('href')).toBe('/tasks/9')
  expect(first.getByText('Done').className).toMatch(cls('text-success')) // StatusPill
  expect(first.getByRole('button', { name: 'Remove #9' }).textContent).toBe('Remove')
  const blocks = within(section('Blocks'))
  expect(blocks.getByRole('link', { name: '#15' }).getAttribute('href')).toBe('/tasks/15')
  expect(blocks.getByRole('listitem').textContent).toBe('#15 Lockout email')
  expect(blocks.queryByRole('button')).toBeNull() // Q9: read-only
  linked.unmount()
  await open(taskPage())
  expect(within(section('Blocked by')).getByText('No blockers.')).toBeTruthy()
  expect(within(section('Blocks')).getByText('Blocks nothing.')).toBeTruthy()
})

test('094 AC26: Add picks from the project\'s other tasks minus the blockers, sends the PUT, and reloads; a refusal shows in the section and keeps the pick', async () => {
  const cycle = 'cycle: #12 waits on #15, which waits on #12'
  const { fetch, responses } = await open(taskPage({}, LINKED), {
    'PUT /api/tasks/12/blocked-by/15': [422, { detail: cycle }],
    'PUT /api/tasks/12/blocked-by/14': [200, { id: 12, blocked: true, blocked_by: [], blocks: [] }],
  })
  expect([...select().options].map((o) => [o.value, o.textContent])).toEqual([
    ['11', '#11 Audit log'], ['14', '#14 Captcha'], ['15', '#15 Lockout email']])
  const add = within(section('Blocked by')).getByRole('button', { name: 'Add' })
  fireEvent.change(select(), { target: { value: '15' } })
  fireEvent.click(add)
  expect((await within(section('Blocked by')).findByRole('alert')).textContent).toBe(cycle)
  expect(within(header()).queryByRole('alert')).toBeNull()
  expect(select().value).toBe('15')
  expect(loads(fetch)).toBe(1)
  sent(fetch, 'PUT', '/api/tasks/12/blocked-by/15')
  responses[`GET ${PAGE}`] = [200, taskPage({}, LINKED)]
  fireEvent.change(select(), { target: { value: '14' } })
  await waitFor(() => expect(add.disabled).toBe(false))
  fireEvent.click(add)
  await waitFor(() => expect(loads(fetch)).toBe(2))
  sent(fetch, 'PUT', '/api/tasks/12/blocked-by/14')
  expect(within(section('Blocked by')).queryByRole('alert')).toBeNull()
})

test('094 AC27: Remove sends the DELETE and reloads; a refusal shows in the section', async () => {
  const gone = '#12 is not blocked by #10'
  const { fetch, responses } = await open(taskPage({}, LINKED), {
    'DELETE /api/tasks/12/blocked-by/10': [404, { detail: gone }],
    'DELETE /api/tasks/12/blocked-by/9': [200, { id: 12, blocked: true, blocked_by: [], blocks: [] }],
  })
  fireEvent.click(within(section('Blocked by')).getByRole('button', { name: 'Remove #10' }))
  expect((await within(section('Blocked by')).findByRole('alert')).textContent).toBe(gone)
  expect(loads(fetch)).toBe(1)
  sent(fetch, 'DELETE', '/api/tasks/12/blocked-by/10')
  responses[`GET ${PAGE}`] = [200, taskPage({}, LINKED)]
  fireEvent.click(within(section('Blocked by')).getByRole('button', { name: 'Remove #9' }))
  await waitFor(() => expect(loads(fetch)).toBe(2))
  sent(fetch, 'DELETE', '/api/tasks/12/blocked-by/9')
  expect(within(section('Blocked by')).queryByRole('alert')).toBeNull()
})
