import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { cls, expectSkeleton, fetched, mockFetch, renderAt } from '../../test/render.jsx'

const PROJECT = {
  id: 3, name: 'api', path: '/home/me/api', default_branch: 'main', workspace_id: 2, workspace: 'personal',
  remote_url: null, test_cmd: 'pytest -q',
}
const BOARD = '/api/pages/projects/3'
const CONTEXT = '/api/projects/3/context'
const ITEMS = '/api/projects/3/context/items'
const board = (project = PROJECT) => ({
  project, factory: 'ready', hint: null, can_run: true, workspaces: [{ id: 2, name: 'personal', projects: 1 }],
  columns: { backlog: [], in_progress: [], review: [], done: [] },
})
/** GET or PUT /api/projects/{id}/context's body; `bytes` counts `context_md` unless given. */
const context = (context_md, extra = {}) => ({
  context_md, context_html: '', bytes: new TextEncoder().encode(context_md).length, max_bytes: 16384, ...extra,
})
/** A <ContextItem> of the API contract. */
const item = (id, title, extra = {}) => ({
  id, parent_id: null, kind: 'item', title, description: '', content_md: `# ${title}\n`, content_html: `<h1>${title}</h1>\n`,
  source_path: null, position: id, created_at: '2026-10-23T10:00:00Z', updated_at: '2026-10-23T10:00:00Z', ...extra,
})
const group = (id, title, extra = {}) => item(id, title, { kind: 'group', content_md: '', content_html: '', ...extra })

const API = item(5, 'API conventions', { description: 'Every endpoint returns JSON.' })
const RUNBOOKS = group(7, 'Runbooks', { description: 'How we ship.' })
const DEPLOY = item(8, 'Deploy', { parent_id: 7, description: 'Tag, then push.' })
const NOTES = item(6, 'Notes', { source_path: '/home/me/notes/notes.md' })
const ROLLBACK = item(9, 'Rollback', { parent_id: 7, source_path: '/home/me/notes/rollback.md' })
const ARCHIVE = group(10, 'Archive')
const DESIGN = group(11, 'Design')
const MOCKUPS = item(12, 'Mockups', { parent_id: 11 })
// flat, as GET answers; the top level is API, Runbooks, Notes, Archive, Design
const LIBRARY = [API, RUNBOOKS, DEPLOY, NOTES, ROLLBACK, ARCHIVE, DESIGN, MOCKUPS]

afterEach(() => {
  vi.useRealTimers()
})

/** Renders /projects/3/context with `items` as GET's reply; waits for the grid. */
async function open(items = LIBRARY, more = {}, ctx = context('# Stack\n', { context_html: '<h1>Stack</h1>\n' })) {
  const responses = { [`GET ${BOARD}`]: [200, board()], [`GET ${CONTEXT}`]: [200, ctx], [`GET ${ITEMS}`]: [200, items], ...more }
  const fetch = mockFetch(responses)
  const view = renderAt('/projects/3/context')
  await screen.findByRole('list', { name: 'Cards' })
  return { fetch, responses, ...view }
}

const count = (fetch, url) => calls(fetch, 'GET', url).length
const advance = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))
const calls = (fetch, method, url) => fetch.mock.calls.filter(([u, init]) => u === url && (init?.method ?? 'GET') === method)
/** The one `method url` call: asserts its X-Requested-By and returns its JSON body as sent. */
function sent(fetch, method, url) {
  const made = calls(fetch, method, url)
  expect(made).toHaveLength(1)
  expect(made[0][1].headers['X-Requested-By']).toBe('fctl')
  return made[0][1].body === undefined ? undefined : JSON.parse(made[0][1].body)
}

/** The page's grid (the first), or a dialog's. */
const grid = (scope = screen) => scope.getAllByRole('list', { name: 'Cards' })[0]
/** Each card's title, in order. */
const titles = (list) => within(list).getAllByRole('listitem').map((li) => li.querySelector('button').textContent)
const card = (title, scope = screen) => scope.getByRole('button', { name: title }).closest('li')
const dialog = (name) => screen.getByRole('dialog', { name })
const field = (scope, name) => within(scope).getByRole('textbox', { name })
const type = (el, value) => fireEvent.change(el, { target: { value } })
const actionsOf = (title, scope = screen) => scope.getByRole('button', { name: `Actions for ${title}` })
const menuOf = (actions) => document.getElementById(actions.getAttribute('popovertarget'))
/** Chooses `label` in the ⋯ menu of `title`; jsdom has no Popover API, so the menu counts as hidden. */
const choose = (title, label, scope) =>
  fireEvent.click(within(menuOf(actionsOf(title, scope))).getByRole('button', { name: label, hidden: true }))
/** A menu's items in order, as `TAG text`. */
const itemsOf = (menu) => [...menu.querySelectorAll('button, p, hr')].map((el) => `${el.tagName} ${el.textContent}`.trim())
const save = (scope) => within(scope).getByRole('button', { name: 'Save' })
const close = (scope) => fireEvent.click(within(scope).getByRole('button', { name: 'Close' }))

test('FE1: the page fetches the board view-model, the context, and the items once each; 10 s later still once; the title', async () => {
  vi.useFakeTimers()
  const fetch = mockFetch({
    [`GET ${BOARD}`]: [200, board()], [`GET ${CONTEXT}`]: [200, context('# Stack\n')], [`GET ${ITEMS}`]: [200, LIBRARY],
  })
  renderAt('/projects/3/context')
  await advance(0)
  expect(titles(grid())[0]).toBe('Stack and conventions')
  expect([count(fetch, BOARD), count(fetch, CONTEXT), count(fetch, ITEMS)]).toEqual([1, 1, 1])
  await advance(10_000)
  expect([count(fetch, BOARD), count(fetch, CONTEXT), count(fetch, ITEMS)]).toEqual([1, 1, 1])
  expect(document.title).toBe('api · Context · Claude Factories')
})

test("FE2: the pinned card, then the top-level cards in order, each a title button and description; counts, paths, no group's cards", async () => {
  await open()
  expect(titles(grid())).toEqual(['Stack and conventions', 'API conventions', 'Runbooks', 'Notes', 'Archive', 'Design'])
  const pinned = card('Stack and conventions')
  expect(within(pinned).getByText('Pinned')).toBeTruthy()
  expect(within(pinned).getByText('Agents read it at the top of fctl show.')).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Actions for Stack and conventions' })).toBeNull()
  expect(within(card('API conventions')).getByText('Every endpoint returns JSON.')).toBeTruthy()
  expect(within(card('Runbooks')).getByText('How we ship.')).toBeTruthy()
  expect(within(card('Runbooks')).getByText('2 cards')).toBeTruthy()
  expect(within(card('Design')).getByText('1 card')).toBeTruthy()
  expect(within(card('Archive')).getByText('0 cards')).toBeTruthy()
  expect(within(card('API conventions')).queryByText(/cards?$/)).toBeNull()
  const path = within(card('Notes')).getByText('/home/me/notes/notes.md')
  expect(path.className).toMatch(cls('font-mono'))
  expect(path.className).toMatch(cls('text-muted'))
  for (const title of ['Deploy', 'Rollback', 'Mockups']) expect(screen.queryByRole('button', { name: title })).toBeNull()
})

test('FE3: the pinned card opens Stack and conventions with the editor; Save puts once, the Preview updates; a refusal stays; Close and Esc', async () => {
  const { fetch, responses } = await open(LIBRARY, {}, context('# Stack\n', { context_html: '<h1>Stack</h1>\n', max_bytes: 10 }))
  const opener = screen.getByRole('button', { name: 'Stack and conventions' })
  fireEvent.click(opener)
  const d = dialog('Stack and conventions')
  expect(d.tagName).toBe('DIALOG')
  expect(d.open).toBe(true)
  const box = field(d, 'Content')
  expect(box.value).toBe('# Stack\n')
  expect(within(d).getByText('8 / 10 bytes')).toBeTruthy()
  const preview = () => within(d).getByRole('region', { name: 'Preview' })
  expect(within(preview()).getByRole('heading', { level: 1, name: 'Stack' })).toBeTruthy()

  type(box, 'ééééé é') // 13 bytes
  const over = within(d).getByText('13 / 10 bytes · over the limit')
  expect(over.className).toMatch(cls('text-danger'))
  expect(save(d).disabled).toBe(true)

  responses[`PUT ${CONTEXT}`] = [200, context('# Go\n', { context_html: '<h1>Go</h1>\n', max_bytes: 10 })]
  type(box, '# Go\n')
  expect(within(d).getByText('5 / 10 bytes')).toBeTruthy()
  fireEvent.click(save(d))
  expect(await within(preview()).findByRole('heading', { name: 'Go' })).toBeTruthy()
  expect(sent(fetch, 'PUT', CONTEXT)).toEqual({ context_md: '# Go\n' })
  expect(d.open).toBe(true)

  responses[`PUT ${CONTEXT}`] = [413, { detail: 'context over 16 KB' }]
  type(box, 'draft')
  fireEvent.click(save(d))
  expect((await within(d).findByRole('alert')).textContent).toBe('context over 16 KB')
  expect(box.value).toBe('draft')
  expect(within(preview()).getByRole('heading', { name: 'Go' })).toBeTruthy()

  close(d)
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(opener)
  // the next open starts from the last save; Esc's close (the browser's, which jsdom lacks) closes it too
  fireEvent.click(opener)
  expect(field(dialog('Stack and conventions'), 'Content').value).toBe('# Go\n')
  act(() => dialog('Stack and conventions').close())
  expect(screen.queryByRole('dialog')).toBeNull()
})

test('FE3: a blank context_md previews Nothing saved yet., muted', async () => {
  await open([], {}, context('  \n'))
  fireEvent.click(screen.getByRole('button', { name: 'Stack and conventions' }))
  const preview = within(dialog('Stack and conventions')).getByRole('region', { name: 'Preview' })
  expect(within(preview).getByText('Nothing saved yet.').className).toMatch(cls('text-muted'))
  expect(preview.querySelector('.markdown')).toBeNull()
})

test('FE4: + New card opens New card with empty fields and a count; Save posts the item; 201 closes, reloads, and shows it', async () => {
  const { fetch, responses } = await open([API])
  fireEvent.click(screen.getByRole('button', { name: '+ New card' }))
  const d = dialog('New card')
  expect([field(d, 'Title').value, field(d, 'Description').value, field(d, 'Content').value]).toEqual(['', '', ''])
  expect(within(d).getByText('0 / 16384 bytes')).toBeTruthy()
  type(field(d, 'Title'), 'Errors')
  type(field(d, 'Description'), 'How we fail.')
  type(field(d, 'Content'), '# Errors é\n')
  expect(within(d).getByText('12 / 16384 bytes')).toBeTruthy()
  const made = item(13, 'Errors', { description: 'How we fail.' })
  responses[`POST ${ITEMS}`] = [201, made]
  responses[`GET ${ITEMS}`] = [200, [API, made]]
  fireEvent.click(save(d))
  await waitFor(() => expect(titles(grid())).toEqual(['Stack and conventions', 'API conventions', 'Errors']))
  expect(sent(fetch, 'POST', ITEMS)).toEqual({ kind: 'item', title: 'Errors', description: 'How we fail.', content_md: '# Errors é\n' })
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(count(fetch, ITEMS)).toBe(2)
})

test('FE5: + New group opens New group with only Title and Description; Save posts the group', async () => {
  const { fetch, responses } = await open([API])
  fireEvent.click(screen.getByRole('button', { name: '+ New group' }))
  const d = dialog('New group')
  expect(within(d).getAllByRole('textbox').map((el) => el.name)).toEqual(['title', 'description'])
  expect(within(d).queryByText(/bytes/)).toBeNull()
  type(field(d, 'Title'), 'Runbooks')
  type(field(d, 'Description'), 'How we ship.')
  responses[`POST ${ITEMS}`] = [201, RUNBOOKS]
  responses[`GET ${ITEMS}`] = [200, [API, RUNBOOKS]]
  fireEvent.click(save(d))
  expect(await screen.findByRole('button', { name: 'Runbooks' })).toBeTruthy()
  expect(sent(fetch, 'POST', ITEMS)).toEqual({ kind: 'group', title: 'Runbooks', description: 'How we ship.' })
  expect(screen.queryByRole('dialog')).toBeNull()
})

test("FE6: a card's title opens Edit <title> filled, with its count and Preview; Save patches; a refusal stays with what was typed", async () => {
  const one = '/api/context/items/5'
  const { fetch, responses } = await open([API], { [`PATCH ${one}`]: [413, { detail: 'card over 16 KB' }] })
  fireEvent.click(screen.getByRole('button', { name: 'API conventions' }))
  const d = dialog('Edit API conventions')
  expect([field(d, 'Title').value, field(d, 'Description').value, field(d, 'Content').value]).toEqual([
    'API conventions', 'Every endpoint returns JSON.', '# API conventions\n',
  ])
  expect(within(d).getByText('18 / 16384 bytes')).toBeTruthy()
  expect(within(within(d).getByRole('region', { name: 'Preview' })).getByRole('heading', { level: 1, name: 'API conventions' })).toBeTruthy()

  type(field(d, 'Title'), 'API rules')
  type(field(d, 'Content'), 'big')
  fireEvent.click(save(d))
  expect((await within(d).findByRole('alert')).textContent).toBe('card over 16 KB')
  expect(d.open).toBe(true)
  expect([field(d, 'Title').value, field(d, 'Content').value]).toEqual(['API rules', 'big'])
  expect(count(fetch, ITEMS)).toBe(1)

  const renamed = { ...API, title: 'API rules', content_md: 'big' }
  responses[`PATCH ${one}`] = [200, renamed]
  responses[`GET ${ITEMS}`] = [200, [renamed]]
  fetch.mockClear()
  fireEvent.click(save(d))
  expect(await screen.findByRole('button', { name: 'API rules' })).toBeTruthy()
  expect(sent(fetch, 'PATCH', one)).toEqual({ title: 'API rules', description: 'Every endpoint returns JSON.', content_md: 'big' })
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(count(fetch, ITEMS)).toBe(1)
})

test("FE7: each ⋯ menu: Edit, Reload from path on path cards, Move to group, Move out of group, then Delete; a group's Edit and Delete", async () => {
  const { fetch, responses } = await open()
  const menu = (title, scope) => {
    const el = menuOf(actionsOf(title, scope))
    expect(el.getAttribute('popover')).toBe('auto')
    return el
  }
  expect(itemsOf(menu('API conventions'))).toEqual([
    'BUTTON Edit', 'P Move to group', 'BUTTON Runbooks', 'BUTTON Archive', 'BUTTON Design', 'HR', 'BUTTON Delete',
  ])
  expect(itemsOf(menu('Notes'))).toEqual([
    'BUTTON Edit', 'BUTTON Reload from path', 'P Move to group', 'BUTTON Runbooks', 'BUTTON Archive', 'BUTTON Design', 'HR',
    'BUTTON Delete',
  ])
  expect(itemsOf(menu('Runbooks'))).toEqual(['BUTTON Edit', 'HR', 'BUTTON Delete'])
  const m = within(menu('Notes'))
  expect(m.getByText('Move to group').className).toMatch(cls('text-muted'))
  expect(m.getByRole('button', { name: 'Delete', hidden: true }).className).toMatch(cls('text-danger'))
  for (const button of m.getAllByRole('button', { hidden: true })) {
    expect(button.getAttribute('popovertargetaction')).toBe('hide')
  }

  // a card in a group lists the other groups and Move out of group
  fireEvent.click(screen.getByRole('button', { name: 'Runbooks' }))
  const g = within(dialog('Runbooks'))
  expect(itemsOf(menu('Rollback', g))).toEqual([
    'BUTTON Edit', 'BUTTON Reload from path', 'P Move to group', 'BUTTON Archive', 'BUTTON Design', 'BUTTON Move out of group', 'HR',
    'BUTTON Delete',
  ])
  close(dialog('Runbooks'))

  // a group's Edit: Title and Description, patched alone
  choose('Runbooks', 'Edit')
  const d = dialog('Edit Runbooks')
  expect(within(d).getAllByRole('textbox').map((el) => el.value)).toEqual(['Runbooks', 'How we ship.'])
  type(field(d, 'Title'), 'Ops')
  responses['PATCH /api/context/items/7'] = [200, { ...RUNBOOKS, title: 'Ops' }]
  fireEvent.click(save(d))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(sent(fetch, 'PATCH', '/api/context/items/7')).toEqual({ title: 'Ops', description: 'How we ship.' })
  // and Edit on a card opens the card's dialog
  choose('API conventions', 'Edit')
  expect(field(dialog('Edit API conventions'), 'Content').value).toBe('# API conventions\n')
})

test('FE7: with no group, a top-level card has no Move to group caption', async () => {
  await open([API, NOTES])
  expect(itemsOf(menuOf(actionsOf('Notes')))).toEqual(['BUTTON Edit', 'BUTTON Reload from path', 'HR', 'BUTTON Delete'])
  expect(itemsOf(menuOf(actionsOf('API conventions')))).toEqual(['BUTTON Edit', 'HR', 'BUTTON Delete'])
})

test("FE8: a group in the menu patches parent_id; Move out of group sends null; each reloads; a refusal is the page's alert", async () => {
  const { fetch, responses } = await open()
  responses['PATCH /api/context/items/5'] = [200, { ...API, parent_id: 7 }]
  responses[`GET ${ITEMS}`] = [200, LIBRARY.map((i) => (i.id === 5 ? { ...API, parent_id: 7 } : i))]
  choose('API conventions', 'Runbooks')
  await waitFor(() => expect(screen.queryByRole('button', { name: 'API conventions' })).toBeNull())
  expect(sent(fetch, 'PATCH', '/api/context/items/5')).toEqual({ parent_id: 7 })
  expect(within(card('Runbooks')).getByText('3 cards')).toBeTruthy()
  expect(count(fetch, ITEMS)).toBe(2)

  fireEvent.click(screen.getByRole('button', { name: 'Runbooks' }))
  responses['PATCH /api/context/items/8'] = [200, { ...DEPLOY, parent_id: null }]
  responses[`GET ${ITEMS}`] = [200, LIBRARY.map((i) => (i.id === 8 ? { ...DEPLOY, parent_id: null } : i))]
  choose('Deploy', 'Move out of group', within(dialog('Runbooks')))
  await waitFor(() => expect(titles(grid())).toContain('Deploy'))
  expect(sent(fetch, 'PATCH', '/api/context/items/8')).toEqual({ parent_id: null })
  expect(titles(grid(within(dialog('Runbooks'))))).toEqual(['Rollback'])
  close(dialog('Runbooks'))

  responses['PATCH /api/context/items/6'] = [422, { detail: 'parent_id 7 is not a group of this project' }]
  choose('Notes', 'Runbooks')
  expect((await screen.findByRole('alert')).textContent).toBe('parent_id 7 is not a group of this project')
})

test('FE9: Delete opens Delete <title>? with the card or group text; its Delete deletes and reloads; a refusal stays inside', async () => {
  const { fetch, responses } = await open()
  choose('API conventions', 'Delete')
  let d = dialog('Delete API conventions?')
  expect(within(d).getByText('This removes the card from the app. A file it was read from stays on disk.')).toBeTruthy()
  fireEvent.click(within(d).getByRole('button', { name: 'Cancel' }))
  expect(screen.queryByRole('dialog')).toBeNull()

  choose('Runbooks', 'Delete')
  d = dialog('Delete Runbooks?')
  expect(
    within(d).getByText('This removes the group and its 2 cards from the app. Files they were read from stay on disk.'),
  ).toBeTruthy()
  responses['DELETE /api/context/items/7'] = [409, { detail: 'locked' }]
  fireEvent.click(within(d).getByRole('button', { name: 'Delete' }))
  expect((await within(d).findByRole('alert')).textContent).toBe('locked')
  expect(d.open).toBe(true)

  responses['DELETE /api/context/items/7'] = [204]
  responses[`GET ${ITEMS}`] = [200, LIBRARY.filter((i) => i.id !== 7 && i.parent_id !== 7)]
  fireEvent.click(within(d).getByRole('button', { name: 'Delete' }))
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Runbooks' })).toBeNull())
  expect(calls(fetch, 'DELETE', '/api/context/items/7')).toHaveLength(2)
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(screen.getByRole('button', { name: '+ New card' }))
})

test("FE10: Reload from path posts reload and reloads; a refusal is the page's alert, or the group modal's from there", async () => {
  const { fetch, responses } = await open()
  responses['POST /api/context/items/6/reload'] = [200, NOTES]
  choose('Notes', 'Reload from path')
  await waitFor(() => expect(count(fetch, ITEMS)).toBe(2))
  expect(sent(fetch, 'POST', '/api/context/items/6/reload')).toBeUndefined()
  expect(screen.queryByRole('alert')).toBeNull()

  responses['POST /api/context/items/6/reload'] = [404, { detail: 'no file at /home/me/notes/notes.md' }]
  choose('Notes', 'Reload from path')
  expect((await screen.findByRole('alert')).textContent).toBe('no file at /home/me/notes/notes.md')

  fireEvent.click(screen.getByRole('button', { name: 'Runbooks' }))
  const g = dialog('Runbooks')
  responses['POST /api/context/items/9/reload'] = [422, { detail: '/home/me/notes/rollback.md: not UTF-8' }]
  choose('Rollback', 'Reload from path', within(g))
  expect((await within(g).findByRole('alert')).textContent).toBe('/home/me/notes/rollback.md: not UTF-8')
  expect(screen.getAllByRole('alert')).toHaveLength(2) // the page's, from before, is left alone
})

test("FE11: a group's title opens its modal: heading, description, its cards in order with menus, the add controls, Close; Esc too", async () => {
  await open()
  const opener = screen.getByRole('button', { name: 'Runbooks' })
  fireEvent.click(opener)
  const d = dialog('Runbooks')
  expect(d.tagName).toBe('DIALOG')
  const g = within(d)
  expect(g.getByRole('heading', { level: 2 }).textContent).toBe('Runbooks')
  expect(g.getByText('How we ship.')).toBeTruthy()
  expect(titles(grid(g))).toEqual(['Deploy', 'Rollback'])
  expect(g.getByText('Tag, then push.')).toBeTruthy()
  expect(actionsOf('Deploy', g)).toBeTruthy()
  expect(actionsOf('Rollback', g)).toBeTruthy()
  for (const name of ['+ New card', 'Add from path', 'Close']) expect(g.getByRole('button', { name })).toBeTruthy()
  expect(g.getByLabelText('Upload files').type).toBe('file')
  expect(g.getByRole('textbox', { name: 'Path' })).toBeTruthy()
  expect(g.queryByRole('button', { name: '+ New group' })).toBeNull()
  close(d)
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(document.activeElement).toBe(opener)

  fireEvent.click(screen.getByRole('button', { name: 'Archive' }))
  expect(within(dialog('Archive')).getByText('No cards in this group yet.')).toBeTruthy()
  act(() => dialog('Archive').close()) // Esc's close
  expect(screen.queryByRole('dialog')).toBeNull()
})

test("FE12: inside the group modal, + New card, an upload, and Add from path send the group's id; the modal's cards update", async () => {
  const { fetch, responses } = await open()
  fireEvent.click(screen.getByRole('button', { name: 'Runbooks' }))
  const g = within(dialog('Runbooks'))
  let library = LIBRARY

  // + New card
  const made = item(20, 'Hotfix', { parent_id: 7 })
  library = [...library, made]
  responses[`POST ${ITEMS}`] = [201, made]
  responses[`GET ${ITEMS}`] = [200, library]
  fireEvent.click(g.getByRole('button', { name: '+ New card' }))
  const d = dialog('New card')
  type(field(d, 'Title'), 'Hotfix')
  fireEvent.click(save(d))
  await waitFor(() => expect(titles(grid(g))).toEqual(['Deploy', 'Rollback', 'Hotfix']))
  expect(sent(fetch, 'POST', ITEMS)).toEqual({ kind: 'item', title: 'Hotfix', description: '', content_md: '', parent_id: 7 })

  // an upload
  const upload = `${ITEMS}/upload?name=oncall.md&parent_id=7`
  const uploaded = item(21, 'On call', { parent_id: 7 })
  library = [...library, uploaded]
  responses[`POST ${upload}`] = [201, uploaded]
  responses[`GET ${ITEMS}`] = [200, library]
  fireEvent.change(g.getByLabelText('Upload files'), { target: { files: [new File(['# On call\n'], 'oncall.md')] } })
  await waitFor(() => expect(titles(grid(g))).toEqual(['Deploy', 'Rollback', 'Hotfix', 'On call']))
  expect(calls(fetch, 'POST', upload)).toHaveLength(1)

  // Add from path
  const read = item(22, 'Release', { parent_id: 7, source_path: '/home/me/notes/release.md' })
  library = [...library, read]
  responses[`POST ${ITEMS}/from-path`] = [201, [read]]
  responses[`GET ${ITEMS}`] = [200, library]
  type(g.getByRole('textbox', { name: 'Path' }), '/home/me/notes/release.md')
  fireEvent.click(g.getByRole('button', { name: 'Add from path' }))
  await waitFor(() => expect(titles(grid(g))).toEqual(['Deploy', 'Rollback', 'Hotfix', 'On call', 'Release']))
  expect(sent(fetch, 'POST', `${ITEMS}/from-path`)).toEqual({ path: '/home/me/notes/release.md', parent_id: 7 })
})

test('FE13: Upload files takes several .md, .markdown, .txt; posts each raw, one after the other, then reloads once', async () => {
  const { fetch, responses } = await open([API])
  const input = screen.getByLabelText('Upload files')
  expect(input.multiple).toBe(true)
  expect(input.getAttribute('accept')).toBe('.md,.markdown,.txt')
  const [a, b] = [new File(['# A\n'], 'a.md'), new File(['b\n'], 'b.txt')]
  const [urlA, urlB] = [`${ITEMS}/upload?name=a.md`, `${ITEMS}/upload?name=b.txt`]
  responses[`POST ${urlA}`] = [201, item(30, 'A')]
  responses[`POST ${urlB}`] = [201, item(31, 'b.txt')]
  responses[`GET ${ITEMS}`] = [200, [API, item(30, 'A'), item(31, 'b.txt')]]
  const answer = fetch.getMockImplementation()
  let release
  fetch.mockImplementation((url, init) =>
    url === urlA ? new Promise((resolve) => (release = () => resolve(answer(url, init)))) : answer(url, init),
  )
  fireEvent.change(input, { target: { files: [a, b] } })
  await waitFor(() => expect(calls(fetch, 'POST', urlA)).toHaveLength(1))
  expect(calls(fetch, 'POST', urlB)).toHaveLength(0) // a.md hasn't answered
  await act(async () => release())
  await waitFor(() => expect(titles(grid())).toEqual(['Stack and conventions', 'API conventions', 'A', 'b.txt']))
  for (const [url, file] of [[urlA, a], [urlB, b]]) {
    const [[, init]] = calls(fetch, 'POST', url)
    expect(init.body).toBe(file)
    expect(init.headers).toEqual({ 'X-Requested-By': 'fctl' })
  }
  const order = fetched(fetch)
  expect(order.indexOf(urlA)).toBeLessThan(order.indexOf(urlB))
  expect(count(fetch, ITEMS)).toBe(2)
})

test('FE14: one refused upload of two: <file name>: <detail> in an alert, the other card shows, and the input is cleared', async () => {
  const { fetch, responses } = await open([API])
  const input = screen.getByLabelText('Upload files')
  const cleared = vi.fn()
  Object.defineProperty(input, 'value', { configurable: true, get: () => '', set: cleared })
  responses[`POST ${ITEMS}/upload?name=big.md`] = [413, { detail: 'card over 16 KB' }]
  responses[`POST ${ITEMS}/upload?name=ok.md`] = [201, item(32, 'OK')]
  responses[`GET ${ITEMS}`] = [200, [API, item(32, 'OK')]]
  fireEvent.change(input, { target: { files: [new File(['x'], 'big.md'), new File(['# OK\n'], 'ok.md')] } })
  expect((await screen.findByRole('alert')).textContent).toBe('big.md: card over 16 KB')
  await waitFor(() => expect(screen.getByRole('button', { name: 'OK' })).toBeTruthy())
  expect(cleared).toHaveBeenCalledWith('')
  expect(count(fetch, ITEMS)).toBe(2)
})

test('FE15: the Path field has its hint; Add from path is disabled while blank, posts {path}, clears on 201; a refusal keeps it', async () => {
  const { fetch, responses } = await open([API])
  const path = screen.getByRole('textbox', { name: 'Path' })
  const hint = document.getElementById(path.getAttribute('aria-describedby'))
  expect(hint.textContent).toBe(
    "An absolute path to a .md, .markdown, or .txt file, or a folder of them, on the backend's machine. In Docker, only mounted folders exist.",
  )
  const add = screen.getByRole('button', { name: 'Add from path' })
  expect(add.disabled).toBe(true)
  type(path, '   ')
  expect(add.disabled).toBe(true)

  const url = `${ITEMS}/from-path`
  responses[`POST ${url}`] = [404, { detail: 'no file or folder at /home/me/nope' }]
  type(path, '/home/me/nope')
  fireEvent.click(add)
  const alert = await screen.findByRole('alert')
  expect(alert.textContent).toBe('no file or folder at /home/me/nope')
  expect(alert.closest('form')).toBe(path.closest('form'))
  expect(path.value).toBe('/home/me/nope')

  const folder = group(40, 'notes', { source_path: '/home/me/notes' })
  responses[`POST ${url}`] = [201, [folder, item(41, 'A', { parent_id: 40 })]]
  responses[`GET ${ITEMS}`] = [200, [API, folder, item(41, 'A', { parent_id: 40 })]]
  fetch.mockClear()
  type(path, '/home/me/notes')
  fireEvent.click(add)
  await waitFor(() => expect(screen.getByRole('button', { name: 'notes' })).toBeTruthy())
  expect(sent(fetch, 'POST', url)).toEqual({ path: '/home/me/notes' })
  expect(path.value).toBe('')
  expect(screen.queryByRole('alert')).toBeNull()
  expect(count(fetch, ITEMS)).toBe(1)
})

test('FE16: loading is one skeleton status with no buttons; a failed items or context load is an alert under the header', async () => {
  const fetch = mockFetch({ [`GET ${BOARD}`]: [200, board()], [`GET ${CONTEXT}`]: [200, context('')] })
  const answer = fetch.getMockImplementation()
  fetch.mockImplementation((url, init) => (url === ITEMS ? new Promise(() => {}) : answer(url, init))) // never answers
  const first = renderAt('/projects/3/context')
  const main = within(screen.getByRole('main'))
  expect((await main.findByRole('heading', { level: 1 })).textContent).toBe('api · personal')
  const skeletons = main.getAllByRole('status')
  expect(skeletons).toHaveLength(1)
  expectSkeleton(skeletons[0])
  expect(main.queryAllByRole('button')).toEqual([])
  first.unmount()

  for (const [failing, other] of [[ITEMS, CONTEXT], [CONTEXT, ITEMS]]) {
    mockFetch({ [`GET ${BOARD}`]: [200, board()], [`GET ${failing}`]: [500, { detail: 'boom' }], [`GET ${other}`]: [200, other === ITEMS ? [] : context('')] })
    const { unmount } = renderAt('/projects/3/context')
    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toBe('boom')
    const h1 = screen.getByRole('heading', { level: 1 })
    expect(h1.closest('header').compareDocumentPosition(alert) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.queryByRole('list', { name: 'Cards' })).toBeNull()
    unmount()
  }
})

test('FE16: a 404 from any of the three loads is the not-found page', async () => {
  for (const missing of [BOARD, CONTEXT, ITEMS]) {
    const responses = { [`GET ${BOARD}`]: [200, board()], [`GET ${CONTEXT}`]: [200, context('')], [`GET ${ITEMS}`]: [200, []] }
    responses[`GET ${missing}`] = [404, { detail: 'Project #3 not found' }]
    mockFetch(responses)
    const { unmount } = renderAt('/projects/3/context')
    expect(await screen.findByRole('heading', { level: 1, name: 'Project #3 not found' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Go to the dashboard' })).toBeTruthy()
    expect(screen.queryByRole('list', { name: 'Cards' })).toBeNull()
    unmount()
  }
})

test("FE16: going from /projects/3/context to /projects/4/context shows project 4's cards", async () => {
  const { router } = await open(LIBRARY, {
    'GET /api/pages/projects/4': [200, board({ ...PROJECT, id: 4, name: 'billing' })],
    'GET /api/projects/4/context': [200, context('four')],
    'GET /api/projects/4/context/items': [200, [item(50, 'Invoices')]],
  })
  await act(() => router.navigate('/projects/4/context'))
  await screen.findByRole('heading', { level: 1, name: 'billing · personal' })
  await waitFor(() => expect(titles(grid())).toEqual(['Stack and conventions', 'Invoices']))
  expect(screen.queryByRole('button', { name: 'API conventions' })).toBeNull()
})
