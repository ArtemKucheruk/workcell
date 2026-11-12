import { act, createEvent, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { expectOfflineBanner, expectSkeleton, fetched, fullText, mockFetch, renderAt } from '../../test/render.jsx'

const PROJECT = { id: 3, name: 'api', path: '/Users/me/api', default_branch: 'main', workspace_id: 2, workspace: 'personal' }
const WORKSPACES = [{ id: 2, name: 'personal', projects: 1 }, { id: 4, name: 'work', projects: 0 }]
const BOARD = '/api/pages/projects/3'
const HINT = "factory isn't committed on main: Create factory on the project board, then commit it on main"
const LEGACY_HINT = 'this repo runs the file-based /factory loop: Create factory with Overwrite, then commit it on main'
const ACTIVE = [409, { detail: 'run #41 active' }]

/** A Card as 020's dto/pages.py has it, with 048's description_md. */
const card = (id, status, extra = {}) => ({
  id, title: `Task ${id}`, description_md: '', status, stage: null, round: null, verdicts: null, additions: null, deletions: null,
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
  vi.restoreAllMocks()
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

/** Fires drag event `type` on `el`. jsdom has no DragEvent, so clientY and relatedTarget are set by hand. */
function fireDrag(type, el, { clientY = 0, relatedTarget = null, ...init } = {}) {
  const event = createEvent[type](el, init)
  Object.defineProperty(event, 'clientY', { value: clientY })
  Object.defineProperty(event, 'relatedTarget', { value: relatedTarget })
  fireEvent(el, event)
}

/** Starts dragging card `id`, with every card's rect stubbed; returns its li. */
function start(id) {
  stubRects()
  const source = cardEl(id)
  const dataTransfer = { setData: vi.fn(), effectAllowed: 'all' }
  fireDrag('dragStart', source, { dataTransfer })
  expect(dataTransfer.setData).toHaveBeenCalledWith('text/plain', String(id))
  return source
}

/** Drags card `id` onto the column headed `label` at `clientY`. */
function drag(id, label, clientY) {
  const source = start(id)
  const target = column(label)
  fireDrag('dragOver', target, { clientY })
  fireDrag('drop', target, { clientY })
  fireDrag('dragEnd', source)
}

// 044: the Move menu sits inside each card
const menuOf = (id) => document.getElementById(`move-${id}`)
// jsdom's UA sheet hides a closed popover, so its buttons are queried with hidden: true
const pick = (id, name) => fireEvent.click(within(menuOf(id)).getByRole('button', { name, hidden: true }))
/** A card's buttons outside its Move menu, by text. */
const cardButtons = (id) =>
  within(cardEl(id)).queryAllByRole('button').filter((b) => !menuOf(id).contains(b)).map((b) => b.textContent)
/** An element's text without the Move menus in it. */
function shown(el) {
  const copy = el.cloneNode(true)
  for (const menu of copy.querySelectorAll('[popover]')) menu.remove()
  return copy.textContent
}

// --- Page and header -------------------------------------------------------------------

test('AC1: /projects/3 shows the project, its workspace, and the title', async () => {
  const { fetch } = await open(board())
  expect(fetched(fetch)).toContain(BOARD)
  const h1 = screen.getByRole('heading', { level: 1 })
  expect(h1.textContent).toBe('api · personal')
  expect(within(h1).getByRole('link', { name: 'personal' }).getAttribute('href')).toBe('/workspaces/2')
  await waitFor(() => expect(document.title).toBe('api · Claude Factories')) // the title is set in an effect, after the heading renders
})

test('FE20: main has no Breadcrumb nav and no Claude Factories link', async () => {
  await open(board())
  const main = within(screen.getByRole('main'))
  expect(main.queryByRole('navigation', { name: 'Breadcrumb' })).toBeNull()
  expect(main.queryByRole('link', { name: 'Claude Factories' })).toBeNull()
})

test('AC2: the header shows Factory: ready ✓, or the uncommitted or none state', async () => {
  const ready = await open(board())
  expect(within(header()).getByText('Factory: ready ✓')).toBeTruthy()
  ready.unmount()
  for (const factory of ['uncommitted', 'none']) {
    const { unmount } = await open(board({}, { factory, can_run: false }))
    expect(within(header()).getByText(`Factory: ${factory}`)).toBeTruthy()
    unmount()
  }
})

test('FE6: the header holds the project header, + New task, Run next, and the hint; main has none of the moved parts', async () => {
  await open(board({}, { factory: 'none', hint: HINT, can_run: false }))
  const head = within(header())
  expect(head.getByRole('heading', { level: 1 }).textContent).toBe('api · personal')
  expect(head.getByRole('link', { name: 'Factory: none' })).toBeTruthy()
  expect(head.getByText('+ New task')).toBeTruthy()
  expect(head.getByRole('button', { name: 'Run next ▶' })).toBeTruthy()
  expect(head.getByText(HINT)).toBeTruthy()
  const main = screen.getByRole('main')
  const inMain = within(main)
  expect(main.textContent).not.toContain('/Users/me/api')
  expect(inMain.queryByRole('link', { name: 'Code' })).toBeNull()
  expect(inMain.queryByRole('button', { name: 'Create factory' })).toBeNull()
  expect(inMain.queryByRole('checkbox', { name: 'Overwrite existing files' })).toBeNull()
  expect(main.querySelector('input[type="file"]')).toBeNull()
  expect(main.textContent).not.toContain('Project context')
  expect(inMain.queryByRole('combobox', { name: 'Workspace' })).toBeNull()
  expect(inMain.queryByRole('button', { name: 'Move' })).toBeNull()
})

test('AC3: a hint shows in the header; a null hint shows none', async () => {
  const withHint = await open(board({}, { factory: 'none', hint: HINT, can_run: false }))
  expect(within(header()).getByText(HINT)).toBeTruthy()
  withHint.unmount()
  await open(board())
  expect(screen.queryByText(/factory isn't committed/)).toBeNull()
})

test('059 FE2: legacy shows the Factory: legacy link and its hint in the header, and Run next is disabled', async () => {
  await open(board({ backlog: [card(1, 'backlog')] }, { factory: 'legacy', hint: LEGACY_HINT, can_run: false }))
  const head = within(header())
  expect(head.getByRole('link', { name: 'Factory: legacy' }).getAttribute('href')).toBe('/projects/3/settings')
  expect(head.getByText(LEGACY_HINT)).toBeTruthy()
  expect(head.getByRole('button', { name: 'Run next ▶' }).disabled).toBe(true)
  expect(screen.getByRole('button', { name: 'Run' }).disabled).toBe(true)
})

test('058 FE5: a factory_error shows as one muted factory/: line in the header, under the hint, and not as an alert', async () => {
  const error = "factory/board.json isn't valid JSON"
  await open(board({}, { factory: 'none', hint: HINT, can_run: false, factory_error: error }))
  const lines = [...header().querySelectorAll('*')].filter((el) => el.textContent.startsWith('factory/: '))
  expect(lines.map((el) => el.textContent)).toEqual([`factory/: ${error}`])
  const [line] = lines
  expect(line.className).toMatch(/(^|\s)text-muted(\s|$)/)
  expect(line.closest('[role="alert"]')).toBeNull()
  expect(screen.queryByRole('alert')).toBeNull()
  expect(within(header()).getByText(HINT).compareDocumentPosition(line) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

test('058 FE6: a null or missing factory_error shows no factory/: line', async () => {
  for (const extra of [{ factory_error: null }, {}]) {
    const { unmount } = await open(board({}, extra))
    expect(screen.getByRole('main').textContent).not.toContain('factory/:')
    unmount()
  }
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

const cls = (re) => new RegExp(`(^|\\s)${re}(\\s|$)`)

test('AC8, 043 FE7: a waiting card shows the waiting on you pill', async () => {
  await open(board({ review: [card(12, 'review', { stage: 'human_review', waiting: true })] }))
  expect(within(cardEl(12)).getByText('waiting on you').className).toMatch(cls('bg-warning'))
})

test('AC9, 043 FE7: an escalated card has the escalated pill and the red left bar; no other card has either', async () => {
  await open(board({
    backlog: [card(1, 'backlog')],
    review: [card(11, 'review', { stage: 'escalated', escalated: true }), card(12, 'review', { stage: 'human_review', waiting: true })],
  }))
  const pill = within(cardEl(11)).getByText('escalated')
  expect(pill.className).toMatch(cls('bg-danger'))
  expect(pill.className).toMatch(cls('text-surface'))
  expect(cardEl(11).className).toMatch(cls('border-l-4'))
  expect(cardEl(11).className).toMatch(cls('border-danger'))
  for (const id of [1, 12]) {
    expect(cardEl(id).className).not.toMatch(/(^|\s)(border-l-4|border-danger)(\s|$)/)
  }
  expect(screen.getAllByText('escalated')).toHaveLength(1)
  expect(within(cardEl(1)).queryByText('waiting on you')).toBeNull()
  expect(screen.getAllByText('waiting on you')).toHaveLength(1)
})

test('AC10: a stage without a run shows the stage and no buttons but Move; no stage shows no stage line', async () => {
  await open(board({ in_progress: [card(13, 'in_progress', { stage: 'build' }), card(15, 'in_progress')] }))
  expect(within(cardEl(13)).getByText('build')).toBeTruthy()
  expect(cardButtons(13)).toEqual(['Move'])
  expect([...cardEl(15).children].map(shown)).toEqual(['#15 Task 15', 'Move'])
})

test('AC11, 043 FE8, 046 FE2: a running card shows the ● running badge, its muted stage, how long ago it started, and no buttons', async () => {
  vi.setSystemTime(new Date('2026-10-18T01:07:00Z')) // 5 minutes after the start
  const running = (id, stage) =>
    card(id, 'in_progress', { stage, run: { id: 40 + id, status: 'running' }, started_at: '2026-10-18T01:02:00Z' })
  await open(board({ in_progress: [running(13, 'build'), running(16, null)] }))
  const li = cardEl(13)
  const badge = within(li).getByText(fullText('● running'))
  expect(badge.className).toMatch(cls('text-accent'))
  const line = badge.parentElement
  expect([...line.children].map((el) => el.textContent)).toEqual(['● running', 'build'])
  expect(line.children[1].className).toMatch(cls('text-muted'))
  expect(within(li).getByText(fullText('started 5m ago'))).toBeTruthy()
  expect(li.querySelector('time').getAttribute('datetime')).toBe('2026-10-18T01:02:00Z')
  expect(li.querySelector('time').getAttribute('title')).toBe('2026-10-18 10:02')
  expect(cardButtons(13)).toEqual(['Move'])
  const bare = within(cardEl(16)).getByText(fullText('● running'))
  expect([...bare.parentElement.children]).toEqual([bare])
  expect(within(cardEl(16)).getByText(fullText('started 5m ago'))).toBeTruthy()
  expect(cardButtons(16)).toEqual(['Move'])
  for (const label of ['In progress', 'Backlog', 'Review', 'Done']) expect(shown(li)).not.toContain(label) // Q5: no status pill
})

test('AC12, 043 FE8: a stalled card shows stalled · stage and Retry, which runs the task and reloads; no card has a status pill', async () => {
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
  expect(document.querySelectorAll('main li .rounded-full')).toHaveLength(0)
})

test('AC13, 043 FE9: chips read r2 sec ✓ ux ✓ ui · code ✗ as colored Chips with titles, then +126 −9; no round shows neither', async () => {
  await open(board({
    in_progress: [card(13, 'in_progress', {
      stage: 'agent_review', round: 2, additions: 126, deletions: 9,
      verdicts: { security: 'PASS', ux: 'PASS', ui: 'pending', code: 'CHANGES' },
    })],
    backlog: [card(14, 'backlog')],
  }))
  const li = cardEl(13)
  expect(within(li).getByText(fullText('r2 sec ✓ ux ✓ ui · code ✗'))).toBeTruthy()
  const chips = [...li.querySelectorAll('[title]')]
  expect(chips.map((s) => [s.tagName, s.textContent, s.title])).toEqual([
    ['SPAN', 'sec ✓', 'security: PASS'], ['SPAN', 'ux ✓', 'ux: PASS'], ['SPAN', 'ui ·', 'ui: pending'], ['SPAN', 'code ✗', 'code: CHANGES'],
  ])
  expect(chips.map((s) => ['text-success', 'text-danger', 'text-muted'].find((c) => cls(c).test(s.className)))).toEqual([
    'text-success', 'text-success', 'text-muted', 'text-danger',
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
  expect(shown(cardEl(10))).toBe('#10 Task 10Move')
})

test('AC15: every backlog card has Run, which runs it and reloads; review and done cards have only Move', async () => {
  const { fetch } = await open(board({
    backlog: [card(14, 'backlog'), card(15, 'backlog')],
    review: [card(12, 'review', { stage: 'human_review', waiting: true })],
    done: [card(9, 'done', { round: 1 })],
  }), { 'POST /api/tasks/15/run': [202, { run_id: 50, session_id: 's', worktree: '/w' }] })
  for (const id of [14, 15]) expect(within(cardEl(id)).getByRole('button', { name: 'Run' })).toBeTruthy()
  for (const id of [12, 9]) expect(cardButtons(id)).toEqual(['Move'])
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

// --- 044: card states and drop feedback ------------------------------------------------

/** Backlog 1, 2, 3 at positions 1, 2, 3. */
const BACKLOG = [card(1, 'backlog'), card(2, 'backlog'), card(3, 'backlog')]
/** A card in every column: Backlog 1, 2, 3; In progress 7 at position 5; Review 12; Done 9. */
const ALL = {
  backlog: BACKLOG,
  in_progress: [card(7, 'in_progress', { position: 5 })],
  review: [card(12, 'review', { stage: 'human_review', waiting: true })],
  done: [card(9, 'done', { round: 1 })],
}
const OK = (id, status) => [200, { id, status, stage: null }]
/** The cards marked with data-drop, as [link text, before|after]. */
const marked = () => [...document.querySelectorAll('[data-drop]')].map((li) => [li.querySelector('a').textContent, li.dataset.drop])
/** The headings of the columns marked with data-over. */
const highlighted = () => [...document.querySelectorAll('section[data-over]')].map((s) => s.querySelector('h2').textContent)
const status = () => screen.getByRole('status')

test('FE1: every card has a hover ring and an accent ring while its link or a button in it has keyboard focus; the li takes no focus', async () => {
  await open(board(ALL))
  const lis = document.querySelectorAll('main section li')
  expect(lis).toHaveLength(6)
  for (const li of lis) {
    expect(li.className).toMatch(/(^|\s)hover:ring-\S+/)
    expect(li.className).toMatch(/(^|\s)has-(focus-visible|\[:focus-visible\]):ring-2(\s|$)/)
    expect(li.className).toMatch(/(^|\s)has-(focus-visible|\[:focus-visible\]):ring-accent(\s|$)/)
    expect(li.hasAttribute('tabindex')).toBe(false)
  }
})

test('FE2: dragstart sets data-dragging on the dragged card only, which dims it; dragend removes it', async () => {
  await open(board({ backlog: BACKLOG }))
  const li = start(2)
  // Q9: set once the browser has taken the drag image
  await waitFor(() => expect(li.hasAttribute('data-dragging')).toBe(true))
  expect(document.querySelectorAll('[data-dragging]')).toHaveLength(1)
  expect(li.className).toMatch(/(^|\s)data-dragging:opacity-\d+(\s|$)/)
  fireDrag('dragEnd', li)
  expect(document.querySelectorAll('[data-dragging]')).toHaveLength(0)
})

test('FE3: the column under the dragged card gets data-over; leaving it, a drop, or dragend clears it', async () => {
  const { fetch } = await open(board(ALL), { 'PATCH /api/tasks/1': OK(1, 'review') })
  const source = start(1)
  fireDrag('dragOver', column('Review'), { clientY: 500 })
  expect(highlighted()).toEqual(['Review 1'])
  expect(column('Review').className).toMatch(cls('data-over:ring-accent'))
  fireDrag('dragOver', column('In progress'), { clientY: 500 })
  expect(highlighted()).toEqual(['In progress 1'])
  // onto its own heading isn't leaving it
  fireDrag('dragLeave', column('In progress'), { relatedTarget: column('In progress').querySelector('h2') })
  expect(highlighted()).toEqual(['In progress 1'])
  fireDrag('dragLeave', column('In progress'), { relatedTarget: column('Done') })
  expect(highlighted()).toEqual([])
  fireDrag('dragOver', column('Review'), { clientY: 500 })
  fireDrag('dragLeave', column('Review'), { relatedTarget: null }) // out of the window
  expect(highlighted()).toEqual([])
  fireDrag('dragOver', column('Review'), { clientY: 500 })
  fireDrag('dragEnd', source)
  expect(highlighted()).toEqual([])
  start(1)
  fireDrag('dragOver', column('Review'), { clientY: 500 })
  fireDrag('drop', column('Review'), { clientY: 500 })
  expect(highlighted()).toEqual([])
  fireDrag('dragEnd', source)
  await waitFor(() => expect(loads(fetch)).toBe(2))
})

test('FE4: dragover marks the gap the drop takes: the card below it is before, or the last card after', async () => {
  await open(board({ backlog: BACKLOG, in_progress: ALL.in_progress }))
  for (const [id, label, y, mark] of [
    [3, 'Backlog', 150, ['#2 Task 2', 'before']],
    [1, 'Backlog', 400, ['#3 Task 3', 'after']],
    [1, 'In progress', 0, ['#7 Task 7', 'before']],
  ]) {
    const source = start(id)
    fireDrag('dragOver', column(label), { clientY: y })
    expect(marked()).toEqual([mark])
    fireDrag('dragEnd', source)
  }
  // the mark follows the pointer, and stays on one card
  const source = start(3)
  fireDrag('dragOver', column('Backlog'), { clientY: 150 })
  fireDrag('dragOver', column('In progress'), { clientY: 400 })
  expect(marked()).toEqual([['#7 Task 7', 'after']])
  fireDrag('dragEnd', source)
})

test('FE5: no line where a drop sends nothing or in an empty column, which keeps its highlight; drop and dragend clear the line', async () => {
  const { fetch } = await open(board({ backlog: BACKLOG }), { 'PATCH /api/tasks/3': OK(3, 'backlog') })
  for (const [id, y] of [[3, 190], [3, 400], [1, 50], [1, 140]]) {
    const source = start(id)
    fireDrag('dragOver', column('Backlog'), { clientY: y })
    expect(highlighted()).toEqual(['Backlog 3'])
    expect(marked()).toEqual([])
    fireDrag('dragEnd', source)
  }
  let source = start(1)
  fireDrag('dragOver', column('Review'), { clientY: 0 })
  expect(highlighted()).toEqual(['Review 0'])
  expect(marked()).toEqual([])
  fireDrag('dragOver', column('Backlog'), { clientY: 400 })
  expect(marked()).toEqual([['#3 Task 3', 'after']])
  fireDrag('dragEnd', source)
  expect(marked()).toEqual([])
  source = start(3)
  fireDrag('dragOver', column('Backlog'), { clientY: 150 })
  expect(marked()).toEqual([['#2 Task 2', 'before']])
  fireDrag('drop', column('Backlog'), { clientY: 150 })
  expect(marked()).toEqual([])
  fireDrag('dragEnd', source)
  await waitFor(() => expect(loads(fetch)).toBe(2))
  expect(sent(fetch, 'PATCH', '/api/tasks/3')).toEqual({ status: 'backlog', position: 1.5 })
})

test('FE6: the line takes no room: during a dragover each list holds just its cards, and the line is absolute on a relative card', async () => {
  await open(board({ backlog: BACKLOG, in_progress: ALL.in_progress }))
  const source = start(3)
  fireDrag('dragOver', column('Backlog'), { clientY: 150 })
  expect(marked()).toEqual([['#2 Task 2', 'before']])
  for (const [label, ids] of [['Backlog', [1, 2, 3]], ['In progress', [7]]]) {
    const items = [...column(label).querySelector('ol').children]
    expect(items.map((el) => [el.tagName, el.querySelector('a').textContent])).toEqual(ids.map((n) => ['LI', `#${n} Task ${n}`]))
  }
  const li = cardEl(2)
  expect(li.className).toMatch(cls('relative'))
  for (const side of ['before', 'after']) expect(li.className).toMatch(cls(`data-\\[drop=${side}\\]:${side}:absolute`))
  fireDrag('dragEnd', source)
})

test("FE7: the gap rule reads only the cards' rects, never a Move menu's: the AC19 drops send the same positions", async () => {
  const cases = [
    [3, 'Backlog', 150, '/api/tasks/3', { status: 'backlog', position: 1.5 }],
    [3, 'Backlog', 100, '/api/tasks/3', { status: 'backlog', position: 0 }],
    [1, 'In progress', 300, '/api/tasks/1', { status: 'in_progress', position: 1 }],
    [2, 'Done', 0, '/api/tasks/2', { status: 'done', position: 1 }],
  ]
  for (const [id, label, y, url, body] of cases) {
    const { fetch, unmount } = await open(board({ backlog: BACKLOG }), { [`PATCH ${url}`]: OK(id, body.status) })
    const menu = menuOf(1)
    expect(cardEl(1).contains(menu)).toBe(true)
    // a rect that would move every gap, if the rule read it
    const rect = vi.fn(() => ({ top: -1000, height: 5000, bottom: 4000, left: 0, right: 200, width: 200 }))
    for (const el of [menu, ...menu.querySelectorAll('*')]) el.getBoundingClientRect = rect
    drag(id, label, y)
    await waitFor(() => expect(loads(fetch)).toBe(2))
    expect(sent(fetch, 'PATCH', url)).toEqual(body)
    expect(rect).not.toHaveBeenCalled()
    unmount()
  }
})

// --- 044: the Move menu ----------------------------------------------------------------

test('FE8: every card in every column has a Move button opening its own popover="auto" menu', async () => {
  await open(board(ALL))
  for (const id of [1, 2, 3, 7, 12, 9]) {
    const move = within(cardEl(id)).getByRole('button', { name: 'Move' })
    expect(move.getAttribute('type')).toBe('button')
    expect(move.getAttribute('aria-describedby')).toBe(`task-${id}`)
    expect(move.getAttribute('popovertarget')).toBe(`move-${id}`)
    expect(menuOf(id).getAttribute('popover')).toBe('auto')
    expect(cardEl(id).contains(menuOf(id))).toBe(true)
  }
})

test('FE9: a menu lists the other columns in order, then Up and Down in Backlog, not past its ends (048: then Edit and Delete)', async () => {
  const names = (id) => within(menuOf(id)).getAllByRole('button', { hidden: true }).map((b) => b.textContent)
  const { unmount } = await open(board(ALL))
  expect(names(1)).toEqual(['In progress', 'Review', 'Done', 'Down', 'Edit', 'Delete'])
  expect(names(2)).toEqual(['In progress', 'Review', 'Done', 'Up', 'Down', 'Edit', 'Delete'])
  expect(names(3)).toEqual(['In progress', 'Review', 'Done', 'Up', 'Edit', 'Delete'])
  expect(names(7)).toEqual(['Backlog', 'Review', 'Done', 'Edit', 'Delete'])
  expect(names(12)).toEqual(['Backlog', 'In progress', 'Done', 'Edit', 'Delete'])
  expect(names(9)).toEqual(['Backlog', 'In progress', 'Review', 'Edit', 'Delete'])
  unmount()
  await open(board({ backlog: [card(1, 'backlog')] }))
  expect(names(1)).toEqual(['In progress', 'Review', 'Done', 'Edit', 'Delete'])
})

test('FE10: every menu button hides its menu natively', async () => {
  await open(board(ALL))
  const buttons = [...document.querySelectorAll('[id^="move-"] button')]
  expect(buttons).toHaveLength(4 + 5 + 4 + 3 + 3 + 3 + 6 * 2) // 048: Edit and Delete on each
  for (const b of buttons) {
    expect(b.getAttribute('popovertarget')).toBe(b.closest('[popover]').id)
    expect(b.getAttribute('popovertargetaction')).toBe('hide')
  }
})

test('FE11: a column button patches the card to the bottom of that column and reloads', async () => {
  const cases = [
    [{ backlog: BACKLOG }, 1, 'Review', { status: 'review', position: 1 }],
    [{ backlog: BACKLOG, in_progress: ALL.in_progress }, 1, 'In progress', { status: 'in_progress', position: 6 }],
    [{ backlog: BACKLOG, review: ALL.review }, 12, 'Backlog', { status: 'backlog', position: 4 }],
  ]
  for (const [columns, id, name, body] of cases) {
    const { fetch, unmount } = await open(board(columns), { [`PATCH /api/tasks/${id}`]: OK(id, body.status) })
    pick(id, name)
    await waitFor(() => expect(loads(fetch)).toBe(2))
    expect(sent(fetch, 'PATCH', `/api/tasks/${id}`)).toEqual(body)
    unmount()
  }
})

test('FE12: Up and Down move a backlog card one place, at the midpoint rule position, and reload', async () => {
  for (const [id, name, position] of [[2, 'Up', 0], [3, 'Up', 1.5], [1, 'Down', 2.5], [2, 'Down', 4]]) {
    const { fetch, unmount } = await open(board({ backlog: BACKLOG }), { [`PATCH /api/tasks/${id}`]: OK(id, 'backlog') })
    pick(id, name)
    await waitFor(() => expect(loads(fetch)).toBe(2))
    expect(sent(fetch, 'PATCH', `/api/tasks/${id}`)).toEqual({ status: 'backlog', position })
    unmount()
  }
})

test('FE13: one hidden status region, empty from the first load, names each move by menu or drop', async () => {
  const { fetch } = await open(board({ backlog: BACKLOG }), {
    'PATCH /api/tasks/1': OK(1, 'review'), 'PATCH /api/tasks/2': OK(2, 'backlog'), 'PATCH /api/tasks/3': OK(3, 'backlog'),
  })
  expect(screen.getAllByRole('status')).toHaveLength(1)
  expect(status().className).toMatch(cls('sr-only'))
  expect(status().textContent).toBe('')
  const steps = [
    [() => pick(1, 'Review'), 'Moved #1 Task 1 to Review.'],
    [() => pick(2, 'Up'), 'Moved #2 Task 2 up.'],
    [() => pick(2, 'Down'), 'Moved #2 Task 2 down.'],
    [() => drag(1, 'Review', 500), 'Moved #1 Task 1 to Review.'],
    [() => drag(3, 'Backlog', 100), 'Moved #3 Task 3 within Backlog.'],
  ]
  for (const [step, words] of steps) {
    const before = loads(fetch)
    step()
    await waitFor(() => expect(loads(fetch)).toBe(before + 1))
    expect(status().textContent).toBe(words)
  }
  expect(screen.queryByRole('alert')).toBeNull()
})

test('FE14: a refused menu move shows in the board alert, not the status region, and reloads with the card in place', async () => {
  const { fetch } = await open(board({ backlog: BACKLOG }), { 'PATCH /api/tasks/1': ACTIVE })
  pick(1, 'Review')
  expect((await screen.findByRole('alert')).textContent).toBe('run #41 active')
  await waitFor(() => expect(loads(fetch)).toBe(2))
  expect(sent(fetch, 'PATCH', '/api/tasks/1')).toEqual({ status: 'review', position: 1 })
  expect(status().textContent).toBe('')
  expect(within(column('Backlog')).getByRole('link', { name: '#1 Task 1' })).toBeTruthy()
})

test("FE15: after a menu move's reload, focus is on the moved card's Move button, in its new column or in place", async () => {
  const { fetch, responses } = await open(board({ backlog: BACKLOG }), {
    'PATCH /api/tasks/1': OK(1, 'review'), 'PATCH /api/tasks/2': ACTIVE,
  })
  responses[`GET ${BOARD}`] = [200, board({ backlog: [card(2, 'backlog'), card(3, 'backlog')], review: [card(1, 'review', { position: 1 })] })]
  const moveButton = (id) => within(cardEl(id)).getByRole('button', { name: 'Move' })
  pick(1, 'Review')
  await waitFor(() => expect(within(column('Review')).queryByRole('link', { name: '#1 Task 1' })).toBeTruthy())
  await waitFor(() => expect(document.activeElement).toBe(moveButton(1)))
  expect(column('Review').contains(document.activeElement)).toBe(true)
  document.activeElement.blur()
  pick(2, 'Down')
  await screen.findByRole('alert')
  await waitFor(() => expect(loads(fetch)).toBe(3))
  await waitFor(() => expect(document.activeElement).toBe(moveButton(2)))
  expect(column('Backlog').contains(document.activeElement)).toBe(true)
})

// --- 044: the board alert --------------------------------------------------------------

test('FE16: an action empties the alert and status region as it starts; a refusal outlasts polls; a success leaves no alert', async () => {
  vi.useFakeTimers()
  const responses = {
    [`GET ${BOARD}`]: [200, board({ backlog: [card(14, 'backlog')] })],
    'PATCH /api/tasks/14': OK(14, 'review'),
    'POST /api/tasks/14/run': ACTIVE,
  }
  const fetch = mockFetch(responses)
  renderAt('/projects/3')
  await advance(0)
  pick(14, 'Review')
  await advance(0)
  expect(status().textContent).toBe('Moved #14 Task 14 to Review.')
  expect(screen.queryByRole('alert')).toBeNull()
  // a refused Run: the status region empties, the alert stays through a successful poll
  fireEvent.click(within(cardEl(14)).getByRole('button', { name: 'Run' }))
  expect(status().textContent).toBe('')
  await advance(0)
  expect(screen.getByRole('alert').textContent).toBe('run #41 active')
  const polled = loads(fetch)
  await advance(3000)
  expect(loads(fetch)).toBe(polled + 1)
  expect(screen.getByRole('alert').textContent).toBe('run #41 active')
  // Run next, pending: no alert until it settles, then the 409's
  let settle
  fetch.mockImplementationOnce(() => new Promise((resolve) => (settle = resolve)))
  fireEvent.click(screen.getByRole('button', { name: 'Run next ▶' }))
  expect(screen.queryByRole('alert')).toBeNull()
  await advance(0)
  expect(screen.queryByRole('alert')).toBeNull()
  expect(fetch.mock.calls.at(-1)[0]).toBe('/api/projects/3/run-next')
  settle(new Response(JSON.stringify(ACTIVE[1]), { status: 409 }))
  await advance(0)
  expect(screen.getByRole('alert').textContent).toBe('run #41 active')
})

// --- 044: columns ----------------------------------------------------------------------

test('FE20: from md up each card list scrolls on its own under its heading, capped near the viewport height', async () => {
  await open(board({ backlog: BACKLOG }))
  const section = column('Backlog')
  const list = section.querySelector('ol')
  expect(list.className).toMatch(cls('md:overflow-y-auto'))
  expect(list.className).toMatch(/(^|\s)md:max-h-\[[^\]\s]*\d+d?vh[^\]\s]*\](\s|$)/)
  expect(list.contains(section.querySelector('h2'))).toBe(false)
  // below md nothing caps or scrolls, so the page does
  expect(`${section.className} ${list.className}`).not.toMatch(/(^|\s)(max-h-|overflow-)/)
})

// --- + New task ------------------------------------------------------------------------

/** + New task's popover, shown as a click would, with hidePopover stubbed: jsdom has no Popover API (Q12). */
function newTask() {
  const button = screen.getByRole('button', { name: '+ New task' })
  const popover = document.getElementById(button.getAttribute('popovertarget'))
  popover.style.display = 'block' // jsdom's UA sheet hides it while closed
  popover.hidePopover = vi.fn()
  popover.showPopover = vi.fn()
  return popover
}

test('FE17: + New task is a button opening a popover="auto" that holds the form; no details; Title has autofocus', async () => {
  await open(board())
  const button = within(header()).getByRole('button', { name: '+ New task' })
  expect(button.getAttribute('type')).toBe('button')
  const popover = document.getElementById(button.getAttribute('popovertarget'))
  expect(popover.getAttribute('popover')).toBe('auto')
  expect(popover.querySelector('form')).toBeTruthy()
  expect(within(popover).getByRole('textbox', { name: 'Title', hidden: true }).hasAttribute('autofocus')).toBe(true)
  expect(screen.getByRole('main').querySelector('details')).toBeNull()
})

test('AC22, FE18: + New task posts the title and markdown, then resets, hides its popover, and reloads', async () => {
  const { fetch } = await open(board(), { 'POST /api/projects/3/tasks': [201, { id: 14, status: 'backlog' }] })
  const popover = newTask()
  const form = within(popover)
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
  expect(popover.hidePopover).toHaveBeenCalledTimes(1)
})

test('AC23, FE19: a refused create shows its detail in the form and keeps the popover open with the input', async () => {
  await open(board(), { 'POST /api/projects/3/tasks': [422, { detail: 'title must not be blank' }] })
  const popover = newTask()
  const form = within(popover)
  fireEvent.change(form.getByRole('textbox', { name: 'Title' }), { target: { value: 'x' } })
  fireEvent.click(form.getByRole('button', { name: 'Add task' }))
  const alert = await form.findByRole('alert')
  expect(alert.textContent).toBe('title must not be blank')
  expect(alert.closest('form')).toBe(form.getByRole('button', { name: 'Add task' }).closest('form'))
  expect(popover.hidePopover).not.toHaveBeenCalled()
  expect(form.getByRole('textbox', { name: 'Title' }).value).toBe('x')
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

test('AC31, 046 FE9, FE12, FE13: a failed first load shows only the alert; a failed poll over the board shows the offline banner until the next success', async () => {
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
  await expectOfflineBanner(responses, `GET ${BOARD}`, () => {
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(4)
    expect(cardEl(14)).toBeTruthy()
  })
})

test("046 FE16: until the first load the board is a skeleton of the header and the loaded board's four columns", async () => {
  mockFetch({}).mockImplementation(() => new Promise(() => {})) // nothing ever answers
  renderAt('/projects/3')
  const skeleton = await screen.findByRole('status')
  expectSkeleton(skeleton)
  const grid = [...skeleton.querySelectorAll('div')].filter((el) => cls('md:grid-cols-4').test(el.className))
  expect(grid).toHaveLength(1)
  const columns = [...grid[0].children]
  expect(columns).toHaveLength(4)
  for (const column of columns) expect(column.className).toMatch(cls('min-h-32'))
})

// --- 048: Edit and Delete --------------------------------------------------------------

const CSV = card(14, 'backlog', { title: 'Export CSV', description_md: 'Columns: *id*' })
const SAVED = [200, { id: 14, status: 'backlog', stage: null }]
const Q8 =
  'This removes its runs, rounds and their files, verdicts, comments, decisions, status history, and transcript records ' +
  'from the app. Its worktree, branch, run logs, and copied transcript files stay on disk.'
const moveOf = (id) => within(cardEl(id)).getByRole('button', { name: 'Move' })
const titleBox = (form) => form.getByRole('textbox', { name: 'Title' })
const descriptionBox = (form) => form.getByRole('textbox', { name: 'Description' })
const type = (box, value) => fireEvent.change(box, { target: { value } })

/** The board with #14 Export CSV in Backlog, then Edit chosen in its menu; `shown` is the submit label as showPopover ran. */
async function editing(more = {}) {
  const view = await open(board({ backlog: [CSV] }), more)
  const popover = newTask()
  let shown
  popover.showPopover = vi.fn(() => (shown = popover.querySelector('form button').textContent))
  pick(14, 'Edit')
  return { ...view, popover, form: within(popover), shown }
}

test('048 FE1: every Move menu ends with a divider, then Edit and Delete, after the columns and any Up and Down', async () => {
  await open(board(ALL))
  const items = (id) => [...menuOf(id).children].slice(1).map((el) => (el.tagName === 'HR' ? '—' : el.textContent))
  expect(items(2)).toEqual(['In progress', 'Review', 'Done', '—', 'Up', 'Down', '—', 'Edit', 'Delete'])
  expect(items(7)).toEqual(['Backlog', 'Review', 'Done', '—', 'Edit', 'Delete'])
  for (const id of [1, 2, 3, 7, 12, 9]) {
    expect(items(id).slice(-3)).toEqual(['—', 'Edit', 'Delete'])
    for (const name of ['Edit', 'Delete']) {
      const item = within(menuOf(id)).getByRole('button', { name, hidden: true })
      expect(item.getAttribute('popovertarget')).toBe(`move-${id}`)
      expect(item.getAttribute('popovertargetaction')).toBe('hide')
    }
  }
})

test('048 FE2: Edit shows the new-task popover labelled Edit #14, filled from the card, with Save for Add task', async () => {
  const { popover, form } = await editing()
  expect(popover.id).toBe('new-task')
  expect(popover.showPopover).toHaveBeenCalledTimes(1)
  expect(popover.querySelector('form button').textContent).toBe('Save')
  const edit = within(form.getByRole('form', { name: 'Edit #14' }))
  expect(titleBox(edit).value).toBe('Export CSV')
  expect(descriptionBox(edit).value).toBe('Columns: *id*')
  expect(edit.getByRole('button', { name: 'Save' })).toBeTruthy()
  expect(form.queryByRole('button', { name: 'Add task' })).toBeNull()
})

test('048 FE2: the form is in edit mode before showPopover runs, so its autofocus lands on the filled Title', async () => {
  const { shown, form } = await editing()
  expect(shown).toBe('Save')
  expect(titleBox(form).hasAttribute('autofocus')).toBe(true)
})

test('048 FE3: Save patches the title and description as typed, then hides the popover, reloads, and says Saved #14', async () => {
  const { fetch, form, popover } = await editing({ 'PATCH /api/tasks/14': SAVED })
  type(titleBox(form), '  Export CSV v2  ')
  type(descriptionBox(form), 'Columns: *id, title*')
  fireEvent.click(form.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(loads(fetch)).toBe(2))
  expect(sent(fetch, 'PATCH', '/api/tasks/14')).toEqual({ title: '  Export CSV v2  ', description_md: 'Columns: *id, title*' })
  expect(popover.hidePopover).toHaveBeenCalledTimes(1)
  expect(status().textContent).toBe('Saved #14 Export CSV v2.')
  expect(sends(fetch, 'POST', '/api/projects/3/tasks')).toEqual([])
  expect(screen.queryByRole('alert')).toBeNull()
})

test("048 FE4: after a save's reload, focus is on card 14's Move button", async () => {
  const { form, responses } = await editing({ 'PATCH /api/tasks/14': SAVED })
  responses[`GET ${BOARD}`] = [200, board({ backlog: [card(15, 'backlog'), { ...CSV, title: 'Export CSV v2' }] })]
  type(titleBox(form), 'Export CSV v2')
  fireEvent.click(form.getByRole('button', { name: 'Save' }))
  await screen.findByRole('link', { name: '#14 Export CSV v2' })
  await waitFor(() => expect(document.activeElement).toBe(moveOf(14)))
})

test('048 FE5: a refused save shows its detail in the form and keeps the popover open with the input; the board alert stays empty', async () => {
  const { fetch, form, popover } = await editing({ 'PATCH /api/tasks/14': [422, { detail: 'title must not be blank' }] })
  type(titleBox(form), 'x')
  type(descriptionBox(form), 'New *body*')
  fireEvent.click(form.getByRole('button', { name: 'Save' }))
  const alert = await form.findByRole('alert')
  expect(alert.textContent).toBe('title must not be blank')
  expect(alert.closest('form')).toBe(form.getByRole('form', { name: 'Edit #14' }))
  expect(screen.getAllByRole('alert')).toEqual([alert])
  expect(popover.hidePopover).not.toHaveBeenCalled()
  expect(titleBox(form).value).toBe('x')
  expect(descriptionBox(form).value).toBe('New *body*')
  expect(form.getByRole('button', { name: 'Save' })).toBeTruthy()
  expect(status().textContent).toBe('')
  expect(loads(fetch)).toBe(1)
})

test('048 FE6: a poll that lands while the Edit form is open leaves the typed Title and Description as they were', async () => {
  vi.useFakeTimers()
  const responses = { [`GET ${BOARD}`]: [200, board({ backlog: [CSV] })] }
  const fetch = mockFetch(responses)
  renderAt('/projects/3')
  await advance(0)
  const form = within(newTask())
  pick(14, 'Edit')
  type(titleBox(form), 'Export CSV v2')
  type(descriptionBox(form), 'Typed *here*')
  responses[`GET ${BOARD}`] = [200, board({ backlog: [{ ...CSV, title: 'Renamed elsewhere', description_md: 'Changed elsewhere' }] })]
  await advance(3000)
  expect(loads(fetch)).toBe(2)
  expect(screen.getByRole('link', { name: '#14 Renamed elsewhere' })).toBeTruthy()
  expect(form.getByRole('form', { name: 'Edit #14' })).toBeTruthy()
  expect(titleBox(form).value).toBe('Export CSV v2')
  expect(descriptionBox(form).value).toBe('Typed *here*')
})

test('048 FE7: + New task clicked over an Edit keeps the popover open on the empty create form, which posts and never patches', async () => {
  const { fetch, form } = await editing({ 'POST /api/projects/3/tasks': [201, { id: 15, status: 'backlog' }] })
  type(titleBox(form), 'Changed')
  const plus = screen.getByRole('button', { name: '+ New task' })
  expect(fireEvent.click(plus)).toBe(false) // canceled, so the native toggle doesn't close the popover
  expect(form.queryByRole('form', { name: 'Edit #14' })).toBeNull()
  expect(form.queryByText('Edit #14')).toBeNull()
  expect(titleBox(form).value).toBe('')
  expect(descriptionBox(form).value).toBe('')
  expect(document.activeElement).toBe(titleBox(form))
  expect(form.queryByRole('button', { name: 'Save' })).toBeNull()
  expect(fireEvent.click(plus)).toBe(true) // in create mode it toggles natively, as before
  type(titleBox(form), 'Import CSV')
  fireEvent.click(form.getByRole('button', { name: 'Add task' }))
  await waitFor(() => expect(loads(fetch)).toBe(2))
  expect(sent(fetch, 'POST', '/api/projects/3/tasks')).toEqual({ title: 'Import CSV', description_md: '' })
  expect(fetch.mock.calls.filter(([, init]) => init?.method === 'PATCH')).toEqual([])
})

test('048 FE8: Delete opens a modal <dialog> through showModal, named Delete #14 Export CSV?, with the Q8 text, Cancel, and a danger Delete', async () => {
  let shown
  const showModal = vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function showModal() {
    shown = this.textContent
    this.open = true
  })
  await open(board({ backlog: [CSV] }))
  expect(screen.queryByRole('dialog')).toBeNull()
  pick(14, 'Delete')
  expect(showModal).toHaveBeenCalledOnce()
  expect(shown).toContain('Delete #14 Export CSV?') // its body rendered first, so showModal can focus Cancel
  const dialog = screen.getByRole('dialog', { name: 'Delete #14 Export CSV?' })
  expect(dialog.tagName).toBe('DIALOG')
  expect(within(dialog).getByText(Q8)).toBeTruthy()
  expect(within(dialog).getAllByRole('button').map((b) => b.textContent)).toEqual(['Cancel', 'Delete'])
  expect(document.getElementById(dialog.getAttribute('aria-describedby')).textContent).toBe(Q8) // round-1 review-ui nit
  const remove = within(dialog).getByRole('button', { name: 'Delete' })
  expect(remove.className).toMatch(cls('bg-danger'))
  expect(remove.className).toMatch(cls('text-surface'))
})

test("048 FE9: the dialog's Delete sends DELETE, closes, reloads without the card, says Deleted #14, and focuses + New task", async () => {
  const { fetch, responses } = await open(board({ backlog: [CSV, card(15, 'backlog')] }), { 'DELETE /api/tasks/14': [204] })
  responses[`GET ${BOARD}`] = [200, board({ backlog: [card(15, 'backlog')] })]
  pick(14, 'Delete')
  const dialog = screen.getByRole('dialog', { name: 'Delete #14 Export CSV?' })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
  await waitFor(() => expect(loads(fetch)).toBe(2))
  expect(sent(fetch, 'DELETE', '/api/tasks/14')).toBeUndefined()
  expect(dialog.open).toBe(false)
  await waitFor(() => expect(screen.queryByRole('link', { name: '#14 Export CSV' })).toBeNull())
  expect(status().textContent).toBe('Deleted #14 Export CSV.')
  expect(document.activeElement).toBe(screen.getByRole('button', { name: '+ New task' }))
  expect(screen.queryByRole('alert')).toBeNull()
})

test("048 FE10: Cancel, or the dialog closing on Esc, sends nothing and gives focus back to the card's Move button", async () => {
  const { fetch } = await open(board({ backlog: [CSV, card(15, 'backlog')] }), { 'DELETE /api/tasks/15': [204] })
  // a delete first leaves returnValue 'deleted' on the dialog, which the next open must clear
  pick(15, 'Delete')
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }))
  await waitFor(() => expect(loads(fetch)).toBe(2))
  pick(14, 'Delete')
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(moveOf(14))
  document.activeElement.blur()
  pick(14, 'Delete')
  const dialog = screen.getByRole('dialog', { name: 'Delete #14 Export CSV?' })
  act(() => dialog.close()) // what Esc does after its cancel event
  expect(dialog.open).toBe(false)
  expect(document.activeElement).toBe(moveOf(14))
  expect(sends(fetch, 'DELETE', '/api/tasks/14')).toEqual([])
  expect(loads(fetch)).toBe(2)
})

test('048 FE11: a refused delete shows its detail inside the dialog, which stays open; the board alert stays empty', async () => {
  const { fetch } = await open(board({ backlog: [CSV] }), { 'DELETE /api/tasks/14': ACTIVE })
  pick(14, 'Delete')
  const dialog = screen.getByRole('dialog', { name: 'Delete #14 Export CSV?' })
  fireEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
  const alert = await within(dialog).findByRole('alert')
  expect(alert.textContent).toBe('run #41 active')
  expect(screen.getAllByRole('alert')).toEqual([alert])
  expect(dialog.open).toBe(true)
  expect(sent(fetch, 'DELETE', '/api/tasks/14')).toBeUndefined()
  expect(status().textContent).toBe('')
  expect(loads(fetch)).toBe(1)
})

test('048 FE12: Delete is disabled, with why in its title, on the running card only; Edit is enabled on every card', async () => {
  const running = card(13, 'in_progress', { stage: 'build', run: { id: 41, status: 'running' }, started_at: '2026-10-18T01:02:00Z' })
  const stalled = card(16, 'in_progress', { stage: 'build', run: { id: 42, status: 'failed' }, stalled: true })
  await open(board({ ...ALL, in_progress: [running, stalled, ...ALL.in_progress] }))
  expect(within(cardEl(13)).getByText(fullText('● running'))).toBeTruthy()
  for (const id of [1, 2, 3, 13, 16, 7, 12, 9]) {
    const menu = within(menuOf(id))
    expect(menu.getByRole('button', { name: 'Edit', hidden: true }).disabled).toBe(false)
    const remove = menu.getByRole('button', { name: 'Delete', hidden: true })
    expect(remove.disabled).toBe(id === 13)
    expect(remove.getAttribute('title')).toBe(id === 13 ? 'Stop the run to delete this task' : null)
  }
})

/** The toggle event the browser fires as the popover closes on Esc or a click outside; jsdom has no Popover API. */
const closePopover = (popover) => act(() => popover.dispatchEvent(Object.assign(new Event('toggle'), { newState: 'closed' })))

test("048 Q9: an Edit closed by Esc gives focus back to the card's Move button unless focus went elsewhere, and leaves edit mode", async () => {
  const { form, popover } = await editing()
  titleBox(form).focus() // inside the popover, which the browser has just hidden
  closePopover(popover)
  expect(document.activeElement).toBe(moveOf(14))
  expect(form.queryByRole('form', { name: 'Edit #14' })).toBeNull()
  expect(form.getByRole('button', { name: 'Add task' })).toBeTruthy()
  expect(fireEvent.click(screen.getByRole('button', { name: '+ New task' }))).toBe(true) // not canceled: it opens natively
  pick(14, 'Edit')
  const elsewhere = screen.getByRole('button', { name: 'Run next ▶' }) // a click outside that took focus keeps it
  elsewhere.focus()
  closePopover(popover)
  expect(document.activeElement).toBe(elsewhere)
})

test('048 round-1 review-ui: + New task over an Edit, then Esc, gives focus to + New task, not body', async () => {
  const { popover } = await editing()
  const plus = screen.getByRole('button', { name: '+ New task' })
  fireEvent.click(plus)
  document.activeElement.blur() // the browser's focus fixup once the popover is hidden
  expect(document.activeElement).toBe(document.body)
  closePopover(popover)
  expect(document.activeElement).toBe(plus)
})

// --- 094: blocked cards ------------------------------------------------------------------

const dep = (id, status) => ({ id, title: `Task ${id}`, status })
/** A card waiting on #12 (backlog), #13 (done), and #14 (in progress). */
const blockedCard = (id, status, extra = {}) =>
  card(id, status, { blocked: true, blocked_by: [dep(12, 'backlog'), dep(13, 'done'), dep(14, 'in_progress')], blocks: [], ...extra })
/** The card's badge: the line with the lock, or null. */
const badge = (id) => cardEl(id).querySelector('svg')?.closest('p') ?? null
/** An element's text without the tooltips in it. */
function visible(el) {
  const copy = el.cloneNode(true)
  for (const tip of copy.querySelectorAll('[role="tooltip"]')) tip.remove()
  return copy.textContent
}

test('094 AC22: a blocked card in Backlog, In progress, or Review shows a hidden lock and Blocked by its open blockers, muted without opacity', async () => {
  await open(board({
    backlog: [blockedCard(15, 'backlog')],
    in_progress: [blockedCard(16, 'in_progress', { stage: 'build' })],
    review: [blockedCard(17, 'review', { stage: 'human_review', waiting: true })],
  }))
  for (const id of [15, 16, 17]) {
    const line = badge(id)
    expect(line.querySelector('svg').getAttribute('aria-hidden')).toBe('true')
    expect(visible(line)).toBe('Blocked by #12, #14') // #13 is done
    expect(cardEl(id).className).toMatch(cls('bg-raised'))
    expect(cardEl(id).className).not.toMatch(cls('bg-surface'))
    expect(cardEl(id).className).not.toMatch(/(^|\s)opacity-/)
    expect(line.className).not.toMatch(/opacity-/)
  }
  expect(within(cardEl(15)).getByRole('button', { name: 'Run' }).disabled).toBe(false) // Q10: the server's 409 decides
})

test('094 AC23: each blocker id links to its task; its title and status are the link\'s description, in the DOM, shown on hover or focus', async () => {
  await open(board({ backlog: [blockedCard(15, 'backlog')] }))
  const links = within(badge(15)).getAllByRole('link')
  expect(links.map((a) => [a.textContent, a.getAttribute('href')])).toEqual([['#12', '/tasks/12'], ['#14', '/tasks/14']])
  const tips = links.map((a) => document.getElementById(a.getAttribute('aria-describedby')))
  expect(tips.map((tip) => tip.textContent)).toEqual(['Task 12 · Backlog', 'Task 14 · In progress'])
  for (const [i, tip] of tips.entries()) {
    expect(tip.getAttribute('role')).toBe('tooltip')
    expect(links[i].parentElement.contains(tip)).toBe(true) // its group, which hover or focus within reveals
    for (const name of ['invisible', 'group-hover:visible', 'group-focus-within:visible']) expect(tip.className).toMatch(cls(name))
  }
  expect(within(badge(15)).getByRole('link', { name: '#12' })).toBe(links[0]) // the name stays the id
})

test('094 AC24: a ready card and every Done card show no badge and keep the surface look', async () => {
  await open(board({
    backlog: [card(15, 'backlog', { blocked: false, blocked_by: [dep(13, 'done')], blocks: [] })],
    done: [blockedCard(18, 'done')],
  }))
  for (const id of [15, 18]) {
    expect(badge(id)).toBeNull()
    expect(cardEl(id).textContent).not.toContain('Blocked by')
    expect(cardEl(id).className).toMatch(cls('bg-surface'))
  }
})
