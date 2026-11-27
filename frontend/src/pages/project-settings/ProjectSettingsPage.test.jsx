import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { FactoryResult } from '../../components/FactoryResult.jsx'
import { fetched, fullText, mockFetch, renderAt } from '../../test/render.jsx'
import { openSelect, pick } from '../../test/select.js'

const PROJECT = {
  id: 3, name: 'api', path: '/home/me/api', default_branch: 'main', workspace_id: 2, workspace: 'personal',
  remote_url: 'git@github.com:me/api.git', test_cmd: 'pytest -q', github_label: null, github_repo: 'me/api',
  github_hint: null,
}
const WORKSPACES = [{ id: 2, name: 'personal', projects: 1 }, { id: 4, name: 'work', projects: 0 }]
const BOARD = '/api/pages/projects/3'
const LEGACY_HINT = 'this repo runs the file-based /factory loop: Create factory with Overwrite, then commit it on main'
const OVERWRITE = "Overwrite replaces SKILL.md and the 7 agents with the app's templates."
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
  'Remote and default branch come from fctl connect. Rerunning it in the repo also resets the name, and the test command when it passes one. If the checkout moves, change the path here.'
const nameBox = () => within(section('Repository')).getByRole('textbox', { name: 'Name' })
const testBox = () => within(section('Repository')).getByRole('textbox', { name: 'Test command' })
const pathBox = () => within(section('Repository')).getByRole('textbox', { name: 'Path' })
const changePath = () => within(section('Repository')).getByRole('button', { name: 'Change path' })

test('049 FE16 (042 FE26), 119 AC16, AC18: Repository opens with a Name and Test command form with Save, a Path form, then remote and default branch as text', async () => {
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
    ['Remote', 'git@github.com:me/api.git'],
    ['Default branch', 'main'],
  ])
  // 119 AC16: the path form, its own, between the Name form and the read-only rows
  expect(pathBox().value).toBe('/home/me/api')
  expect(changePath().closest('form')).toBe(pathBox().closest('form'))
  expect(pathBox().closest('form')).not.toBe(nameBox().closest('form'))
  // Q15: the forms come first, above the read-only rows; those have no field
  const dl = section('Repository').querySelector('dl')
  expect(save.compareDocumentPosition(pathBox()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(pathBox().compareDocumentPosition(dl) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(dl.querySelectorAll('input, textarea, select')).toHaveLength(0)
  expect(repo.getByText(fullText(Q5)).querySelector('code').textContent).toBe('fctl connect')
  unmount()
  await open(board({ project: { ...PROJECT, remote_url: null, test_cmd: null } }))
  expect(testBox().value).toBe('')
  expect(facts()).toEqual([
    ['Remote', 'none'],
    ['Default branch', 'main'],
  ])
})

test('119 AC16: Change path sends PATCH {path} as typed; on 200 the page reloads and the input shows the stored path', async () => {
  const { fetch, responses } = await open(board(), {
    'PATCH /api/projects/3': [200, { id: 3, workspace_id: 2, name: 'api', path: '/srv/api', test_cmd: 'pytest -q' }],
  })
  fireEvent.change(pathBox(), { target: { value: '/srv/link/api' } })
  responses[`GET ${BOARD}`] = [200, board({ project: { ...PROJECT, path: '/srv/api' } })]
  fireEvent.click(changePath())
  await waitFor(() => expect(pathBox().value).toBe('/srv/api'))
  expect(sent(fetch, 'PATCH', '/api/projects/3')).toEqual({ path: '/srv/link/api' })
  expect(loads(fetch)).toBe(2)
  expect(within(section('Repository')).queryByRole('alert')).toBeNull()
})

test('119 AC17: a refused path change shows its detail in the path form, which keeps what was typed', async () => {
  const detail = '/srv/api/src is not a main checkout; use /srv/api'
  const { fetch } = await open(board(), { 'PATCH /api/projects/3': [422, { detail }] })
  fireEvent.change(pathBox(), { target: { value: '/srv/api/src' } })
  fireEvent.click(changePath())
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe(detail)
  expect(alert.closest('form')).toBe(pathBox().closest('form'))
  expect(pathBox().value).toBe('/srv/api/src')
  expect(loads(fetch)).toBe(1)
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
  fireEvent.click(within(section('Repository')).getByRole('button', { name: 'Save' }))
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
  fireEvent.click(within(section('Repository')).getByRole('button', { name: 'Save' }))
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

test('059 FE4: legacy shows the hint, the Overwrite note, the files on disk in order, then Create factory unticked', async () => {
  const files = ['.claude/skills/factory/SKILL.md', '.claude/agents/spec-writer.md']
  await open(board({ factory: 'legacy', hint: LEGACY_HINT, can_run: false, factory_files: files }))
  expect(within(screen.getByRole('main')).getByRole('link', { name: 'Factory: legacy' }).getAttribute('href')).toBe(
    '/projects/3/settings',
  )
  const factorySection = within(section('Factory'))
  const hint = factorySection.getByText(LEGACY_HINT)
  const note = factorySection.getByText(`${OVERWRITE} These exist now:`)
  const list = section('Factory').querySelector('ul')
  expect([...list.querySelectorAll('li > code')].map((c) => c.textContent)).toEqual(files)
  const create = factorySection.getByRole('button', { name: 'Create factory' })
  expect(factorySection.getByRole('checkbox', { name: 'Overwrite existing files' }).checked).toBe(false)
  const order = [hint, note, list, create]
  for (let i = 1; i < order.length; i++) {
    expect(order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  }
})

test('059 FE5: legacy with no factory files says none of them exist, with no list', async () => {
  await open(board({ factory: 'legacy', hint: LEGACY_HINT, can_run: false, factory_files: [] }))
  expect(within(section('Factory')).getByText(`${OVERWRITE} None of them exist now.`)).toBeTruthy()
  expect(section('Factory').querySelector('ul')).toBeNull()
})

test('059 FE6: uncommitted, none, and ready have no Overwrite note', async () => {
  const files = ['.claude/skills/factory/SKILL.md']
  for (const factory of ['uncommitted', 'none', 'ready']) {
    const hint = factory === 'none' ? HINT : null
    const { unmount } = await open(board({ factory, hint, can_run: factory === 'ready', factory_files: files }))
    expect(section('Factory').textContent).not.toContain('Overwrite replaces')
    expect(section('Factory').querySelector('ul')).toBeNull()
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

// --- Sync factory/ (058) -----------------------------------------------------------------

const SYNC = '/api/projects/3/import-factory'
const SYNC_NOTE =
  "The repo's factory/board.json and factory/backlog.md as tasks. The board also syncs them when either file changes."
const job = (n, created) => ({ job: `05${n}-job`, task_id: 70 + n, created, rounds: 0, transcripts: 0 })
const SYNCED = { imported: [job(1, true), job(2, false), job(3, false)], skipped: 1 }
const syncButton = () => within(section('Import')).getByRole('button', { name: 'Sync factory/' })

test('058 FE1: Import has Sync factory/ under its muted note; a click sends one POST import-factory with the body {}', async () => {
  const { fetch } = await open(board(), { [`POST ${SYNC}`]: [200, SYNCED] })
  const note = within(section('Import')).getByText(fullText(SYNC_NOTE))
  expect(note.className).toMatch(/(^|\s)text-muted(\s|$)/)
  expect([...note.querySelectorAll('code')].map((c) => c.textContent)).toEqual(['factory/board.json', 'factory/backlog.md'])
  expect(note.compareDocumentPosition(syncButton()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  fireEvent.click(syncButton())
  await screen.findByText(/^Synced factory\//)
  expect(sent(fetch, 'POST', SYNC)).toEqual({})
  expect(fetch.mock.calls.filter(([, init]) => init?.method && init.method !== 'GET')).toHaveLength(1)
})

test('058 FE2: a 200 says Synced factory/: 1 new, 2 updated, 1 skipped in a polite live region and reloads the page', async () => {
  const { fetch } = await open(board(), { [`POST ${SYNC}`]: [200, SYNCED] })
  fireEvent.click(syncButton())
  const line = await screen.findByText('Synced factory/: 1 new, 2 updated, 1 skipped')
  expect(line.closest('[aria-live]').getAttribute('aria-live')).toBe('polite')
  expect(line.closest('section')).toBe(section('Import'))
  expect(screen.queryByRole('alert')).toBeNull()
  await waitFor(() => expect(loads(fetch)).toBe(2))
})

test('058 FE3: a refused sync shows its detail as an alert in Import and does not reload', async () => {
  const detail = 'factory:001-setup is imported in project #2'
  const { fetch } = await open(board(), { [`POST ${SYNC}`]: [409, { detail }] })
  fireEvent.click(syncButton())
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe(detail)
  expect(alert.closest('section')).toBe(section('Import'))
  expect(screen.queryByText(/^Synced/)).toBeNull()
  await waitFor(() => expect(syncButton().disabled).toBe(false))
  expect(loads(fetch)).toBe(1)
})

test('058 FE4: Sync factory/ is disabled while its request is pending, and enabled again after', async () => {
  const { fetch } = await open(board(), { [`POST ${SYNC}`]: [200, SYNCED] })
  const reply = fetch.getMockImplementation()
  let release
  const gate = new Promise((resolve) => (release = resolve))
  fetch.mockImplementation((url, init) => (url === SYNC ? gate.then(() => reply(url, init)) : reply(url, init)))
  expect(syncButton().disabled).toBe(false)
  fireEvent.click(syncButton())
  expect(syncButton().disabled).toBe(true)
  release()
  await screen.findByText('Synced factory/: 1 new, 2 updated, 1 skipped')
  expect(syncButton().disabled).toBe(false)
  expect(sends(fetch, 'POST', SYNC)).toHaveLength(1)
})

// --- GitHub issues (108) -----------------------------------------------------------------

const ISSUES = '/api/projects/3/github-issues/sync'
const ISSUES_SYNCED = { new: 2, updated: 1, skipped: 5 }
const ISSUES_LINE = 'Synced GitHub issues: 2 new, 1 updated, 5 skipped'
const github = () => within(section('GitHub issues'))
const labelBox = () => github().getByRole('textbox', { name: 'Label' })
const syncNow = () => github().getByRole('button', { name: 'Sync now' })

test('108 AC27: GitHub issues follows Import, with a Label prefilled from github_label; its Save sends PATCH {github_label}, says Saved. and reloads', async () => {
  const project = { ...PROJECT, github_label: 'bug' }
  const { fetch, responses } = await open(board({ project }), {
    'PATCH /api/projects/3': [200, { id: 3, workspace_id: 2, name: 'api', test_cmd: 'pytest -q', github_label: 'ui' }],
  })
  const regions = screen.getAllByRole('region')
  expect(regions.indexOf(section('GitHub issues'))).toBe(regions.indexOf(section('Import')) + 1)
  expect(labelBox().value).toBe('bug')
  expect(labelBox().getAttribute('placeholder')).toBe('all open issues')
  fireEvent.change(labelBox(), { target: { value: ' ui ' } })
  responses[`GET ${BOARD}`] = [200, board({ project: { ...project, github_label: 'ui' } })]
  fireEvent.click(github().getByRole('button', { name: 'Save' }))
  const saved = await github().findByText('Saved.')
  expect(saved.closest('[aria-live]').getAttribute('aria-live')).toBe('polite')
  expect(sent(fetch, 'PATCH', '/api/projects/3')).toEqual({ github_label: ' ui ' })
  await waitFor(() => expect(loads(fetch)).toBe(2))
  expect(labelBox().value).toBe('ui')
})

test('108 AC27: a refused Label save shows as an alert in the section and keeps what was typed', async () => {
  const { fetch } = await open(board(), { 'PATCH /api/projects/3': [422, { detail: 'something is wrong' }] })
  fireEvent.change(labelBox(), { target: { value: 'needs triage' } })
  fireEvent.click(github().getByRole('button', { name: 'Save' }))
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe('something is wrong')
  expect(alert.closest('section')).toBe(section('GitHub issues'))
  expect(labelBox().value).toBe('needs triage')
  expect(github().queryByText('Saved.')).toBeNull()
  expect(loads(fetch)).toBe(1)
})

test('108 AC28: Sync now sends POST github-issues/sync {}, is disabled while pending, and says the counts in a polite live region, then reloads', async () => {
  const { fetch } = await open(board(), { [`POST ${ISSUES}`]: [200, ISSUES_SYNCED] })
  const reply = fetch.getMockImplementation()
  let release
  const gate = new Promise((resolve) => (release = resolve))
  fetch.mockImplementation((url, init) => (url === ISSUES ? gate.then(() => reply(url, init)) : reply(url, init)))
  expect(syncNow().disabled).toBe(false)
  fireEvent.click(syncNow())
  expect(syncNow().disabled).toBe(true)
  release()
  const line = await github().findByText(ISSUES_LINE)
  expect(line.closest('[aria-live]').getAttribute('aria-live')).toBe('polite')
  expect(syncNow().disabled).toBe(false)
  expect(sent(fetch, 'POST', ISSUES)).toEqual({})
  expect(screen.queryByRole('alert')).toBeNull()
  await waitFor(() => expect(loads(fetch)).toBe(2))
})

test('108 AC28: the live region is cleared when a sync starts, so the same result is announced again', async () => {
  const { fetch } = await open(board(), { [`POST ${ISSUES}`]: [200, ISSUES_SYNCED] })
  fireEvent.click(syncNow())
  await github().findByText(ISSUES_LINE)
  const reply = fetch.getMockImplementation()
  let release
  const gate = new Promise((resolve) => (release = resolve))
  fetch.mockImplementation((url, init) => (url === ISSUES ? gate.then(() => reply(url, init)) : reply(url, init)))
  fireEvent.click(syncNow())
  expect(github().queryByText(ISSUES_LINE)).toBeNull()
  release()
  expect(await github().findByText(ISSUES_LINE)).toBeTruthy()
})

test('108 AC29: a refused sync shows its detail as an alert in the section and does not reload', async () => {
  const detail = 'gh is not logged in: run gh auth login. You are not logged into any GitHub hosts.'
  const { fetch } = await open(board(), { [`POST ${ISSUES}`]: [409, { detail }] })
  fireEvent.click(syncNow())
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe(detail)
  expect(alert.closest('section')).toBe(section('GitHub issues'))
  expect(screen.queryByText(/^Synced GitHub/)).toBeNull()
  await waitFor(() => expect(syncNow().disabled).toBe(false))
  expect(loads(fetch)).toBe(1)
})

test('108 AC30: with a github.com origin a muted line names the repo; without one the hint shows and Sync now is disabled', async () => {
  const { unmount } = await open(board())
  const line = github().getByText('Open issues of me/api as Backlog tasks, through your gh login.')
  expect(line.className).toMatch(/(^|\s)text-muted(\s|$)/)
  unmount()
  const hint = "origin isn't on GitHub (gitlab.com); GitHub issues sync needs a github.com origin."
  const { fetch } = await open(board({ project: { ...PROJECT, github_repo: null, github_hint: hint } }))
  expect(github().getByText(hint)).toBeTruthy()
  expect(github().queryByText(/^Open issues of/)).toBeNull()
  expect(syncNow().disabled).toBe(true)
  fireEvent.click(syncNow())
  expect(sends(fetch, 'POST', ISSUES)).toHaveLength(0)
  expect(labelBox().disabled).toBe(false) // the label can still be saved
})

// --- Plane (109) -----------------------------------------------------------------------------

const PLANE_SYNC = '/api/projects/3/plane/sync'
const PLANE_LINE = 'Synced Plane: 2 new, 1 updated, 5 skipped'
const NO_PLANE = { plane_api_url: null, plane_workspace: null, plane_project_id: null, plane_mark_done: false, plane_key_set: false }
const PLANE_SET = { plane_api_url: 'https://plane.example.com', plane_workspace: 'acme', plane_project_id: 'p-1', plane_mark_done: true, plane_key_set: true }
const planeBoard = (plane = NO_PLANE) => board({ project: { ...PROJECT, ...plane } })
const planeSection = () => within(section('Plane'))
const box = (name) => planeSection().getByLabelText(name)
const planeSync = () => planeSection().getByRole('button', { name: 'Sync now' })
const patched = (plane) => [200, { id: 3, workspace_id: 2, name: 'api', test_cmd: 'pytest -q', github_label: null, ...plane }]

test('109 AC17: Plane follows GitHub issues with API URL (default https://api.plane.so), Workspace slug, Project ID, Mark done in Plane, and Save (PATCH, Saved., reload)', async () => {
  const { fetch, responses } = await open(planeBoard(), { 'PATCH /api/projects/3': patched({ ...PLANE_SET, plane_key_set: true }) })
  const regions = screen.getAllByRole('region')
  expect(regions.indexOf(section('Plane'))).toBe(regions.indexOf(section('GitHub issues')) + 1)
  expect(box('API URL').value).toBe('https://api.plane.so')
  expect([box('Workspace slug').value, box('Project ID').value, box('Mark done in Plane').checked]).toEqual(['', '', false])
  fireEvent.change(box('API URL'), { target: { value: 'https://plane.example.com/' } })
  fireEvent.change(box('Workspace slug'), { target: { value: 'acme' } })
  fireEvent.change(box('Project ID'), { target: { value: 'p-1' } })
  fireEvent.change(box('API key'), { target: { value: 'k-123' } })
  fireEvent.click(box('Mark done in Plane'))
  responses[`GET ${BOARD}`] = [200, planeBoard(PLANE_SET)]
  fireEvent.click(planeSection().getByRole('button', { name: 'Save' }))
  const saved = await planeSection().findByText('Saved.')
  expect(saved.closest('[aria-live]').getAttribute('aria-live')).toBe('polite')
  expect(sent(fetch, 'PATCH', '/api/projects/3')).toEqual({
    plane_api_url: 'https://plane.example.com/', plane_workspace: 'acme', plane_project_id: 'p-1', plane_mark_done: true,
    plane_api_key: 'k-123',
  })
  await waitFor(() => expect(loads(fetch)).toBe(2))
  expect(box('API URL').value).toBe('https://plane.example.com')
})

test('109 AC17: a refused Plane save shows as an alert in the section and keeps what was typed', async () => {
  const detail = 'plane_api_url must be an http(s) URL like https://api.plane.so'
  const { fetch } = await open(planeBoard(), { 'PATCH /api/projects/3': [422, { detail }] })
  fireEvent.change(box('API URL'), { target: { value: 'ftp://x' } })
  fireEvent.click(planeSection().getByRole('button', { name: 'Save' }))
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe(detail)
  expect(alert.closest('section')).toBe(section('Plane'))
  expect(box('API URL').value).toBe('ftp://x')
  expect(loads(fetch)).toBe(1)
})

test('109 AC18: the API key is write-only: an empty password input when not set; `API key: set` with Replace and Clear when set', async () => {
  const leak = 'plane_api_LEAK_should_never_render'
  const { unmount } = await open(planeBoard())
  expect(box('API key').type).toBe('password')
  expect(box('API key').value).toBe('')
  unmount()
  const { fetch, responses } = await open(board({ project: { ...PROJECT, ...PLANE_SET, plane_api_key: leak } }), {
    'PATCH /api/projects/3': patched({ ...PLANE_SET }),
  })
  expect(document.body.innerHTML).not.toContain(leak)
  expect(planeSection().getByText('API key: set')).toBeTruthy()
  expect(planeSection().queryByLabelText('API key')).toBeNull()
  fireEvent.click(planeSection().getByRole('button', { name: 'Replace' }))
  expect(box('API key').type).toBe('password')
  expect(box('API key').value).toBe('')
  fireEvent.change(box('API key'), { target: { value: 'new-key' } })
  fireEvent.click(planeSection().getByRole('button', { name: 'Save' }))
  await planeSection().findByText('Saved.')
  expect(sent(fetch, 'PATCH', '/api/projects/3').plane_api_key).toBe('new-key')
  await waitFor(() => expect(loads(fetch)).toBe(2))
  fetch.mockClear()
  responses['PATCH /api/projects/3'] = patched({ ...PLANE_SET, plane_key_set: false })
  responses[`GET ${BOARD}`] = [200, planeBoard({ ...PLANE_SET, plane_key_set: false })]
  fireEvent.click(planeSection().getByRole('button', { name: 'Clear' }))
  await waitFor(() => expect(planeSection().queryByText('API key: set')).toBeNull())
  expect(sent(fetch, 'PATCH', '/api/projects/3')).toEqual({ plane_api_key: '' })
  expect(box('API key').value).toBe('')
})

test('109 AC18: Save without a typed key leaves the stored key alone', async () => {
  const { fetch } = await open(planeBoard(PLANE_SET), { 'PATCH /api/projects/3': patched(PLANE_SET) })
  fireEvent.click(planeSection().getByRole('button', { name: 'Save' }))
  await planeSection().findByText('Saved.')
  expect(Object.keys(sent(fetch, 'PATCH', '/api/projects/3'))).not.toContain('plane_api_key')
})

test('109 AC19: Sync now is disabled until URL, slug, project ID are saved and a key is set', async () => {
  for (const missing of ['plane_api_url', 'plane_workspace', 'plane_project_id', 'plane_key_set']) {
    const { fetch, unmount } = await open(planeBoard({ ...PLANE_SET, [missing]: missing === 'plane_key_set' ? false : null }))
    expect(planeSync().disabled).toBe(true)
    fireEvent.click(planeSync())
    expect(sends(fetch, 'POST', PLANE_SYNC)).toHaveLength(0)
    unmount()
  }
  await open(planeBoard(PLANE_SET))
  expect(planeSync().disabled).toBe(false)
})

test('109 AC19: Sync now posts {}, is disabled while pending, says the counts in a polite region cleared as a sync starts, and reloads', async () => {
  const { fetch } = await open(planeBoard(PLANE_SET), { [`POST ${PLANE_SYNC}`]: [200, { new: 2, updated: 1, skipped: 5 }] })
  fireEvent.click(planeSync())
  const line = await planeSection().findByText(PLANE_LINE)
  expect(line.closest('[aria-live]').getAttribute('aria-live')).toBe('polite')
  expect(sent(fetch, 'POST', PLANE_SYNC)).toEqual({})
  await waitFor(() => expect(loads(fetch)).toBe(2))
  const reply = fetch.getMockImplementation()
  let release
  const gate = new Promise((resolve) => (release = resolve))
  fetch.mockImplementation((url, init) => (url === PLANE_SYNC ? gate.then(() => reply(url, init)) : reply(url, init)))
  fireEvent.click(planeSync())
  expect(planeSync().disabled).toBe(true)
  expect(planeSection().queryByText(PLANE_LINE)).toBeNull()
  release()
  expect(await planeSection().findByText(PLANE_LINE)).toBeTruthy()
  expect(planeSync().disabled).toBe(false)
})

test('109 AC19: a refused sync shows its detail as an alert in the Plane section and does not reload', async () => {
  const detail = 'Plane refused the API key: check it in project Settings'
  const { fetch } = await open(planeBoard(PLANE_SET), { [`POST ${PLANE_SYNC}`]: [409, { detail }] })
  fireEvent.click(planeSync())
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe(detail)
  expect(alert.closest('section')).toBe(section('Plane'))
  expect(screen.queryByText(/^Synced Plane/)).toBeNull()
  await waitFor(() => expect(planeSync().disabled).toBe(false))
  expect(loads(fetch)).toBe(1)
})

// --- Move (board AC27–AC28, moved) -------------------------------------------------------

test('FE31 (AC27), 049 Q13: Move lists the workspaces, patches the chosen one, the header follows the reload, and so does the sidebar', async () => {
  const { fetch, responses } = await open(board(), {
    'PATCH /api/projects/3': [200, { id: 3, workspace_id: 4, name: 'api', test_cmd: 'pytest -q' }],
  })
  const select = screen.getByRole('combobox', { name: 'Workspace' })
  const options = within(openSelect(select)).getAllByRole('option', { hidden: true }) // jsdom: no Popover API
  expect(options.map((o) => [o.textContent, o.getAttribute('aria-selected')])).toEqual([['personal', 'true'], ['work', 'false']])
  responses[`GET ${BOARD}`] = [200, board({ project: { ...PROJECT, workspace_id: 4, workspace: 'work' } })]
  pick(select, '4')
  fireEvent.click(screen.getByRole('button', { name: 'Move' }))
  const h1 = await screen.findByRole('heading', { level: 1, name: 'api · work' })
  expect(within(h1).getByRole('link', { name: 'work' }).getAttribute('href')).toBe('/workspaces/4')
  expect(sent(fetch, 'PATCH', '/api/projects/3')).toEqual({ workspace_id: 4 })
  expect(loads(fetch)).toBe(2)
  await waitFor(() => expect(fetched(fetch).filter((url) => url === '/api/pages/sidebar')).toHaveLength(2))
})

test('FE31 (AC28): a refused move shows its detail in the Move form', async () => {
  await open(board(), { 'PATCH /api/projects/3': [404, { detail: 'Not Found' }] })
  pick(screen.getByRole('combobox', { name: 'Workspace' }), '4')
  fireEvent.click(screen.getByRole('button', { name: 'Move' }))
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe('Not Found')
  expect(alert.closest('form')).toBe(screen.getByRole('button', { name: 'Move' }).closest('form'))
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('api · personal')
})

// --- Title, 404, another project ---------------------------------------------------------

test('FE32: the title; a 404 is the not-found state; /projects/4/settings resets Move and clears results', async () => {
  const { router, responses } = await open(board(), { [`POST ${IMPORT}`]: [200, IMPORTED] })
  await waitFor(() => expect(document.title).toBe('api · Settings · Workcell'))
  importFile(bundleFile())
  await screen.findByText(fullText('Imported #12 Rate-limit <login>'))
  pick(screen.getByRole('combobox', { name: 'Workspace' }), '4')
  expect(screen.getByRole('combobox', { name: 'Workspace' }).textContent).toBe('work')

  // same workspace as project 3, so only a reset per project puts the select back on it
  responses['GET /api/pages/projects/4'] = [200, board({ project: { ...PROJECT, id: 4, name: 'billing' } })]
  await act(() => router.navigate('/projects/4/settings'))
  await screen.findByRole('heading', { level: 1, name: 'billing · personal' })
  expect(screen.getByRole('combobox', { name: 'Workspace' }).textContent).toBe('personal')
  expect(screen.queryByText(/^Imported/)).toBeNull()
  expect(screen.getByRole('button', { name: 'Import' }).disabled).toBe(true)

  await act(() => router.navigate('/projects/99/settings'))
  expect(await screen.findByRole('heading', { level: 1, name: 'Not Found' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Go to the dashboard' }).getAttribute('href')).toBe('/')
})
