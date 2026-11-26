import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { expect, test } from 'vitest'
import { cls, fetched, fullText, mockFetch, renderAt } from '../../test/render.jsx'
import { openSelect, pick as pickValue } from '../../test/select.js'

const API = '/api/pages/projects/3/code'
/** 020's CodeProject, with 047's workspace and 090's web_url. */
const PROJECT = { id: 3, name: 'api', path: '/home/me/api', workspace_id: 2, workspace: 'personal', web_url: null }
const TREE = {
  'README.md': { path: 'README.md' },
  'src/': { 'a.py': { path: 'src/a.py' }, 'lib/': { 'b.py': { path: 'src/lib/b.py' } } },
  'docs/': { 'guide.md': { path: 'docs/guide.md' } },
}
/** 054 BE1: local branches, then the origin ones with no local twin. */
const BRANCHES = ['feature-x', 'main', 'origin/old']
/** 020's CodePage view-model: the spec's README landing, with 054's branches; `extra` overrides its fields. */
const landing = (extra = {}) => ({
  project: PROJECT, error: null, branch: 'main', branches: BRANCHES, tree: TREE, shown: 'README.md',
  view: { text: '# Hi\n', lines: 1 }, lang: 'md', readme_html: '<h1>Hi</h1>\n', ...extra,
})
/** A file's view-model: `shown` is its path, with a TextView or NoteView and no readme_html. */
const file = (path, view, lang = null, extra = {}) => landing({ shown: path, view, lang, readme_html: null, ...extra })
const text = (t) => ({ text: t, lines: t.split('\n').length - 1 })

/** Renders `at` with `responses` keyed by "GET url", and waits for the first page heading. */
async function open(responses, at = '/projects/3/code') {
  const fetch = mockFetch(responses)
  const view = renderAt(at)
  await screen.findAllByRole('heading', { level: 1 })
  return { fetch, ...view }
}
/** Opens `?path=<path>` with `page` as its view-model. */
const openFile = (path, page) => open({ [`GET ${API}?${new URLSearchParams({ path })}`]: [200, page] }, `/projects/3/code?path=${path}`)

// 042 FE33: the code view-model's requests; the header's board view-model is counted apart
const loads = (fetch) => fetched(fetch).filter((url) => /^\/api\/pages\/projects\/\d+\/code/.test(url))
const BOARD = '/api/pages/projects/3'
/** 042's board view-model, for the header. */
const BOARD_PAGE = {
  project: { ...PROJECT, default_branch: 'main', workspace_id: 2, workspace: 'personal', remote_url: null, test_cmd: null },
  factory: 'ready', hint: null, can_run: true, workspaces: [{ id: 2, name: 'personal', projects: 1 }],
  columns: { backlog: [], in_progress: [], review: [], done: [] },
}
const h1 = () => document.querySelector('main h1')
const picker = () => screen.queryByRole('combobox', { name: 'Branch' })
/** The Branch select's options as [text, value] pairs, read by opening it; Esc closes it again. */
const options = () => {
  const pairs = [...openSelect(picker()).querySelectorAll('[role="option"]')].map((o) => [o.textContent, o.dataset.value])
  fireEvent.keyDown(picker(), { key: 'Escape' })
  return pairs
}
const pick = (value) => pickValue(picker(), value)
const hrefs = () => [...files().querySelectorAll('a')].map((a) => [a.textContent, a.getAttribute('href')])
/** FE9's hrefs, with no browsed branch. */
const PLAIN_HREFS = [
  ['README.md', '/projects/3/code?path=README.md'],
  ['a.py', '/projects/3/code?path=src%2Fa.py'],
  ['b.py', '/projects/3/code?path=src%2Flib%2Fb.py'],
  ['guide.md', '/projects/3/code?path=docs%2Fguide.md'],
]
const FOLLOWING = Node.DOCUMENT_POSITION_FOLLOWING
const files = () => screen.queryByRole('navigation', { name: 'Files' })
const link = (name) => within(files()).getByRole('link', { name })
const column = () => files().nextElementSibling
const fileHeader = () => screen.queryByRole('heading', { level: 2 })
const gutter = () => document.querySelector('main pre[aria-hidden="true"]')
const codes = () => [...document.querySelectorAll('main pre code')]
const highlighted = () => document.querySelectorAll('main [class*="hljs-"]')
const dir = (name) => within(files()).getByRole('button', { name })
const expanded = (name) => dir(name).getAttribute('aria-expanded')
/** FE12: a.py is in src/, which is closed on the landing, so its link is reached by opening src/ first. */
const openSrc = () => fireEvent.click(dir('src/'))
/** The Files nav as nested arrays: a file's name, or [directory, its entries]. */
const shape = (ul) =>
  [...ul.children].map((li) => {
    const button = li.querySelector(':scope > button')
    return button ? [button.textContent, shape(li.querySelector(':scope > ul'))] : li.textContent
  })

// --- Route, header, URL ------------------------------------------------------------------

test('AC1, FE33: the landing fetches once with no query; the header is the project header; the page title', async () => {
  const { fetch } = await open({ [`GET ${API}`]: [200, landing()], [`GET ${BOARD}`]: [200, BOARD_PAGE] })
  const header = document.querySelector('main header')
  await waitFor(() => expect(h1().textContent).toBe('api · personal'))
  expect(h1().closest('header')).toBe(header)
  expect(within(h1()).getByRole('link', { name: 'personal' }).getAttribute('href')).toBe('/workspaces/2')
  expect(within(header).getByText('Factory: ready ✓')).toBeTruthy()
  // FE12: the Branch select, not the old `Branch main` text, follows the factory state
  const branch = within(header).getByRole('combobox', { name: 'Branch' })
  expect(within(header).getByText('Factory: ready ✓').compareDocumentPosition(branch) & FOLLOWING).toBeTruthy()
  await waitFor(() => expect(document.title).toBe('api · Code · Claude Factories'))
  await new Promise((r) => setTimeout(r, 50)) // Q1: no polling, so nothing more arrives
  expect(loads(fetch)).toEqual([API])
  expect(fetched(fetch).filter((url) => url === BOARD)).toHaveLength(1)
})

test('FE33, 047 Q1: a ?path= change refetches the code view-model, not the board one; a failed board one leaves the h1 api · personal', async () => {
  const { fetch, router, unmount } = await open({
    [`GET ${API}`]: [200, landing()],
    [`GET ${API}?path=src%2Fa.py`]: [200, file('src/a.py', text('x = 1\n'), 'py')],
    [`GET ${BOARD}`]: [200, BOARD_PAGE],
  })
  await waitFor(() => expect(h1().textContent).toBe('api · personal'))
  openSrc()
  fireEvent.click(link('a.py'))
  await waitFor(() => expect(fileHeader().textContent).toBe('src/a.py'))
  await act(() => router.navigate('/projects/3/code'))
  await waitFor(() => expect(loads(fetch)).toHaveLength(3))
  expect(fetched(fetch).filter((url) => url === BOARD)).toHaveLength(1)
  expect(h1().textContent).toBe('api · personal')
  unmount()

  for (const failure of [[500, { detail: 'boom' }], [404, { detail: 'Not Found' }]]) {
    const failed = await open({ [`GET ${API}`]: [200, landing()], [`GET ${BOARD}`]: failure })
    await waitFor(() => expect(fetched(failed.fetch)).toContain(BOARD))
    await act(() => new Promise((r) => setTimeout(r, 20)))
    expect(h1().textContent).toBe('api · personal') // 047 Q1: from the code view-model
    expect(screen.queryByRole('alert')).toBeNull()
    expect(document.querySelector('main').textContent).not.toContain('Factory:')
    expect(files()).not.toBeNull()
    failed.unmount()
  }
})

test('047 FE4: the breadcrumb personal › api › Code sits above the project header, from the code view-model alone', async () => {
  for (const board of [[200, BOARD_PAGE], [500, { detail: 'boom' }], [404, { detail: 'Not Found' }]]) {
    const { fetch, unmount } = await open({ [`GET ${API}?path=src%2Fa.py`]: [200, file('src/a.py', text('x = 1\n'), 'py')], [`GET ${BOARD}`]: board }, '/projects/3/code?path=src/a.py')
    await waitFor(() => expect(fetched(fetch)).toContain(BOARD))
    await act(() => new Promise((r) => setTimeout(r, 20)))
    const crumbs = screen.getByRole('navigation', { name: 'Breadcrumb' })
    expect(crumbs.textContent).toBe('personal › api › Code') // no file-path parts
    expect(within(crumbs).getAllByRole('link').map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
      ['personal', '/workspaces/2'], ['api', '/projects/3'],
    ])
    const current = within(crumbs).getByText('Code')
    expect([current.getAttribute('aria-current'), current.closest('a')]).toEqual(['page', null])
    const header = h1().closest('header')
    expect(header.contains(crumbs)).toBe(false)
    expect(crumbs.compareDocumentPosition(header) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(within(header).getByRole('link', { name: 'personal' }).getAttribute('href')).toBe('/workspaces/2')
    unmount()
  }
})

test('FE1: the header has a Branch select after the factory state: the checked-out branch as "", then the others', async () => {
  await open({ [`GET ${API}`]: [200, landing()], [`GET ${BOARD}`]: [200, BOARD_PAGE] })
  const header = document.querySelector('main header')
  const factory = await within(header).findByText('Factory: ready ✓')
  const select = within(header).getByRole('combobox', { name: 'Branch' })
  expect(select.getAttribute('aria-haspopup')).toBe('listbox') // 107: the shared Select
  expect(factory.compareDocumentPosition(select) & FOLLOWING).toBeTruthy()
  expect(options()).toEqual([['main', ''], ['feature-x', 'feature-x'], ['origin/old', 'origin/old']])
  expect(select.value).toBe('')
  expect(select.textContent).toBe('main')
  expect(select.className).toMatch(cls('font-mono'))
  // the old plain `Branch main` text is gone: only the line holding the Select reads so
  expect(screen.queryAllByText(fullText('Branch main')).every((el) => el.contains(select))).toBe(true)
  expect(header.querySelector('code')).toBeNull()
  // round-1 review-ui: the header's flex item shrinks (min-w-0), so the select's max width holds on a 390 px screen
  expect(select.parentElement.className).toMatch(cls('min-w-0'))
  expect(select.className).toMatch(cls('max-w-[min(100%,28rem)]'))
})

test('AC2, FE2, FE3, FE12: "detached HEAD" is the first option, before every listed branch; no select and no Branch text without one', async () => {
  const { unmount } = await open({ [`GET ${API}`]: [200, landing({ branch: 'detached HEAD' })] })
  expect(options()).toEqual([['detached HEAD', ''], ...BRANCHES.map((b) => [b, b])])
  expect(picker().value).toBe('')
  unmount()
  await open({ [`GET ${API}`]: [200, landing({ branch: null, branches: [] })] })
  expect(picker()).toBeNull()
  expect(document.querySelector('main [role="combobox"]')).toBeNull()
  expect(document.querySelector('main').textContent).not.toContain('Branch')
})

test('FE4: ?branch=feature-x is fetched and selected; ?branch=<the checked-out branch> selects the "" option', async () => {
  const { fetch, unmount } = await open({ [`GET ${API}?branch=feature-x`]: [200, landing()] }, '/projects/3/code?branch=feature-x')
  expect(loads(fetch)).toEqual(['/api/pages/projects/3/code?branch=feature-x'])
  expect(picker().value).toBe('feature-x')
  unmount()
  const main = await open({ [`GET ${API}?branch=main`]: [200, landing()] }, '/projects/3/code?branch=main')
  expect(loads(main.fetch)).toEqual(['/api/pages/projects/3/code?branch=main'])
  expect(picker().value).toBe('')
  expect(hrefs()).toEqual(PLAIN_HREFS) // no browsed branch, so no &branch=
})

test('FE5 (Q3): choosing origin/old, from the landing or a file, moves to ?branch=origin%2Fold with no ?path= and fetches it', async () => {
  for (const at of ['/projects/3/code', '/projects/3/code?path=src/a.py']) {
    const { fetch, router, unmount } = await open({
      [`GET ${API}`]: [200, landing()],
      [`GET ${API}?path=src%2Fa.py`]: [200, file('src/a.py', text('x = 1\n'), 'py')],
      [`GET ${API}?branch=origin%2Fold`]: [200, landing({ readme_html: '<h1>Old</h1>\n' })],
    }, at)
    pick('origin/old')
    await waitFor(() => expect(column().querySelector('.markdown')?.textContent.trim()).toBe('Old'))
    expect(router.state.location.pathname).toBe('/projects/3/code')
    expect(router.state.location.search).toBe('?branch=origin%2Fold')
    expect(loads(fetch)).toEqual([at === '/projects/3/code' ? API : `${API}?path=src%2Fa.py`, `${API}?branch=origin%2Fold`])
    expect(picker().value).toBe('origin/old')
    unmount()
  }
})

test('FE6: from ?path=src/a.py&branch=feature-x, the first option moves to /projects/3/code with no query and fetches it', async () => {
  const { fetch, router } = await open({
    [`GET ${API}?path=src%2Fa.py&branch=feature-x`]: [200, file('src/a.py', text('x = 1\n'), 'py')],
    [`GET ${API}`]: [200, landing()],
  }, '/projects/3/code?path=src/a.py&branch=feature-x')
  expect(picker().value).toBe('feature-x')
  pick('')
  await waitFor(() => expect(fileHeader().textContent).toBe('README.md'))
  expect(router.state.location.pathname).toBe('/projects/3/code')
  expect(router.state.location.search).toBe('')
  expect(loads(fetch)).toEqual([`${API}?path=src%2Fa.py&branch=feature-x`, API])
  expect(picker().value).toBe('')
})

test('FE7: while a branch is browsed every Files link keeps &branch=, and a click fetches it; with none they stay as today', async () => {
  const { fetch, router } = await open({
    [`GET ${API}`]: [200, landing()],
    [`GET ${API}?branch=feature-x`]: [200, landing()],
    [`GET ${API}?path=src%2Fa.py&branch=feature-x`]: [200, file('src/a.py', text('x = 1\n'), 'py')],
  })
  expect(hrefs()).toEqual(PLAIN_HREFS)
  pick('feature-x')
  await waitFor(() => expect(loads(fetch)).toHaveLength(2))
  await waitFor(() => expect(hrefs()).toEqual(PLAIN_HREFS.map(([name, href]) => [name, `${href}&branch=feature-x`])))
  openSrc()
  fireEvent.click(link('a.py'))
  await waitFor(() => expect(fileHeader().textContent).toBe('src/a.py'))
  expect(router.state.location.search).toBe('?path=src%2Fa.py&branch=feature-x')
  expect(loads(fetch).at(-1)).toBe(`${API}?path=src%2Fa.py&branch=feature-x`)
  expect(picker().value).toBe('feature-x')
  expect(link('a.py').getAttribute('aria-current')).toBe('page')
})

test('FE8: a branch named origin/feat#1&x round-trips through the select, the URL, the file links, and the API', async () => {
  const name = 'origin/feat#1&x'
  const q = 'branch=origin%2Ffeat%231%26x'
  const { fetch, router } = await open({
    [`GET ${API}`]: [200, landing({ branches: [...BRANCHES, name] })],
    [`GET ${API}?${q}`]: [200, landing({ branches: [...BRANCHES, name] })],
    [`GET ${API}?path=README.md&${q}`]: [200, file('README.md', text('# Feat\n'), 'md', { branches: [...BRANCHES, name] })],
  })
  expect(options().at(-1)).toEqual([name, name])
  pick(name)
  await waitFor(() => expect(loads(fetch)).toEqual([API, `${API}?${q}`]))
  expect(router.state.location.search).toBe(`?${q}`)
  expect(picker().value).toBe(name)
  await waitFor(() => expect(link('README.md').getAttribute('href')).toBe(`/projects/3/code?path=README.md&${q}`))
  fireEvent.click(link('README.md'))
  await waitFor(() => expect(loads(fetch).at(-1)).toBe(`${API}?path=README.md&${q}`))
  expect(router.state.location.search).toBe(`?path=README.md&${q}`)
  expect(picker().value).toBe(name)
})

test('FE9: a 404 for an unknown ?branch= is the not-found state with its detail and no Files nav', async () => {
  const detail = 'nope is not a branch in api'
  const { fetch } = await open({ [`GET ${API}?branch=nope`]: [404, { detail }] }, '/projects/3/code?branch=nope')
  expect(loads(fetch)).toEqual([`${API}?branch=nope`])
  expect(h1().textContent).toBe(detail)
  expect(files()).toBeNull()
  expect(picker()).toBeNull()
})

test('FE10: an empty ?branch= fetches the code view-model with no query', async () => {
  const { fetch } = await open({ [`GET ${API}`]: [200, landing()] }, '/projects/3/code?branch=')
  expect(loads(fetch)).toEqual([API])
  expect(picker().value).toBe('')
  expect(hrefs()).toEqual(PLAIN_HREFS)
})

test('AC3: ?path= is sent encoded and titles the page; an empty ?path= is the landing with no query', async () => {
  const { fetch, unmount } = await openFile('src/a.py', file('src/a.py', text('x = 1\n'), 'py'))
  expect(loads(fetch)).toEqual(['/api/pages/projects/3/code?path=src%2Fa.py'])
  await waitFor(() => expect(document.title).toBe('src/a.py · api · Code · Claude Factories'))
  unmount()
  const empty = await open({ [`GET ${API}`]: [200, landing()] }, '/projects/3/code?path=')
  expect(loads(empty.fetch)).toEqual([API])
})

// --- Tree --------------------------------------------------------------------------------

test('FE9 (AC4): the Files nav is FileTree, nested in the view-model order, with encoded file links', async () => {
  await open({ [`GET ${API}`]: [200, landing()] })
  // FE1 checks the nesting itself; here the view-model's tree reaches FileTree in its Object.entries order
  expect(shape(files().querySelector(':scope > ul'))).toEqual([
    'README.md',
    ['src/', ['a.py', ['lib/', ['b.py']]]],
    ['docs/', ['guide.md']],
  ])
  expect(within(files()).getAllByRole('button').map((b) => [b.textContent, b.getAttribute('aria-expanded')])).toEqual([
    ['src/', 'false'], ['docs/', 'false'],
  ])
  expect(hrefs()).toEqual(PLAIN_HREFS)
})

test('FE10 (AC5): nothing open on the landing; the URL\'s file opens its directories and is the current page', async () => {
  const { unmount } = await open({ [`GET ${API}`]: [200, landing()] })
  expect(within(files()).getAllByRole('button').map((b) => b.getAttribute('aria-expanded'))).toEqual(['false', 'false'])
  expect(files().querySelectorAll('[aria-current]').length).toBe(0) // 047: the breadcrumb's Code is current too
  unmount()
  await openFile('src/lib/b.py', file('src/lib/b.py', text('y = 2\n'), 'py'))
  expect([expanded('src/'), expanded('lib/'), expanded('docs/')]).toEqual(['true', 'true', 'false'])
  expect(link('b.py').getAttribute('aria-current')).toBe('page')
  expect([...files().querySelectorAll('[aria-current]')]).toEqual([link('b.py')])
})

test('FE11: a ?path= change opens the new file\'s directories and keeps the ones I opened', async () => {
  const { router } = await open({
    [`GET ${API}`]: [200, landing()],
    [`GET ${API}?path=docs%2Fguide.md`]: [200, file('docs/guide.md', text('# Guide\n'), 'md')],
  })
  openSrc()
  await act(() => router.navigate('/projects/3/code?path=docs/guide.md'))
  await waitFor(() => expect(fileHeader().textContent).toBe('docs/guide.md'))
  expect(expanded('docs/')).toBe('true')
  expect(link('guide.md').getAttribute('aria-current')).toBe('page')
  expect(expanded('src/')).toBe('true')
  expect(expanded('lib/')).toBe('false')
})

test('AC6, FE12: clicking a.py moves the URL, fetches its view-model, and shows the file', async () => {
  const { fetch, router } = await open({
    [`GET ${API}`]: [200, landing()],
    [`GET ${API}?path=src%2Fa.py`]: [200, file('src/a.py', text('import os\n'), 'py')],
  })
  openSrc()
  fireEvent.click(link('a.py'))
  await waitFor(() => expect(fileHeader().textContent).toBe('src/a.py'))
  expect(router.state.location.pathname).toBe('/projects/3/code')
  expect(router.state.location.search).toBe('?path=src%2Fa.py')
  expect(loads(fetch)).toEqual([API, '/api/pages/projects/3/code?path=src%2Fa.py'])
  expect(codes()[0].textContent).toBe('import os\n')
})

test('AC7: a name with a space, #, and & round-trips through the link, the URL, and the API', async () => {
  const name = 'a b#c&d.txt'
  const { fetch } = await open({
    [`GET ${API}`]: [200, landing({ tree: { [name]: { path: name }, ...TREE } })],
    [`GET ${API}?path=a+b%23c%26d.txt`]: [200, file(name, text('hello\n'), 'txt', { tree: { [name]: { path: name }, ...TREE } })],
  })
  expect(link(name).getAttribute('href')).toBe('/projects/3/code?path=a+b%23c%26d.txt')
  fireEvent.click(link(name))
  await waitFor(() => expect(fileHeader().textContent).toBe(name))
  expect(fileHeader().querySelector('code').textContent).toBe(name)
  expect(loads(fetch).at(-1)).toBe('/api/pages/projects/3/code?path=a+b%23c%26d.txt')
})

// --- Landing -----------------------------------------------------------------------------

test('AC8: the landing shows the README.md header and readme_html as markdown, with no gutter', async () => {
  await open({ [`GET ${API}`]: [200, landing()] })
  expect(fileHeader().querySelector('code').textContent).toBe('README.md')
  const readme = column().querySelector('.markdown')
  expect(within(readme).getByRole('heading', { name: 'Hi' }).tagName).toBe('H1')
  expect(gutter()).toBeNull()
  expect(document.querySelector('main pre')).toBeNull()
})

test('AC9: no README shows the note, no file header, and the tree', async () => {
  await open({ [`GET ${API}`]: [200, landing({ shown: '', view: { note: 'No README.md in this project.' }, readme_html: null })] })
  expect(within(column()).getByText('No README.md in this project.')).toBeTruthy()
  expect(fileHeader()).toBeNull()
  expect(files()).not.toBeNull()
})

test('AC10: a README the backend won\'t show keeps its header and shows the note, not markdown', async () => {
  const note = 'Not shown: points outside the project.'
  await open({ [`GET ${API}`]: [200, landing({ view: { note }, readme_html: null })] })
  expect(fileHeader().querySelector('code').textContent).toBe('README.md')
  expect(within(column()).getByText(note)).toBeTruthy()
  expect(document.querySelector('main .markdown')).toBeNull()
})

// --- Viewer ------------------------------------------------------------------------------

test('AC11: a file shows its header, an aria-hidden gutter of line numbers, and one <pre><code> of its text', async () => {
  const src = 'import os\n\nx = 1\n'
  await openFile('src/a.py', file('src/a.py', { text: src, lines: 3 }, 'py'))
  expect(fileHeader().querySelector('code').textContent).toBe('src/a.py')
  expect(gutter().textContent).toBe('1\n2\n3')
  expect(codes().length).toBe(1)
  expect(codes()[0].textContent).toBe(src)
})

test('AC12: a known extension is highlighted, the whole file at once', async () => {
  const { unmount } = await openFile('src/a.py', file('src/a.py', text('def f():\n    return 1\n'), 'py'))
  const keywords = [...codes()[0].querySelectorAll('span.hljs-keyword')].map((s) => s.textContent)
  expect(keywords).toContain('def')
  unmount()
  await openFile('src/a.py', file('src/a.py', text('x = """a\nb"""\n'), 'py'))
  const strings = codes()[0].querySelectorAll('.hljs-string')
  expect([...strings].map((s) => s.textContent)).toEqual(['"""a\nb"""'])
})

test('AC13: no lang, or one highlight.js doesn\'t know, shows the text as is with no hljs- classes', async () => {
  const src = 'def f():\n    return 1\n'
  for (const lang of [null, 'zzz']) {
    const { unmount } = await openFile('src/a.py', file('src/a.py', text(src), lang))
    expect(highlighted().length).toBe(0)
    expect(codes()[0].textContent).toBe(src)
    unmount()
  }
})

test('AC14: HTML in a file shows as text, highlighted or not, and adds no element', async () => {
  const src = '<img src=x onerror=alert(1)>'
  for (const lang of ['py', null]) {
    const { unmount } = await openFile('src/a.py', file('src/a.py', { text: src, lines: 1 }, lang))
    expect(codes()[0].textContent).toBe(src)
    expect(document.querySelector('main img')).toBeNull()
    unmount()
  }
})

test('AC15: a file note shows under its header, with no gutter and no <pre>', async () => {
  for (const note of ['Binary file not shown.', 'File over 1 MB not shown.', 'Empty file.', 'Not shown: not a regular file.']) {
    const { unmount } = await openFile('src/a.py', file('src/a.py', { note }, 'py'))
    expect(fileHeader().querySelector('code').textContent).toBe('src/a.py')
    const shown = within(column()).getByText(note)
    expect(fileHeader().compareDocumentPosition(shown) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(gutter()).toBeNull()
    expect(document.querySelector('main pre')).toBeNull()
    unmount()
  }
})

// --- States ------------------------------------------------------------------------------

test('AC16: an unknown project is the not-found state with the API\'s detail and a link home', async () => {
  await open({ 'GET /api/pages/projects/99/code': [404, { detail: 'Project #99 not found' }] }, '/projects/99/code')
  expect(h1().textContent).toBe('Project #99 not found')
  expect(within(document.querySelector('main')).getByRole('link', { name: 'Go to the dashboard' }).getAttribute('href')).toBe('/')
})

test('AC17: a path the backend refuses is the not-found state with its detail and no Files nav', async () => {
  const cases = [
    ['../secret.txt', '/api/pages/projects/3/code?path=..%2Fsecret.txt'],
    ['/etc/passwd', '/api/pages/projects/3/code?path=%2Fetc%2Fpasswd'],
  ]
  for (const [path, url] of cases) {
    const detail = `${path} is not a tracked file in api`
    const { fetch, unmount } = await open({ [`GET ${url}`]: [404, { detail }] }, `/projects/3/code?path=${path}`)
    expect(loads(fetch)).toEqual([url])
    expect(h1().textContent).toBe(detail)
    expect(files()).toBeNull()
    unmount()
  }
})

test('AC18: a git failure shows the alert under the header, with no Files nav', async () => {
  const page = landing({
    project: { ...PROJECT, path: '/home/me/gone' }, error: 'fatal: not a git repository', branch: null, branches: [], tree: {},
    shown: '', view: null, lang: null, readme_html: null,
  })
  await open({ [`GET ${API}`]: [200, page] })
  expect(screen.getByRole('alert').textContent).toBe("Can't list files in /home/me/gone: fatal: not a git repository")
  expect(h1().textContent).toBe('api · personal') // FE4: no board view-model mocked; 047 Q1: the code one names it
  expect(files()).toBeNull()
})

test('AC19: an empty tree says No tracked files. and has no Files nav', async () => {
  await open({ [`GET ${API}`]: [200, landing({ tree: {}, shown: '', view: { note: 'No README.md in this project.' }, readme_html: null })] })
  expect(screen.getByText('No tracked files.')).toBeTruthy()
  expect(files()).toBeNull()
})

test('AC20: a failed first load is an alert alone; a failed click keeps the page with an alert', async () => {
  mockFetch({ [`GET ${API}`]: [500, { detail: 'boom' }] })
  const first = renderAt('/projects/3/code')
  expect((await screen.findByRole('alert')).textContent).toBe('boom')
  expect(h1()).toBeNull()
  first.unmount()

  await open({ [`GET ${API}`]: [200, landing()], [`GET ${API}?path=src%2Fa.py`]: [500, { detail: 'boom' }] })
  openSrc()
  fireEvent.click(link('a.py'))
  expect((await screen.findByRole('alert')).textContent).toBe('boom')
  expect(h1().textContent).toBe('api · personal') // FE4: no board view-model mocked; 047 Q1: the code one names it
  expect(files()).not.toBeNull()
})

// --- 090: links to the git host -----------------------------------------------------------

const WEB = 'https://github.com/owner/repo'
const withWeb = { ...PROJECT, web_url: WEB }
const header = () => document.querySelector('main header')
const outLinks = () => [...document.querySelectorAll('main a[target]')]
const newTab = (a) => [a.getAttribute('target'), a.getAttribute('rel')]

test('090 AC12: with web_url the header links to it in a new tab, on the Branch line after the select', async () => {
  await open({ [`GET ${API}`]: [200, landing({ project: withWeb })] })
  const a = within(header()).getByRole('link', { name: 'github.com/owner/repo (opens in a new tab)' })
  expect(a.getAttribute('href')).toBe(WEB)
  expect(newTab(a)).toEqual(['_blank', 'noopener noreferrer'])
  expect(picker().compareDocumentPosition(a) & FOLLOWING).toBeTruthy()
  expect(a.closest('p')).toBe(picker().closest('p'))
})

test('090 AC12, Q4: with no Branch line (a git failure) the repo link has its own line', async () => {
  const page = landing({
    project: withWeb, error: 'fatal: not a git repository', branch: null, branches: [], tree: {},
    shown: '', view: null, lang: null, readme_html: null,
  })
  await open({ [`GET ${API}`]: [200, page] })
  expect(picker()).toBeNull()
  const a = within(header()).getByRole('link', { name: /^github\.com\/owner\/repo/ })
  expect(a.getAttribute('href')).toBe(WEB)
  expect(a.closest('p').className).toMatch(cls('basis-full'))
})

test('090 AC13: with web_url null or absent there is no repo link and the page renders as today', async () => {
  const { unmount } = await open({ [`GET ${API}`]: [200, landing()] })
  expect(outLinks()).toEqual([])
  expect(picker()).not.toBeNull()
  unmount()
  const { web_url: _, ...older } = PROJECT
  await open({ [`GET ${API}`]: [200, landing({ project: older })] })
  expect(outLinks()).toEqual([])
  expect(fileHeader().textContent).toBe('README.md')
})

test('090 AC14: file_url adds a second link beside the file h2; null adds none', async () => {
  const url = `${WEB}/blob/main/src/a.py`
  const { unmount } = await openFile('src/a.py', file('src/a.py', text('a = 1\n'), 'py', { project: withWeb, file_url: url }))
  const a = screen.getByRole('link', { name: 'View on github.com (opens in a new tab)' })
  expect(a.getAttribute('href')).toBe(url)
  expect(newTab(a)).toEqual(['_blank', 'noopener noreferrer'])
  expect(a.parentElement).toBe(fileHeader().parentElement)
  expect(fileHeader().compareDocumentPosition(a) & FOLLOWING).toBeTruthy()
  expect(fileHeader().textContent).toBe('src/a.py')
  unmount()
  await openFile('src/a.py', file('src/a.py', text('a = 1\n'), 'py', { project: withWeb, file_url: null }))
  expect(outLinks().map((l) => l.getAttribute('href'))).toEqual([WEB])
})

test('090 AC15: each link names where it goes and that it opens in a new tab', async () => {
  const url = `${WEB}/blob/main/src/a.py`
  await openFile('src/a.py', file('src/a.py', text('a = 1\n'), 'py', { project: withWeb, file_url: url }))
  const names = outLinks().map((a) => a.textContent)
  expect(names).toEqual(['github.com/owner/repo (opens in a new tab)', 'View on github.com (opens in a new tab)'])
  for (const a of outLinks()) expect(a.querySelector('span').className).toMatch(cls('sr-only'))
})
