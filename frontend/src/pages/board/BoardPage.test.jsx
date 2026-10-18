import { act, createEvent, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { fetched, fullText, mockFetch, renderAt } from '../../test/render.jsx'

const PROJECT = { id: 3, name: 'api', path: '/Users/me/api', default_branch: 'main', workspace_id: 2, workspace: 'personal' }
const WORKSPACES = [{ id: 2, name: 'personal', projects: 1 }, { id: 4, name: 'work', projects: 0 }]
const BOARD = '/api/pages/projects/3'
const HINT = "factory isn't committed on main: Create factory on the project board, then commit it on main"
const ACTIVE = [409, { detail: 'run #41 active' }]

/** A Card as 020's dto/pages.py has it. */
const card = (id, status, extra = {}) => ({
  id, title: `Task ${id}`, status, stage: null, round: null, verdicts: null, additions: null, deletions: null,
  run: null, position: id, started_at: null, waiting: false, escalated: false, stalled: false, ...extra,
})
/** A BoardPage view-model; `columns` fills in the rest of the four. */
const board = (columns = {}, extra = {}) => ({
  project: PROJECT, factory: 'ready', hint: null, can_run: true, workspaces: WORKSPACES,
  columns: { backlog: [], in_progress: [], review: [], done: [], ...columns }, ...extra,
})

beforeEach(() => {
  vi.stubEnv('TZ', 'Asia/Tokyo') // UTC+9, as in the dashboard and workspace tests
})
afterEach(() => {
  vi.useRealTimers()
})

/** Renders /projects/3 with `page` as its view-model; mutate `responses` to change later replies. */
async function open(page, more = {}) {
  const responses = { [`GET ${BOARD}`]: [200, page], ...more }
  const fetch = mockFetch(responses)
  const view = renderAt('/projects/3')
  await screen.findByRole('heading', { level: 1 })
  return { fetch, responses, ...view }
}

const loads = (fetch) => fetched(fetch).filter((url) => url === BOARD).length
const header = () => document.querySelector('main header')
const cardEl = (id) => screen.getByRole('link', { name: new RegExp(`^#${id} `) }).closest('li')
const column = (label) => screen.getByRole('heading', { level: 2, name: new RegExp(`^${label} \\d+$`) }).closest('section')
const sends = (fetch, method, url) => fetch.mock.calls.filter(([u, init]) => u === url && init?.method === method)

/** The one `method url` call: asserts its X-Requested-By and returns its JSON body. */
function sent(fetch, method, url) {
  const calls = sends(fetch, method, url)
  expect(calls).toHaveLength(1)
  const [, init] = calls[0]
  expect(init.headers['X-Requested-By']).toBe('fctl')
  return init.body === undefined ? undefined : JSON.parse(init.body)
}

/** Q1: cards stacked 50 px apart from y=100, 40 px tall; midpoints at 120, 170, 220, … */
function stubRects() {
  for (const li of document.querySelectorAll('section li')) {
    const i = [...li.parentElement.children].indexOf(li)
    li.getBoundingClientRect = () => ({ top: 100 + 50 * i, height: 40, bottom: 140 + 50 * i, left: 0, right: 200, width: 200 })
  }
}

/** Drags card `id` onto the column headed `label` at `clientY`. */
function drag(id, label, clientY) {
  stubRects()
  const source = cardEl(id)
  const dataTransfer = { setData: vi.fn(), effectAllowed: 'all' }
  fireEvent.dragStart(source, { dataTransfer })
  expect(dataTransfer.setData).toHaveBeenCalledWith('text/plain', String(id))
  const target = column(label)
  fireEvent.dragOver(target)
  const drop = createEvent.drop(target)
  Object.defineProperty(drop, 'clientY', { value: clientY })
  fireEvent(target, drop)
  fireEvent.dragEnd(source)
}

// --- Page and header -------------------------------------------------------------------

test('AC1: /projects/3 shows the project, its workspace, path, title, and Code link', async () => {
  const { fetch } = await open(board())
  expect(fetched(fetch)).toContain(BOARD)
  const h1 = screen.getByRole('heading', { level: 1 })
  expect(h1.textContent).toBe('api · personal')
  expect(within(h1).getByRole('link', { name: 'personal' }).getAttribute('href')).toBe('/workspaces/2')
  expect(screen.getByText('/Users/me/api')).toBeTruthy()
  expect(document.title).toBe('api · Claude Factories')
  expect(screen.getByRole('link', { name: 'Code' }).getAttribute('href')).toBe('/projects/3/code')
})

test('AC2: ready shows Factory: ready ✓ and no form; uncommitted and none show the Create factory form', async () => {
  const ready = await open(board())
  expect(screen.getByText('Factory: ready ✓')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Create factory' })).toBeNull()
  expect(screen.queryByRole('checkbox', { name: 'Overwrite existing files' })).toBeNull()
  ready.unmount()
  for (const factory of ['uncommitted', 'none']) {
    const { unmount } = await open(board({}, { factory, can_run: false }))
    expect(screen.getByText(`Factory: ${factory}`)).toBeTruthy()
    expect(screen.getByRole('checkbox', { name: 'Overwrite existing files' }).checked).toBe(false)
    expect(screen.getByRole('button', { name: 'Create factory' })).toBeTruthy()
    unmount()
  }
})

test('AC3: a hint shows in the header; a null hint shows none', async () => {
  const withHint = await open(board({}, { factory: 'none', hint: HINT, can_run: false }))
  expect(within(header()).getByText(HINT)).toBeTruthy()
  withHint.unmount()
  await open(board())
  expect(screen.queryByText(/factory isn't committed/)).toBeNull()
})

test('AC4: can_run disables or enables Run next, every Run, and every Retry', async () => {
  const columns = {
    backlog: [card(1, 'backlog'), card(2, 'backlog')],
    in_progress: [card(3, 'in_progress', { stage: 'build', run: { id: 9, status: 'failed' }, stalled: true })],
  }
  for (const canRun of [false, true]) {
    const { unmount } = await open(board(columns, { can_run: canRun }))
    const buttons = [
      screen.getByRole('button', { name: 'Run next ▶' }),
      ...screen.getAllByRole('button', { name: 'Run' }),
      screen.getByRole('button', { name: 'Retry' }),
    ]
    expect(buttons).toHaveLength(4)
    expect(buttons.map((b) => b.disabled)).toEqual(Array(4).fill(!canRun))
    unmount()
  }
})

// --- Columns and cards -----------------------------------------------------------------

test('AC5: four columns in order with counts; cards in API order', async () => {
  await open(board({
    backlog: [card(5, 'backlog'), card(2, 'backlog')],
    in_progress: [card(7, 'in_progress')],
    done: [card(1, 'done'), card(3, 'done'), card(4, 'done')],
  }))
  expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
    'Backlog 2', 'In progress 1', 'Review 0', 'Done 3',
  ])
  const ids = (label) => within(column(label)).queryAllByRole('link').map((a) => a.textContent)
  expect(ids('Backlog')).toEqual(['#5 Task 5', '#2 Task 2'])
  expect(ids('In progress')).toEqual(['#7 Task 7'])
  expect(ids('Review')).toEqual([])
  expect(ids('Done')).toEqual(['#1 Task 1', '#3 Task 3', '#4 Task 4'])
})

test('AC6: empty columns say so; Backlog says how to add a task', async () => {
  await open(board())
  expect(
    within(column('Backlog')).getByText(
      fullText('No tasks. Add one with + New task, or run fctl task add "title" in the repo.'),
    ),
  ).toBeTruthy()
  for (const label of ['In progress', 'Review', 'Done']) {
    expect(within(column(label)).getByText('No tasks')).toBeTruthy()
  }
})

test('AC7: a card links #id title to the task, drags by the card not the link, and shows titles as text', async () => {
  await open(board({ backlog: [card(14, 'backlog', { title: '<script>alert(1)</script>' })] }))
  const link = screen.getByRole('link', { name: '#14 <script>alert(1)</script>' })
  expect(link.getAttribute('href')).toBe('/tasks/14')
  expect(link.getAttribute('draggable')).toBe('false')
  expect(link.closest('li').getAttribute('draggable')).toBe('true')
  expect(document.querySelector('main script')).toBeNull()
})

test('AC8: a waiting card shows waiting on you', async () => {
  await open(board({ review: [card(12, 'review', { stage: 'human_review', waiting: true })] }))
  expect(within(cardEl(12)).getByText('waiting on you')).toBeTruthy()
})

test('AC9: an escalated card has the red badge and left bar; no other card does', async () => {
  await open(board({
    backlog: [card(1, 'backlog')],
    review: [card(11, 'review', { stage: 'escalated', escalated: true }), card(12, 'review', { stage: 'human_review', waiting: true })],
  }))
  const badge = within(cardEl(11)).getByText('⚠ NEEDS YOU — escalated')
  expect(badge.className).toMatch(/(^|\s)text-red-\d+/)
  const bar = (li) => /(^|\s)border-l-4(\s|$)/.test(li.className) && /(^|\s)border-red-\d+/.test(li.className)
  expect(bar(cardEl(11))).toBe(true)
  for (const id of [1, 12]) {
    expect(cardEl(id).className).not.toMatch(/(^|\s)(border-l-4|border-red-\d+)(\s|$)/)
  }
  expect(screen.getAllByText('⚠ NEEDS YOU — escalated')).toHaveLength(1)
})

test('AC10: a stage without a run shows the stage and no buttons; no stage shows no stage line', async () => {
  await open(board({ in_progress: [card(13, 'in_progress', { stage: 'build' }), card(15, 'in_progress')] }))
  expect(within(cardEl(13)).getByText('build')).toBeTruthy()
  expect(within(cardEl(13)).queryAllByRole('button')).toEqual([])
  expect([...cardEl(15).children].map((el) => el.textContent)).toEqual(['#15 Task 15'])
})

test('AC11: a running card shows ● running · stage and its local start time, and no buttons', async () => {
  const running = (id, stage) =>
    card(id, 'in_progress', { stage, run: { id: 40 + id, status: 'running' }, started_at: '2026-10-18T01:02:00Z' })
  await open(board({ in_progress: [running(13, 'build'), running(16, null)] }))
  const li = cardEl(13)
  expect(within(li).getByText('● running · build')).toBeTruthy()
  expect(within(li).getByText(fullText('started 10:02'))).toBeTruthy()
  expect(li.querySelector('time').getAttribute('datetime')).toBe('2026-10-18T01:02:00Z')
  expect(within(li).queryAllByRole('button')).toEqual([])
  expect(within(cardEl(16)).getByText('● running')).toBeTruthy()
  expect(within(cardEl(16)).queryAllByRole('button')).toEqual([])
})

test('AC12: a stalled card shows stalled · stage and Retry, which runs the task and reloads', async () => {
  const stalled = (id, stage) => card(id, 'in_progress', { stage, run: { id: 40 + id, status: 'failed' }, stalled: true })
  const { fetch } = await open(board({ in_progress: [stalled(13, 'build'), stalled(16, null)] }), {
    'POST /api/tasks/13/run': [202, { run_id: 50, session_id: 's', worktree: '/w' }],
  })
  expect(within(cardEl(13)).getByText(fullText('stalled · build'))).toBeTruthy()
  expect(within(cardEl(16)).getByText(fullText('stalled'))).toBeTruthy()
  expect(within(cardEl(16)).getByRole('button', { name: 'Retry' })).toBeTruthy()
  fireEvent.click(within(cardEl(13)).getByRole('button', { name: 'Retry' }))
  await waitFor(() => expect(loads(fetch)).toBe(2))
  expect(sent(fetch, 'POST', '/api/tasks/13/run')).toBeUndefined()
})

test('AC13: chips read r2 sec✓ ux✓ ui· co✗ with titles, then +126 −9; no round shows neither', async () => {
  await open(board({
    in_progress: [card(13, 'in_progress', {
      stage: 'agent_review', round: 2, additions: 126, deletions: 9,
      verdicts: { security: 'PASS', ux: 'PASS', ui: 'pending', code: 'CHANGES' },
    })],
    backlog: [card(14, 'backlog')],
  }))
  const li = cardEl(13)
  expect(within(li).getByText(fullText('r2 sec✓ ux✓ ui· co✗'))).toBeTruthy()
  expect([...li.querySelectorAll('[title]')].map((s) => [s.textContent, s.title])).toEqual([
    ['sec✓', 'security: PASS'], ['ux✓', 'ux: PASS'], ['ui·', 'ui: pending'], ['co✗', 'code: CHANGES'],
  ])
  expect(within(li).getByText('+126 −9')).toBeTruthy()
  expect(cardEl(14).querySelectorAll('[title]')).toHaveLength(0)
  expect(cardEl(14).textContent).not.toMatch(/r\d|\+\d|−/)
})

test('AC14: done cards show N rounds, no chips or +/−; a null round shows neither', async () => {
  const done = (id, round) => card(id, 'done', {
    round, additions: round && 10, deletions: round && 2,
    verdicts: round && { security: 'PASS', ux: 'PASS', ui: 'PASS', code: 'PASS' },
  })
  await open(board({ done: [done(8, 3), done(9, 1), done(10, null)] }))
  expect(within(cardEl(8)).getByText('3 rounds')).toBeTruthy()
  expect(within(cardEl(9)).getByText('1 round')).toBeTruthy()
  for (const id of [8, 9, 10]) {
    expect(cardEl(id).querySelectorAll('[title]')).toHaveLength(0)
    expect(cardEl(id).textContent).not.toMatch(/\+\d|−/)
  }
  expect(cardEl(10).textContent).toBe('#10 Task 10')
})

test('AC15: every backlog card has Run, which runs it and reloads; review and done cards have none', async () => {
  const { fetch } = await open(board({
    backlog: [card(14, 'backlog'), card(15, 'backlog')],
    review: [card(12, 'review', { stage: 'human_review', waiting: true })],
    done: [card(9, 'done', { round: 1 })],
  }), { 'POST /api/tasks/15/run': [202, { run_id: 50, session_id: 's', worktree: '/w' }] })
  for (const id of [14, 15]) expect(within(cardEl(id)).getByRole('button', { name: 'Run' })).toBeTruthy()
  for (const id of [12, 9]) expect(within(cardEl(id)).queryAllByRole('button')).toEqual([])
  fireEvent.click(within(cardEl(15)).getByRole('button', { name: 'Run' }))
  await waitFor(() => expect(loads(fetch)).toBe(2))
  expect(sent(fetch, 'POST', '/api/tasks/15/run')).toBeUndefined()
})

// --- Board actions ---------------------------------------------------------------------

test('AC16: Run next posts to the project and reloads', async () => {
  const { fetch } = await open(board({ backlog: [card(14, 'backlog')] }), {
    'POST /api/projects/3/run-next': [202, { task_id: 14, run_id: 50 }],
  })
  fireEvent.click(screen.getByRole('button', { name: 'Run next ▶' }))
  await waitFor(() => expect(loads(fetch)).toBe(2))
  expect(sent(fetch, 'POST', '/api/projects/3/run-next')).toBeUndefined()
})

test('AC17: a refused Run, Retry, or Run next shows its detail in the board alert; the next success clears it', async () => {
  const columns = {
    backlog: [card(14, 'backlog')],
    in_progress: [card(13, 'in_progress', { stage: 'build', run: { id: 40, status: 'failed' }, stalled: true })],
  }
  const clicks = {
    Run: ['POST /api/tasks/14/run', () => within(cardEl(14)).getByRole('button', { name: 'Run' })],
    Retry: ['POST /api/tasks/13/run', () => within(cardEl(13)).getByRole('button', { name: 'Retry' })],
    'Run next': ['POST /api/projects/3/run-next', () => screen.getByRole('button', { name: 'Run next ▶' })],
  }
  for (const [refused, ok] of [['Run', 'Retry'], ['Retry', 'Run next'], ['Run next', 'Run']]) {
    const { fetch, responses, unmount } = await open(board(columns))
    responses[clicks[refused][0]] = ACTIVE
    fireEvent.click(clicks[refused][1]())
    expect((await screen.findByRole('alert')).textContent).toBe('run #41 active')
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(4)
    responses[clicks[ok][0]] = [202, {}]
    fireEvent.click(clicks[ok][1]())
    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    expect(fetch.mock.calls.filter(([, init]) => init?.method === 'POST').every(([, init]) => init.headers['X-Requested-By'] === 'fctl')).toBe(true)
    unmount()
  }
  // a successful move clears it too
  const { fetch } = await open(board(columns), {
    'POST /api/tasks/14/run': ACTIVE,
    'PATCH /api/tasks/14': [200, { id: 14, status: 'review', stage: null }],
  })
  fireEvent.click(within(cardEl(14)).getByRole('button', { name: 'Run' }))
  await screen.findByRole('alert')
  drag(14, 'Review', 500)
  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
  expect(sent(fetch, 'PATCH', '/api/tasks/14')).toEqual({ status: 'review', position: 1 })
})

// --- Drag and drop ---------------------------------------------------------------------

test('AC18: dropping a backlog card below the only Review card patches status review, position 2, and reloads', async () => {
  const { fetch } = await open(board({
    backlog: [card(14, 'backlog')],
    review: [card(12, 'review', { position: 1 })],
  }), { 'PATCH /api/tasks/14': [200, { id: 14, status: 'review', stage: null }] })
  drag(14, 'Review', 500)
  await waitFor(() => expect(loads(fetch)).toBe(2))
  expect(sent(fetch, 'PATCH', '/api/tasks/14')).toEqual({ status: 'review', position: 2 })
})

test('AC19: a drop between two cards takes their midpoint, above the first takes −1, an empty column takes 1', async () => {
  const backlog = [card(1, 'backlog', { position: 1 }), card(2, 'backlog', { position: 2 }), card(3, 'backlog', { position: 3 })]
  const cases = [
    [3, 'Backlog', 150, '/api/tasks/3', { status: 'backlog', position: 1.5 }],
    [3, 'Backlog', 100, '/api/tasks/3', { status: 'backlog', position: 0 }],
    [1, 'In progress', 300, '/api/tasks/1', { status: 'in_progress', position: 1 }],
    [2, 'Done', 0, '/api/tasks/2', { status: 'done', position: 1 }],
  ]
  for (const [id, label, y, url, body] of cases) {
    const { fetch, unmount } = await open(board({ backlog }), { [`PATCH ${url}`]: [200, { id, status: body.status, stage: null }] })
    drag(id, label, y)
    await waitFor(() => expect(loads(fetch)).toBe(2))
    expect(sent(fetch, 'PATCH', url)).toEqual(body)
    unmount()
  }
})

test('AC20: dropping a card in the gap directly above or below itself sends nothing', async () => {
  const backlog = [card(1, 'backlog', { position: 1 }), card(2, 'backlog', { position: 2 }), card(3, 'backlog', { position: 3 })]
  const { fetch } = await open(board({ backlog }))
  drag(3, 'Backlog', 190) // between B and C
  drag(3, 'Backlog', 400) // below C
  drag(1, 'Backlog', 50) // above A
  drag(1, 'Backlog', 140) // between A and B
  await act(() => Promise.resolve())
  expect(fetch.mock.calls.filter(([, init]) => init?.method === 'PATCH')).toEqual([])
  expect(loads(fetch)).toBe(1)
})

test('AC21: a refused move shows its detail in the board alert and reloads', async () => {
  const { fetch } = await open(board({ in_progress: [card(13, 'in_progress', { stage: 'build', run: { id: 41, status: 'running' }, started_at: '2026-10-18T01:02:00Z' })] }), {
    'PATCH /api/tasks/13': ACTIVE,
  })
  drag(13, 'Review', 500)
  expect((await screen.findByRole('alert')).textContent).toBe('run #41 active')
  await waitFor(() => expect(loads(fetch)).toBe(2))
  expect(sent(fetch, 'PATCH', '/api/tasks/13')).toEqual({ status: 'review', position: 1 })
  expect(within(column('In progress')).getByRole('link', { name: '#13 Task 13' })).toBeTruthy()
})

// --- + New task ------------------------------------------------------------------------

function openNewTask() {
  const summary = screen.getByText('+ New task')
  fireEvent.click(summary)
  const details = summary.closest('details')
  expect(details.open).toBe(true)
  return within(details)
}

test('AC22: + New task posts the title and markdown, then clears, closes, and reloads', async () => {
  const { fetch } = await open(board(), { 'POST /api/projects/3/tasks': [201, { id: 14, status: 'backlog' }] })
  const form = openNewTask()
  const title = form.getByRole('textbox', { name: 'Title' })
  expect(title.required).toBe(true)
  expect(title.getAttribute('pattern')).toBe('.*\\S.*')
  const description = form.getByRole('textbox', { name: 'Description' })
  expect(description.tagName).toBe('TEXTAREA')
  expect(description.placeholder).toBe('Markdown')
  fireEvent.change(title, { target: { value: 'Export CSV' } })
  fireEvent.change(description, { target: { value: 'Rows as **CSV**' } })
  fireEvent.click(form.getByRole('button', { name: 'Add task' }))
  await waitFor(() => expect(loads(fetch)).toBe(2))
  expect(sent(fetch, 'POST', '/api/projects/3/tasks')).toEqual({ title: 'Export CSV', description_md: 'Rows as **CSV**' })
  expect(title.value).toBe('')
  expect(description.value).toBe('')
  expect(title.closest('details').open).toBe(false)
})

test('AC23: a refused create shows its detail in the form and keeps it open', async () => {
  await open(board(), { 'POST /api/projects/3/tasks': [422, { detail: 'title must not be blank' }] })
  const form = openNewTask()
  fireEvent.change(form.getByRole('textbox', { name: 'Title' }), { target: { value: 'x' } })
  fireEvent.click(form.getByRole('button', { name: 'Add task' }))
  const alert = await form.findByRole('alert')
  expect(alert.textContent).toBe('title must not be blank')
  expect(alert.closest('form')).toBe(form.getByRole('button', { name: 'Add task' }).closest('form'))
  expect(alert.closest('details').open).toBe(true)
  expect(form.getByRole('textbox', { name: 'Title' }).value).toBe('x')
})

// --- Create factory --------------------------------------------------------------------

const factoryOut = (written, skipped) => [200, { written, skipped, commit_hint: 'git add .claude && git commit -m "Add factory"' }]

test('AC24: Create factory sends overwrite false, or true when ticked', async () => {
  for (const overwrite of [false, true]) {
    const { fetch, unmount } = await open(board({}, { factory: 'none', can_run: false }), {
      'POST /api/projects/3/factory': factoryOut(['.claude/a.md'], []),
    })
    if (overwrite) fireEvent.click(screen.getByRole('checkbox', { name: 'Overwrite existing files' }))
    fireEvent.click(screen.getByRole('button', { name: 'Create factory' }))
    await screen.findByText('Commit them so runs can see the factory:')
    expect(sent(fetch, 'POST', '/api/projects/3/factory')).toEqual({ overwrite })
    unmount()
  }
})

test('AC25: the result lists what was written or skipped, the commit hint, and reloads', async () => {
  const skipped8 = Array.from({ length: 8 }, (_, i) => `.claude/agents/s${i}.md`)
  const cases = [
    [['.claude/a.md', '.claude/b.md'], [], 'Wrote 2 files:', null],
    [[], skipped8, null, 'Skipped 8 existing files (tick Overwrite to replace them):'],
    [['.claude/a.md'], ['.claude/b.md'], 'Wrote 1 file:', 'Skipped 1 existing file (tick Overwrite to replace them):'],
  ]
  for (const [written, skipped, wrote, skip] of cases) {
    const { fetch, unmount } = await open(board({}, { factory: 'uncommitted', can_run: false }), {
      'POST /api/projects/3/factory': factoryOut(written, skipped),
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create factory' }))
    await screen.findByText('Commit them so runs can see the factory:')
    if (wrote) expect(screen.getByText(wrote)).toBeTruthy()
    else expect(screen.queryByText(/^Wrote/)).toBeNull()
    if (skip) expect(screen.getByText(skip)).toBeTruthy()
    else expect(screen.queryByText(/^Skipped/)).toBeNull()
    const codes = [...header().querySelectorAll('li > code')].map((c) => c.textContent)
    expect(codes).toEqual([...written, ...skipped])
    const hint = header().querySelector('pre > code')
    expect(hint.textContent).toBe('git add .claude && git commit -m "Add factory"')
    await waitFor(() => expect(loads(fetch)).toBe(2))
    unmount()
  }
})

test('AC26: a refused Create factory shows its detail beside the form, with no file lists', async () => {
  const { fetch } = await open(board({}, { factory: 'none', can_run: false }), {
    'POST /api/projects/3/factory': [409, { detail: 'no test command: run fctl connect --test-cmd' }],
  })
  fireEvent.click(screen.getByRole('button', { name: 'Create factory' }))
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe('no test command: run fctl connect --test-cmd')
  expect(alert.closest('header')).toBe(screen.getByRole('button', { name: 'Create factory' }).closest('header'))
  expect(screen.queryByText(/^(Wrote|Skipped|Commit them)/)).toBeNull()
  expect(header().querySelector('li > code, pre')).toBeNull()
  expect(loads(fetch)).toBe(1)
})

// --- Move to another workspace ---------------------------------------------------------

test('AC27: Move patches the workspace and the header follows the reloaded view-model', async () => {
  const { fetch, responses } = await open(board(), { 'PATCH /api/projects/3': [200, { id: 3, workspace_id: 4 }] })
  const select = screen.getByRole('combobox', { name: 'Workspace' })
  expect([...select.options].map((o) => [o.textContent, o.selected])).toEqual([['personal', true], ['work', false]])
  responses[`GET ${BOARD}`] = [200, { ...board(), project: { ...PROJECT, workspace_id: 4, workspace: 'work' } }]
  fireEvent.change(select, { target: { value: '4' } })
  fireEvent.click(screen.getByRole('button', { name: 'Move' }))
  const h1 = await screen.findByRole('heading', { level: 1, name: 'api · work' })
  expect(within(h1).getByRole('link', { name: 'work' }).getAttribute('href')).toBe('/workspaces/4')
  expect(sent(fetch, 'PATCH', '/api/projects/3')).toEqual({ workspace_id: 4 })
  expect(loads(fetch)).toBe(2)
})

test('AC28: a refused move shows its detail in the Move form', async () => {
  await open(board(), { 'PATCH /api/projects/3': [404, { detail: 'Not Found' }] })
  fireEvent.change(screen.getByRole('combobox', { name: 'Workspace' }), { target: { value: '4' } })
  fireEvent.click(screen.getByRole('button', { name: 'Move' }))
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe('Not Found')
  expect(alert.closest('form')).toBe(screen.getByRole('button', { name: 'Move' }).closest('form'))
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('api · personal')
})

// --- Polling and states ----------------------------------------------------------------

const advance = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))

test('AC29: the board reloads 3000 ms after the last load settles and shows the new view-model', async () => {
  vi.useFakeTimers()
  const responses = { [`GET ${BOARD}`]: [200, board({ in_progress: [card(13, 'in_progress', { stage: 'build' })] })] }
  const fetch = mockFetch(responses)
  renderAt('/projects/3')
  await advance(0)
  expect(within(column('In progress')).getByRole('link', { name: '#13 Task 13' })).toBeTruthy()
  responses[`GET ${BOARD}`] = [200, board({ review: [card(13, 'review', { stage: 'human_review', waiting: true })] })]
  await advance(2999)
  expect(loads(fetch)).toBe(1)
  await advance(1)
  expect(loads(fetch)).toBe(2)
  expect(within(column('Review')).getByRole('link', { name: '#13 Task 13' })).toBeTruthy()
  expect(within(column('In progress')).getByText('No tasks')).toBeTruthy()
})

test("AC30: the API's 404 shows the not-found state with its detail and a link home", async () => {
  mockFetch({ 'GET /api/pages/projects/999': [404, { detail: 'Not Found' }] })
  renderAt('/projects/999')
  expect(await screen.findByRole('heading', { name: 'Not Found' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Go to the dashboard' }).getAttribute('href')).toBe('/')
})

test('AC31: a failed first load shows only the alert; a failed later poll keeps the board until the next success', async () => {
  mockFetch({ [`GET ${BOARD}`]: [500, { detail: 'boom' }] })
  const first = renderAt('/projects/3')
  expect((await screen.findByRole('alert')).textContent).toBe('boom')
  expect(screen.queryAllByRole('heading', { level: 2 })).toEqual([])
  first.unmount()

  vi.useFakeTimers()
  const responses = { [`GET ${BOARD}`]: [200, board({ backlog: [card(14, 'backlog')] })] }
  mockFetch(responses)
  renderAt('/projects/3')
  await advance(0)
  expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(4)
  responses[`GET ${BOARD}`] = [502, { detail: 'Backend unreachable at http://127.0.0.1:4545' }]
  await advance(3000)
  expect(screen.getByRole('alert').textContent).toBe('Backend unreachable at http://127.0.0.1:4545')
  expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(4)
  expect(cardEl(14)).toBeTruthy()
  responses[`GET ${BOARD}`] = [200, board({ backlog: [card(14, 'backlog')] })]
  await advance(3000)
  expect(screen.queryByRole('alert')).toBeNull()
  expect(cardEl(14)).toBeTruthy()
})
