import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { FactoryResult } from '../../components/FactoryResult.jsx'
import { fetched, fullText, mockFetch, renderAt } from '../../test/render.jsx'

const PROJECT = {
  id: 3, name: 'api', path: '/Users/me/api', default_branch: 'main', workspace_id: 2, workspace: 'personal',
  remote_url: 'git@github.com:me/api.git', test_cmd: 'pytest -q',
}
const WORKSPACES = [{ id: 2, name: 'personal', projects: 1 }, { id: 4, name: 'work', projects: 0 }]
const BOARD = '/api/pages/projects/3'
const HINT = "factory isn't committed on main: Create factory in the project's Settings, then commit it on main"

/** The board view-model (042's API contract), with no cards: Settings reads only the project and factory. */
const board = (extra = {}) => ({
  project: PROJECT, factory: 'ready', hint: null, can_run: true, workspaces: WORKSPACES,
  columns: { backlog: [], in_progress: [], review: [], done: [] }, ...extra,
})

afterEach(() => {
  vi.useRealTimers()
})

/** Renders /projects/3/settings with `page` as its view-model; mutate `responses` to change later replies. */
async function open(page, more = {}, at = '/projects/3/settings') {
  const responses = { [`GET ${BOARD}`]: [200, page], ...more }
  const fetch = mockFetch(responses)
  const view = renderAt(at)
  await screen.findByRole('heading', { level: 1 })
  return { fetch, responses, ...view }
}

const loads = (fetch) => fetched(fetch).filter((url) => url === BOARD).length
const section = (name) => screen.getByRole('region', { name })
const sends = (fetch, method, url) => fetch.mock.calls.filter(([u, init]) => u === url && init?.method === method)
const advance = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))

/** The one `method url` call: asserts its X-Requested-By and returns its JSON body. */
function sent(fetch, method, url) {
  const calls = sends(fetch, method, url)
  expect(calls).toHaveLength(1)
  const [, init] = calls[0]
  expect(init.headers['X-Requested-By']).toBe('fctl')
  return init.body === undefined ? undefined : JSON.parse(init.body)
}

// --- Loading and details -----------------------------------------------------------------

test('FE25: the page fetches the board view-model once, and 10 s fetch nothing more', async () => {
  vi.useFakeTimers()
  const fetch = mockFetch({ [`GET ${BOARD}`]: [200, board()] })
  renderAt('/projects/3/settings')
  await advance(0)
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('api · personal')
  const pages = () => fetched(fetch).filter((url) => !url.startsWith('/api/pages/sidebar') && url !== '/api/auth')
  expect(pages()).toEqual([BOARD])
  await advance(10_000)
  expect(pages()).toEqual([BOARD])
})

const Q5 =
  'Path, remote, and default branch come from fctl connect. Rerunning it in the repo also resets the name, and the test command when it passes one.'
const nameBox = () => within(section('Repository')).getByRole('textbox', { name: 'Name' })
const testBox = () => within(section('Repository')).getByRole('textbox', { name: 'Test command' })

test('049 FE16 (042 FE26): Repository opens with a Name and Test command form with Save, then path, remote, and default branch as text', async () => {
  const { unmount } = await open(board())
  const repo = within(section('Repository'))
  const facts = () => {
    const dl = section('Repository').querySelector('dl')
    return [...dl.querySelectorAll('dt')].map((dt) => [dt.textContent, dt.nextElementSibling.textContent])
  }
  expect([nameBox().value, testBox().value]).toEqual(['api', 'pytest -q'])
  const save = repo.getByRole('button', { name: 'Save' })
  expect(save.closest('form')).toBe(nameBox().closest('form'))
  expect(testBox().closest('form')).toBe(nameBox().closest('form'))
  expect(facts()).toEqual([
    ['Path', '/Users/me/api'],
    ['Remote', 'git@github.com:me/api.git'],
    ['Default branch', 'main'],
  ])
  // Q15: the form comes first, above the read-only rows; those have no field
  const dl = section('Repository').querySelector('dl')
  expect(save.compareDocumentPosition(dl) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(dl.querySelectorAll('input, textarea, select')).toHaveLength(0)
  expect(repo.getByText(fullText(Q5)).querySelector('code').textContent).toBe('fctl connect')
  unmount()
  await open(board({ project: { ...PROJECT, remote_url: null, test_cmd: null } }))
  expect(testBox().value).toBe('')
  expect(facts()).toEqual([
    ['Path', '/Users/me/api'],
    ['Remote', 'none'],
    ['Default branch', 'main'],
  ])
})

test('049 FE17: Save sends PATCH {name, test_cmd} as typed; on 200 the page reloads, the header follows, and the sidebar is fetched again', async () => {
  const { fetch, responses } = await open(board(), {
    'PATCH /api/projects/3': [200, { id: 3, workspace_id: 2, name: 'api2', test_cmd: null }],
  })
  const sidebarLoads = () => fetched(fetch).filter((url) => url === '/api/pages/sidebar').length
  await waitFor(() => expect(sidebarLoads()).toBe(1))
  fireEvent.change(nameBox(), { target: { value: '  api2 ' } })
  fireEvent.change(testBox(), { target: { value: '   ' } })
  responses[`GET ${BOARD}`] = [200, board({ project: { ...PROJECT, name: 'api2', test_cmd: null } })]
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByRole('heading', { level: 1, name: 'api2 · personal' })).toBeTruthy()
  expect(sent(fetch, 'PATCH', '/api/projects/3')).toEqual({ name: '  api2 ', test_cmd: '   ' })
  expect(loads(fetch)).toBe(2)
  await waitFor(() => expect(sidebarLoads()).toBe(2))
  expect([nameBox().value, testBox().value]).toEqual(['api2', '']) // what the server stored
  expect(within(section('Repository')).getByText('Saved.')).toBeTruthy()
})

test('049 FE18: a refused Save shows its detail in the form, which keeps what was typed', async () => {
  const { fetch } = await open(board(), { 'PATCH /api/projects/3': [422, { detail: 'name must not be blank' }] })
  fireEvent.change(nameBox(), { target: { value: '   ' } })
  fireEvent.change(testBox(), { target: { value: 'make test' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe('name must not be blank')
  expect(alert.closest('form')).toBe(nameBox().closest('form'))
  expect([nameBox().value, testBox().value]).toEqual(['   ', 'make test'])
  expect(loads(fetch)).toBe(1)
  expect(screen.queryByText('Saved.')).toBeNull()
})

const PROJECT_TEXT =
  'This removes its tasks, with their runs, rounds and their files, verdicts, comments, decisions, status history, and ' +
  'transcript records, from the app. The repo, its worktrees and branches, run logs, and copied transcript files stay on disk.'

test('049 FE19: the last section, Danger zone, has a danger Delete project that opens the dialog; confirming deletes and opens /workspaces/2', async () => {
  const { fetch, router } = await open(board(), { 'DELETE /api/projects/3': [204] })
  const sections = screen.getAllByRole('region')
  expect(sections.at(-1)).toBe(section('Danger zone'))
  const button = within(section('Danger zone')).getByRole('button', { name: 'Delete project' })
  expect(button.className).toMatch(/(^|\s)bg-danger(\s|$)/)
  expect(screen.queryByRole('dialog')).toBeNull()
  fireEvent.click(button)
  const dialog = screen.getByRole('dialog', { name: 'Delete project api?' })
  expect(document.getElementById(dialog.getAttribute('aria-describedby')).textContent).toBe(PROJECT_TEXT)
  expect(within(dialog).getAllByRole('button').map((b) => b.textContent)).toEqual(['Cancel', 'Delete'])
  fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(sends(fetch, 'DELETE', '/api/projects/3')).toEqual([])
  fireEvent.click(button)
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }))
  await waitFor(() => expect(router.state.location.pathname).toBe('/workspaces/2'))
  expect(sent(fetch, 'DELETE', '/api/projects/3')).toBeUndefined()
})

test('FE27: ready has no Create factory; uncommitted and none show the unticked checkbox, the button, and the hint', async () => {
  const ready = await open(board())
  expect(screen.queryByRole('button', { name: 'Create factory' })).toBeNull()
  expect(screen.queryByRole('checkbox', { name: 'Overwrite existing files' })).toBeNull()
  ready.unmount()
  for (const [factory, hint] of [['uncommitted', null], ['none', HINT]]) {
    const { unmount } = await open(board({ factory, hint, can_run: false }))
    const factorySection = within(section('Factory'))
    expect(factorySection.getByRole('checkbox', { name: 'Overwrite existing files' }).checked).toBe(false)
    expect(factorySection.getByRole('button', { name: 'Create factory' })).toBeTruthy()
    if (hint) expect(factorySection.getByText(hint)).toBeTruthy()
    else expect(section('Factory').textContent).not.toContain("isn't committed")
    unmount()
  }
})

// --- Create factory (board AC24–AC26, moved) --------------------------------------------

const factoryOut = (written, skipped) => [200, { written, skipped, commit_hint: 'git add .claude && git commit -m "Add factory"' }]

test('FE28 (AC24): Create factory sends overwrite false, or true when ticked', async () => {
  for (const overwrite of [false, true]) {
    const { fetch, unmount } = await open(board({ factory: 'none', can_run: false }), {
      'POST /api/projects/3/factory': factoryOut(['.claude/a.md'], []),
    })
    if (overwrite) fireEvent.click(screen.getByRole('checkbox', { name: 'Overwrite existing files' }))
    fireEvent.click(screen.getByRole('button', { name: 'Create factory' }))
    await screen.findByText('Commit them so runs can see the factory:')
    expect(sent(fetch, 'POST', '/api/projects/3/factory')).toEqual({ overwrite })
    unmount()
  }
})

test('FE28 (AC25): the result lists what was written or skipped, the commit hint, and reloads', async () => {
  const skipped8 = Array.from({ length: 8 }, (_, i) => `.claude/agents/s${i}.md`)
  const cases = [
    [['.claude/a.md', '.claude/b.md'], [], 'Wrote 2 files:', null],
    [[], skipped8, null, 'Skipped 8 existing files (tick Overwrite to replace them):'],
    [['.claude/a.md'], ['.claude/b.md'], 'Wrote 1 file:', 'Skipped 1 existing file (tick Overwrite to replace them):'],
  ]
  for (const [written, skipped, wrote, skip] of cases) {
    const { fetch, unmount } = await open(board({ factory: 'uncommitted', can_run: false }), {
      'POST /api/projects/3/factory': factoryOut(written, skipped),
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create factory' }))
    await screen.findByText('Commit them so runs can see the factory:')
    if (wrote) expect(screen.getByText(wrote)).toBeTruthy()
    else expect(screen.queryByText(/^Wrote/)).toBeNull()
    if (skip) expect(screen.getByText(skip)).toBeTruthy()
    else expect(screen.queryByText(/^Skipped/)).toBeNull()
    const result = section('Factory').querySelector('[aria-live="polite"]')
    expect([...result.querySelectorAll('li > code')].map((c) => c.textContent)).toEqual([...written, ...skipped])
    expect(result.querySelector('pre > code').textContent).toBe('git add .claude && git commit -m "Add factory"')
    await waitFor(() => expect(loads(fetch)).toBe(2))
    unmount()
  }
})

test('052 FE12: Create factory\'s result is the shared FactoryResult\'s markup', async () => {
  const [, out] = factoryOut(['.claude/a.md'], ['.claude/b.md'])
  await open(board({ factory: 'none', can_run: false }), { 'POST /api/projects/3/factory': [200, out] })
  fireEvent.click(screen.getByRole('button', { name: 'Create factory' }))
  await screen.findByText('Wrote 1 file:')
  const result = section('Factory').querySelector('[aria-live="polite"]')
  const { container } = render(<FactoryResult out={out} />)
  expect(result.innerHTML).toBe(container.innerHTML)
})

test('FE29 (AC26): a refused Create factory shows its detail beside the form, with no file lists', async () => {
  const { fetch } = await open(board({ factory: 'none', can_run: false }), {
    'POST /api/projects/3/factory': [409, { detail: 'no test command: run fctl connect --test-cmd' }],
  })
  fireEvent.click(screen.getByRole('button', { name: 'Create factory' }))
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe('no test command: run fctl connect --test-cmd')
  expect(alert.closest('section')).toBe(screen.getByRole('button', { name: 'Create factory' }).closest('section'))
  expect(screen.queryByText(/^(Wrote|Skipped|Commit them)/)).toBeNull()
  expect(section('Factory').querySelector('li > code, pre')).toBeNull()
  expect(loads(fetch)).toBe(1)
})

// --- Import (032 AC47–AC49, moved) -------------------------------------------------------

const IMPORT = '/api/projects/3/import'
const IMPORTED = { task_id: 12, title: 'Rate-limit <login>', import_key: 'task:7@2026-10-17T10:03:00Z', created: true,
  status: 'backlog', rounds: 2, transcripts: 0 }
const bundleFile = () => new File(['PK\x05\x06'], 'task-12.zip', { type: 'application/zip' })

/** Chooses `file` in the Import input and clicks Import. */
function importFile(file) {
  fireEvent.change(screen.getByLabelText('Task bundle (.zip)'), { target: { files: [file] } })
  fireEvent.click(screen.getByRole('button', { name: 'Import' }))
}

test('FE30 (032 AC47): Import is disabled until a file is chosen, then sends one POST with the File itself', async () => {
  const { fetch } = await open(board(), { [`POST ${IMPORT}`]: [200, IMPORTED] })
  const input = screen.getByLabelText('Task bundle (.zip)')
  expect([input.type, input.getAttribute('accept')]).toEqual(['file', '.zip,application/zip'])
  expect(input.closest('section')).toBe(section('Import'))
  expect(screen.getByRole('button', { name: 'Import' }).disabled).toBe(true)
  const file = bundleFile()
  fireEvent.change(input, { target: { files: [file] } })
  expect(screen.getByRole('button', { name: 'Import' }).disabled).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: 'Import' }))
  await screen.findByText(fullText('Imported #12 Rate-limit <login>'))
  const calls = sends(fetch, 'POST', IMPORT)
  expect(calls).toHaveLength(1)
  expect(calls[0][1].body).toBe(file)
  expect(calls[0][1].headers).toEqual({ 'X-Requested-By': 'fctl' })
  expect(fetch.mock.calls.filter(([, init]) => init?.method && init.method !== 'GET')).toHaveLength(1)
})

test('FE30 (032 AC48): a 200 shows Imported #12 title linking to the task and reloads', async () => {
  const { fetch } = await open(board(), { [`POST ${IMPORT}`]: [200, IMPORTED] })
  importFile(bundleFile())
  const line = await screen.findByText(fullText('Imported #12 Rate-limit <login>'))
  expect(line.closest('[aria-live]')).toBeTruthy()
  expect(within(line).getByRole('link').getAttribute('href')).toBe('/tasks/12')
  await waitFor(() => expect(loads(fetch)).toBe(2))
})

test('FE30 (032 AC49): a 413 or 422 shows its detail, and the page stays', async () => {
  for (const [status, detail] of [[413, 'bundle over 50 MB'], [422, 'unknown bundle entry "notes.txt"']]) {
    const { fetch, unmount } = await open(board(), { [`POST ${IMPORT}`]: [status, { detail }] })
    importFile(bundleFile())
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe(detail)
    expect(alert.closest('[aria-live]')).toBeTruthy()
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('api · personal')
    expect(section('Repository')).toBeTruthy()
    expect(screen.queryByText(/^Imported/)).toBeNull()
    expect(loads(fetch)).toBe(1)
    unmount()
  }
})

// --- Move (board AC27–AC28, moved) -------------------------------------------------------

test('FE31 (AC27), 049 Q13: Move lists the workspaces, patches the chosen one, the header follows the reload, and so does the sidebar', async () => {
  const { fetch, responses } = await open(board(), {
    'PATCH /api/projects/3': [200, { id: 3, workspace_id: 4, name: 'api', test_cmd: 'pytest -q' }],
  })
  const select = screen.getByRole('combobox', { name: 'Workspace' })
  expect([...select.options].map((o) => [o.textContent, o.selected])).toEqual([['personal', true], ['work', false]])
  responses[`GET ${BOARD}`] = [200, board({ project: { ...PROJECT, workspace_id: 4, workspace: 'work' } })]
  fireEvent.change(select, { target: { value: '4' } })
  fireEvent.click(screen.getByRole('button', { name: 'Move' }))
  const h1 = await screen.findByRole('heading', { level: 1, name: 'api · work' })
  expect(within(h1).getByRole('link', { name: 'work' }).getAttribute('href')).toBe('/workspaces/4')
  expect(sent(fetch, 'PATCH', '/api/projects/3')).toEqual({ workspace_id: 4 })
  expect(loads(fetch)).toBe(2)
  await waitFor(() => expect(fetched(fetch).filter((url) => url === '/api/pages/sidebar')).toHaveLength(2))
})

test('FE31 (AC28): a refused move shows its detail in the Move form', async () => {
  await open(board(), { 'PATCH /api/projects/3': [404, { detail: 'Not Found' }] })
  fireEvent.change(screen.getByRole('combobox', { name: 'Workspace' }), { target: { value: '4' } })
  fireEvent.click(screen.getByRole('button', { name: 'Move' }))
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe('Not Found')
  expect(alert.closest('form')).toBe(screen.getByRole('button', { name: 'Move' }).closest('form'))
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('api · personal')
})

// --- Title, 404, another project ---------------------------------------------------------

test('FE32: the title; a 404 is the not-found state; /projects/4/settings resets Move and clears results', async () => {
  const { router, responses } = await open(board(), { [`POST ${IMPORT}`]: [200, IMPORTED] })
  await waitFor(() => expect(document.title).toBe('api · Settings · Claude Factories'))
  importFile(bundleFile())
  await screen.findByText(fullText('Imported #12 Rate-limit <login>'))
  fireEvent.change(screen.getByRole('combobox', { name: 'Workspace' }), { target: { value: '4' } })

  // same workspace as project 3, so only a reset per project puts the select back on it
  responses['GET /api/pages/projects/4'] = [200, board({ project: { ...PROJECT, id: 4, name: 'billing' } })]
  await act(() => router.navigate('/projects/4/settings'))
  await screen.findByRole('heading', { level: 1, name: 'billing · personal' })
  expect(screen.getByRole('combobox', { name: 'Workspace' }).value).toBe('2')
  expect(screen.queryByText(/^Imported/)).toBeNull()
  expect(screen.getByRole('button', { name: 'Import' }).disabled).toBe(true)

  await act(() => router.navigate('/projects/99/settings'))
  expect(await screen.findByRole('heading', { level: 1, name: 'Not Found' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Go to the dashboard' }).getAttribute('href')).toBe('/')
})
