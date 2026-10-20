import { act, cleanup, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { fetched, mockFetch, renderAt } from '../../test/render.jsx'

const PAGE = '/api/pages/tasks/12/review'
const COMMENTS = '/api/tasks/12/comments'
const APPROVE = '/api/tasks/12/approve'
const CHANGES = '/api/tasks/12/request-changes'
const WORKTREE = '/Users/me/api/.claude/worktrees/12-rate-limit-login'
const HINT = `cd ${WORKTREE}\ngit add -A && git commit -m 'Rate-limit login'`
const PASS = { security: 'PASS', ux: 'PASS', ui: 'PASS', code: 'PASS' }
const PENDING = { security: 'pending', ux: 'pending', ui: 'pending', code: 'pending' }
const M = '−' // the minus sign in every +A −D

/** 020's ReviewTask, with 047's workspace: the spec's fixture task. */
const TASK = {
  id: 12, project_id: 3, project: 'api', workspace_id: 2, workspace: 'personal', title: 'Rate-limit login', status: 'review', stage: 'human_review',
  branch: 'factory/12-rate-limit-login', worktree_path: WORKTREE,
  description_md: '', description_html: '', spec_md: null, spec_html: '', commit_hint: null,
}
/** ReviewRound. */
const ROUND1 = { n: 1, trigger: 'initial', files: 2, additions: 118, deletions: 9, verdicts: { ...PASS, security: 'CHANGES' }, posted: {} }
const ROUND2 = { n: 2, trigger: 'agent', files: 2, additions: 126, deletions: 9, verdicts: PASS, posted: {} }
/** RoundSummary: a ReviewRound without `posted`. */
const summary = ({ posted, ...rest }) => rest
/** 020's ReviewPage view-model; `task` overrides fields of the fixture task. */
const reviewPage = (task = {}, extra = {}) => ({
  task: { ...TASK, ...task }, rounds: [ROUND1, ROUND2], selected: summary(ROUND2), approver: null, files: [],
  timeline: [], ...extra,
})
const noRounds = (task = {}) => reviewPage(task, { rounds: [], selected: null })

/** DiffRow, with the backend's side and anchor (020 Q5). */
function row(path, kind, old, nw, text, comments = []) {
  const side = { add: 'new', ctx: 'new', del: 'old' }[kind] ?? null
  return { kind, old, new: nw, side, anchor: side && `${path}:${side}:${side === 'new' ? nw : old}`, text, comments }
}
/** FileOut. */
const file = (path, extra = {}) => ({
  path, old_path: null, change: 'modified', binary: false, additions: 0, deletions: 0, lang: null, rows: [], orphans: [],
  ...extra,
})
/** Comment. */
const comment = (id, line, extra = {}) => ({
  id, author: 'security', path: 'app.py', line, side: 'new', body_md: 'Use **host**',
  body_html: '<p>Use <strong>host</strong></p>\n', ...extra,
})
const APP_ROWS = [
  row('app.py', 'hunk', null, null, '@@ -1,2 +1,3 @@'),
  row('app.py', 'ctx', 1, 1, 'import os'),
  row('app.py', 'add', null, 2, 'x = 1'),
  row('app.py', 'del', 2, null, 'y = 2'),
]
const appFile = (extra = {}) => file('app.py', { additions: 1, deletions: 1, lang: 'py', rows: APP_ROWS, ...extra })

beforeEach(() => {
  vi.stubEnv('TZ', 'Asia/Tokyo') // UTC+9, as in the other page tests
})
afterEach(() => {
  vi.useRealTimers() // 046 FE6's clock
})

/** Renders `path` with `page` as the view-model its round fetches; mutate `responses` to change later replies. */
async function open(page, path = '/tasks/12/review', more = {}) {
  const round = new URLSearchParams(path.split(/[?#]/)[1]).get('round')
  const responses = { [`GET ${PAGE}${round ? `?round=${round}` : ''}`]: [200, page], ...more }
  const fetch = mockFetch(responses)
  const view = renderAt(path)
  await screen.findByRole('heading', { level: 1 })
  return { fetch, responses, ...view }
}
const openFiles = (page, more) => open(page, '/tasks/12/review?tab=files', more)

const loads = (fetch) => fetched(fetch).filter((url) => url.startsWith(PAGE)).length
const header = () => document.querySelector('main header')
const section = (name) => screen.getByRole('region', { name })
const tabs = () => screen.getByRole('navigation', { name: 'Review tabs' })
const tab = (name) => within(tabs()).getByRole('link', { name })
const rows = () => [...section('Rounds').querySelectorAll('ol > li')]
const tr = (id) => document.getElementById(id)
const fileRows = (path) => [...document.getElementById(`file:${path}`).querySelectorAll('tbody > tr')]
const inlineBoxes = () => [...document.querySelectorAll('table textarea')]
const headerButton = (name) => within(header()).getByRole('button', { name })

/** The one POST to `url`: asserts its X-Requested-By and returns its parsed body. */
function sent(fetch, url) {
  const calls = fetch.mock.calls.filter(([u, init]) => u === url && init?.method === 'POST')
  expect(calls).toHaveLength(1)
  expect(calls[0][1].headers['X-Requested-By']).toBe('fctl')
  return JSON.parse(calls[0][1].body)
}

/** `url` went out before the last view-model load. */
function postedBeforeReload(fetch, url) {
  const urls = fetched(fetch)
  expect(urls.indexOf(url)).toBeGreaterThan(-1)
  expect(urls.indexOf(url)).toBeLessThan(urls.findLastIndex((u) => u.startsWith(PAGE)))
}

// --- Header and URL ----------------------------------------------------------------------

test('AC1, 047 FE3: /tasks/12/review fetches the view-model with no query and shows the title, breadcrumb, and page title', async () => {
  const { fetch } = await open(reviewPage())
  expect(fetched(fetch).filter((url) => url.startsWith('/api/pages/tasks'))).toEqual([PAGE])
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('#12 Rate-limit login')
  const crumbs = screen.getByRole('navigation', { name: 'Breadcrumb' })
  expect(crumbs.closest('header')).toBe(header())
  expect(crumbs.textContent).toBe('personal › api › #12 › Review')
  expect(within(crumbs).getAllByRole('link').map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
    ['personal', '/workspaces/2'], ['api', '/projects/3'], ['#12', '/tasks/12'],
  ])
  const current = within(crumbs).getByText('Review')
  expect([current.getAttribute('aria-current'), current.closest('a')]).toEqual(['page', null])
  await waitFor(() => expect(document.title).toBe('#12 Rate-limit login · Review · Claude Factories'))
})

const cls = (name) => new RegExp(`(^|\\s)${name}(\\s|$)`)

test('AC2, 043 FE12: the status pill and stage, the branch in a <code>, and the selected round\'s files and +/−', async () => {
  const cases = [
    ['review', 'human_review', 'Review', 'text-warning', ['waiting on you', 'bg-warning']],
    ['review', 'escalated', 'Review', 'text-warning', ['escalated', 'bg-danger']],
    ['in_progress', 'build', 'In progress', 'text-accent', ['build', 'text-muted']],
    ['backlog', null, 'Backlog', 'text-muted', null],
    ['done', null, 'Done', 'text-success', null],
  ]
  for (const [status, stage, label, tone, after] of cases) {
    const { unmount } = await open(reviewPage({ status, stage }))
    const pill = within(header().querySelector(':scope > p')).getByText(label, { selector: 'span' }) // 047: not the breadcrumb's Review
    expect(pill.className).toMatch(cls(tone))
    const state = [...pill.parentElement.children]
    expect(state.map((el) => el.textContent)).toEqual(after ? [label, after[0]] : [label])
    if (after) expect(state[1].className).toMatch(cls(after[1]))
    expect(header().textContent).not.toContain('●')
    unmount()
  }
  const two = await open(reviewPage())
  expect(within(header()).getByText('factory/12-rate-limit-login').tagName).toBe('CODE')
  expect(within(header()).getByText(`2 files changed +126 ${M}9`)).toBeTruthy()
  two.unmount()
  await open(reviewPage({}, { selected: { ...summary(ROUND2), files: 1, additions: 3, deletions: 0 } }))
  expect(within(header()).getByText(`1 file changed +3 ${M}0`)).toBeTruthy()
})

test('AC3: the round <select> lists the rounds; picking 1 sets ?round=1 and shows its totals', async () => {
  const { fetch, router } = await open(reviewPage(), '/tasks/12/review', {
    [`GET ${PAGE}?round=1`]: [200, reviewPage({}, { selected: summary(ROUND1) })],
  })
  const select = within(header()).getByLabelText('round')
  expect(select.tagName).toBe('SELECT')
  expect([...select.options].map((o) => o.textContent)).toEqual(['1', '2'])
  expect(select.value).toBe('2')
  fireEvent.change(select, { target: { value: '1' } })
  expect(router.state.location.search).toBe('?round=1')
  await waitFor(() => expect(fetched(fetch)).toContain(`${PAGE}?round=1`))
  expect(await within(header()).findByText(`2 files changed +118 ${M}9`)).toBeTruthy()
  expect(within(header()).getByLabelText('round').value).toBe('1')
})

test('AC4: ?round=1&tab=files fetches round 1 and shows Files changed; the tab links keep round and mark the active one', async () => {
  const { fetch, unmount } = await open(reviewPage({}, { selected: summary(ROUND1), files: [appFile()] }), '/tasks/12/review?round=1&tab=files')
  expect(fetched(fetch).filter((url) => url.startsWith('/api/pages/tasks'))).toEqual([`${PAGE}?round=1`])
  expect(screen.getByRole('navigation', { name: 'Files' })).toBeTruthy()
  expect(tab('Conversation').getAttribute('href')).toBe('/tasks/12/review?round=1')
  expect(tab('Files changed 2').getAttribute('href')).toBe('/tasks/12/review?round=1&tab=files')
  expect(tab('Conversation').hasAttribute('aria-current')).toBe(false)
  expect(tab('Files changed 2').getAttribute('aria-current')).toBe('page')
  unmount()

  for (const path of ['/tasks/12/review', '/tasks/12/review?tab=bogus']) {
    const { unmount } = await open(reviewPage(), path)
    expect(tab('Conversation').getAttribute('href')).toBe('/tasks/12/review')
    expect(tab('Files changed 2').getAttribute('href')).toBe('/tasks/12/review?tab=files')
    expect(tab('Conversation').getAttribute('aria-current')).toBe('page')
    expect(tab('Files changed 2').hasAttribute('aria-current')).toBe(false)
    expect(section('Description')).toBeTruthy()
    expect(screen.queryByRole('navigation', { name: 'Files' })).toBeNull()
    unmount()
  }
})

test('AC5: clicking between the tabs fetches nothing', async () => {
  const { fetch, router } = await open(reviewPage({}, { files: [appFile()] }))
  fireEvent.click(tab('Files changed 2'))
  expect(await screen.findByRole('navigation', { name: 'Files' })).toBeTruthy()
  expect(router.state.location.search).toBe('?tab=files')
  fireEvent.click(tab('Conversation'))
  expect(await screen.findByRole('region', { name: 'Description' })).toBeTruthy()
  expect(fetched(fetch).filter((url) => url.startsWith('/api/pages/tasks'))).toEqual([PAGE])
})

test('AC6: a title with markup shows as text and adds no script', async () => {
  await open(reviewPage({ title: '<script>alert(1)</script>' }))
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('#12 <script>alert(1)</script>')
  expect(document.querySelector('main script')).toBeNull()
})

// --- Conversation ------------------------------------------------------------------------

test('AC7: the description renders its HTML or says No description.; a non-blank spec sits in a closed Spec <details>', async () => {
  const withText = await open(reviewPage({
    description_md: 'Max **5**', description_html: '<p>Max <strong>5</strong></p>\n',
    spec_md: '## Criteria\n\n- 429\n', spec_html: '<h2>Criteria</h2>\n<ul>\n<li>429</li>\n</ul>\n',
  }))
  expect(section('Description').querySelector('.markdown strong').textContent).toBe('5')
  const details = section('Description').querySelectorAll('details')
  expect(details).toHaveLength(1)
  expect(details[0].hasAttribute('open')).toBe(false)
  expect(details[0].querySelector('summary').textContent).toBe('Spec')
  expect(within(details[0]).getByText('429').tagName).toBe('LI')
  withText.unmount()
  for (const spec_md of [null, '  \n']) {
    const { unmount } = await open(reviewPage({ spec_md }))
    expect(within(section('Description')).getByText('No description.')).toBeTruthy()
    expect(screen.queryByText('Spec', { selector: 'summary' })).toBeNull()
    unmount()
  }
})

test('AC8, 043 FE12, 047 FE17: rounds show in order with plain colored chips titled by verdict, and no chip popovers', async () => {
  await open(reviewPage())
  expect(rows().map((li) => li.querySelector('p').textContent)).toEqual([
    `Round 1 initial sec ✗ ux ✓ ui ✓ code ✓ +118 ${M}9`,
    `Round 2 agent sec ✓ ux ✓ ui ✓ code ✓ +126 ${M}9`,
  ])
  const chips = [...rows()[0].querySelectorAll('p [title]')]
  expect(chips.map((el) => el.tagName)).toEqual(['SPAN', 'SPAN', 'SPAN', 'SPAN'])
  expect(chips.map((el) => el.getAttribute('title'))).toEqual(['security: CHANGES', 'ux: PASS', 'ui: PASS', 'code: PASS'])
  // 043 FE12: colored as in FE5
  expect(chips.map((el) => ['text-success', 'text-danger'].find((c) => cls(c).test(el.className)))).toEqual([
    'text-danger', 'text-success', 'text-success', 'text-success',
  ])
  expect(section('Rounds').querySelector('[popover], [popovertarget]')).toBeNull()
  // 047: Review changes' is the page's one popover
  expect([...document.querySelectorAll('[popover]')].map((el) => el.id)).toEqual(['review-changes'])
  expect([...document.querySelectorAll('[popovertarget]')].map((el) => el.textContent)).toEqual(['Review changes ▾'])
})

test('AC9: posted verdicts with a body are closed <details> in reviewer order; a blank body gets none', async () => {
  const security = {
    verdict: 'CHANGES', body_md: 'app/limits.py:31 trusts X-Forwarded-For\n\nUse **host**',
    body_html: '<p>app/limits.py:31 trusts X-Forwarded-For</p>\n<p>Use <strong>host</strong></p>\n',
  }
  const ux = { verdict: 'PASS', body_md: '\nReads well\n', body_html: '<p>Reads well</p>\n' }
  const ui = { verdict: 'PASS', body_md: '  \n', body_html: '' }
  await open(reviewPage({}, { rounds: [{ ...ROUND1, posted: { ux, ui, security } }, ROUND2] }))
  const details = [...rows()[0].querySelectorAll('details')]
  expect(details.map((d) => d.querySelector('summary').textContent)).toEqual([
    'security · CHANGES app/limits.py:31 trusts X-Forwarded-For',
    'ux · PASS Reads well',
  ])
  expect(details.map((d) => d.hasAttribute('open'))).toEqual([false, false])
  expect(within(details[0]).getByText('host').tagName).toBe('STRONG')
  expect(rows()[1].querySelector('details')).toBeNull()
})

test('AC10: a standalone round with nothing posted says no agent review; a factory one shows four pending chips', async () => {
  const pending = { ...ROUND1, verdicts: PENDING, posted: {} }
  const standalone = await open(reviewPage({ worktree_path: null }, { rounds: [pending], selected: summary(pending) }))
  expect(rows()[0].querySelector('p').textContent).toBe(`Round 1 initial no agent review +118 ${M}9`)
  expect(rows()[0].querySelectorAll('[title]')).toHaveLength(0)
  standalone.unmount()
  await open(reviewPage({}, { rounds: [pending], selected: summary(pending) }))
  expect(rows()[0].querySelector('p').textContent).toBe(`Round 1 initial sec · ux · ui · code · +118 ${M}9`)
  expect([...rows()[0].querySelectorAll('[title]')].map((el) => el.getAttribute('title'))).toEqual([
    'security: pending', 'ux: pending', 'ui: pending', 'code: pending',
  ])
})

test('AC11: no rounds says No rounds yet., with no round <select> and no files changed', async () => {
  await open(noRounds())
  expect(within(section('Rounds')).getByText('No rounds yet.')).toBeTruthy()
  expect(screen.queryByRole('combobox')).toBeNull()
  expect(screen.queryByText(/files? changed/)).toBeNull()
})

test("AC12: the approver's decision shows with its round and rendered body; null shows none", async () => {
  const approved = await open(reviewPage({}, {
    approver: { decision: 'APPROVE', n: 2, body_md: 'All **4** PASS', body_html: '<p>All <strong>4</strong> PASS</p>\n' },
  }))
  const block = screen.getByRole('region', { name: 'Approver' })
  expect(block.textContent.startsWith('Approver · APPROVE')).toBe(true)
  expect(block.textContent).toContain('round 2')
  expect(within(block).getByText('4').tagName).toBe('STRONG')
  approved.unmount()
  await open(reviewPage())
  expect(screen.queryByText(/Approver ·/)).toBeNull()
})

test('AC13, 046 FE6: the timeline is an ordered list of relative times with local titles, labels, and rendered bodies; no polling', async () => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-18T03:02:00Z'))
  const fetch = mockFetch({
    [`GET ${PAGE}`]: [200, reviewPage({}, {
      timeline: [
        { created_at: '2026-10-18T01:02:00Z', kind: 'event', id: 1, label: 'created · backlog', body_md: null, body_html: '' },
        { created_at: '2026-10-18T01:41:00Z', kind: 'decision', id: 7, label: 'approver APPROVE · round 2', body_md: 'All **4**', body_html: '<p>All <strong>4</strong></p>\n' },
      ],
    })],
  })
  renderAt('/tasks/12/review')
  await act(() => vi.advanceTimersByTimeAsync(0))
  const items = [...section('Timeline').querySelectorAll('ol > li')]
  expect(items).toHaveLength(2)
  expect(items[0].textContent).toBe('2h ago created · backlog')
  expect(items[1].textContent.startsWith('1h ago approver APPROVE · round 2')).toBe(true)
  expect(items.map((li) => li.querySelector('time').getAttribute('datetime'))).toEqual([
    '2026-10-18T01:02:00Z', '2026-10-18T01:41:00Z',
  ])
  expect(items.map((li) => li.querySelector('time').getAttribute('title'))).toEqual(['2026-10-18 10:02', '2026-10-18 10:41'])
  expect(within(items[1]).getByText('4').tagName).toBe('STRONG')
  await act(() => vi.advanceTimersByTimeAsync(10_000)) // Q3: still loaded once
  expect(fetched(fetch).filter((url) => url === PAGE)).toHaveLength(1)
})

test('AC14: the comment box posts my comment, reloads, and empties; Comment is disabled while blank', async () => {
  const { fetch } = await open(reviewPage(), '/tasks/12/review', { [`POST ${COMMENTS}`]: [201, { id: 90 }] })
  const box = screen.getByLabelText('Comment')
  expect(box.tagName).toBe('TEXTAREA')
  expect(box.getAttribute('placeholder')).toBe('Leave a comment…')
  const button = within(box.closest('form')).getByRole('button', { name: 'Comment' })
  expect(button.disabled).toBe(true)
  fireEvent.change(box, { target: { value: ' \n ' } })
  expect(button.disabled).toBe(true)
  fireEvent.change(box, { target: { value: 'Looks good' } })
  expect(button.disabled).toBe(false)
  fireEvent.click(button)
  await waitFor(() => expect(loads(fetch)).toBe(2))
  expect(sent(fetch, COMMENTS)).toEqual({ author: 'me', body_md: 'Looks good' })
  postedBeforeReload(fetch, COMMENTS)
  expect(screen.getByLabelText('Comment').value).toBe('')
})

test('AC15: a refused conversation comment shows its detail inside the form and keeps the text', async () => {
  const { fetch } = await open(reviewPage(), '/tasks/12/review', {
    [`POST ${COMMENTS}`]: [422, { detail: 'body_md must not be blank' }],
  })
  const box = screen.getByLabelText('Comment')
  fireEvent.change(box, { target: { value: 'Looks good' } })
  fireEvent.click(within(box.closest('form')).getByRole('button', { name: 'Comment' }))
  const alert = await within(box.closest('form')).findByRole('alert')
  expect(alert.textContent).toBe('body_md must not be blank')
  expect(box.value).toBe('Looks good')
  sent(fetch, COMMENTS)
  expect(loads(fetch)).toBe(1)
})

test('AC16: with no rounds the Conversation tab says comments open later and has no comment box', async () => {
  await open(noRounds())
  expect(screen.getByText('Comments open once a round is submitted.')).toBeTruthy()
  expect(screen.queryByLabelText('Comment')).toBeNull()
})

// --- Files changed -----------------------------------------------------------------------

test('AC17: the file tree nests directories in patch order, each file a fragment link with +/−', async () => {
  await openFiles(reviewPage({}, {
    files: [
      file('app/limits.py', { additions: 42 }),
      file('README.md', { additions: 1, deletions: 1 }),
      file('app/auth.py', { additions: 12, deletions: 3 }),
    ],
  }))
  const tree = screen.getByRole('navigation', { name: 'Files' })
  const top = [...tree.querySelector('ul').children]
  expect(top).toHaveLength(2)
  expect(top[0].firstChild.textContent).toBe('app/')
  const nested = [...top[0].querySelector('ul').children]
  expect(nested.map((li) => li.textContent)).toEqual([`limits.py +42 ${M}0`, `auth.py +12 ${M}3`])
  expect(top[1].textContent).toBe(`README.md +1 ${M}1`)
  expect([...tree.querySelectorAll('a')].map((a) => a.getAttribute('href'))).toEqual([
    '#file:app/limits.py', '#file:app/auth.py', '#file:README.md',
  ])
})

test('AC18: each file is a section headed by its path, its change, and +/−', async () => {
  await openFiles(reviewPage({}, {
    files: [
      file('app/new.py', { change: 'added', additions: 5 }),
      file('app/old.py', { change: 'deleted', deletions: 7 }),
      file('app/moved.py', { change: 'renamed', old_path: 'app/was.py', additions: 1, deletions: 1 }),
      file('app/same.py', { additions: 2, deletions: 2 }),
    ],
  }))
  const heading = (path) => {
    const el = document.getElementById(`file:${path}`)
    expect(el.tagName).toBe('SECTION')
    const h = el.querySelector('h2')
    expect(h.querySelector('code').textContent).toBe(path)
    return h.textContent
  }
  expect(heading('app/new.py')).toBe(`app/new.py (new) +5 ${M}0`)
  expect(heading('app/old.py')).toBe(`app/old.py (deleted) +0 ${M}7`)
  expect(heading('app/moved.py')).toBe(`app/moved.py (renamed from app/was.py) +1 ${M}1`)
  expect(heading('app/same.py')).toBe(`app/same.py +2 ${M}2`)
})

test('AC19: one <tr> per row; line rows carry the anchor id and link only the number on their side', async () => {
  await openFiles(reviewPage({}, { files: [appFile({ lang: null })] }))
  const trs = fileRows('app.py')
  expect(trs).toHaveLength(4)
  const [hunk, ctx, add, del] = trs
  expect(hunk.children).toHaveLength(1)
  expect(hunk.textContent).toBe('@@ -1,2 +1,3 @@')
  expect(hunk.querySelector('a')).toBeNull()
  expect([ctx, add, del]).toEqual([tr('app.py:new:1'), tr('app.py:new:2'), tr('app.py:old:2')])

  const cells = (el) => [...el.children].map((td) => td.textContent)
  const links = (el) => [...el.querySelectorAll('a')].map((a) => [a.closest('td').cellIndex, a.getAttribute('href'), a.textContent])
  expect(cells(add)).toEqual(['', '2', '+', 'x = 1'])
  expect(links(add)).toEqual([[1, '#app.py:new:2', '2']])
  expect(cells(del)).toEqual(['2', '', '-', 'y = 2'])
  expect(links(del)).toEqual([[0, '#app.py:old:2', '2']])
  expect(cells(ctx)).toEqual(['1', '1', '', 'import os'])
  expect(links(ctx)).toEqual([[1, '#app.py:new:1', '1']])
})

test('AC20: a note row is one cell of text with no number or link', async () => {
  await openFiles(reviewPage({}, {
    files: [file('logo.png', { binary: true, rows: [row('logo.png', 'note', null, null, 'Binary file not shown.')] })],
  }))
  const [note] = fileRows('logo.png')
  expect(note.children).toHaveLength(1)
  expect(note.textContent).toBe('Binary file not shown.')
  expect(note.querySelector('a')).toBeNull()
  expect(note.hasAttribute('id')).toBe(false)
})

test('AC21: a known lang is colored by highlight.js; null or unknown shows the text as is', async () => {
  const fn = (path, lang) => file(path, { lang, rows: [row(path, 'add', null, 1, 'def f():')] })
  await openFiles(reviewPage({}, { files: [fn('a.py', 'py'), fn('b', null), fn('c.zzz', 'zzz')] }))
  const code = (id) => tr(id).lastElementChild
  expect(code('a.py:new:1').querySelector('span.hljs-keyword').textContent).toBe('def')
  expect(code('a.py:new:1').textContent).toBe('def f():')
  for (const id of ['b:new:1', 'c.zzz:new:1']) {
    expect(code(id).querySelector('[class*="hljs-"]')).toBeNull()
    expect(code(id).textContent).toBe('def f():')
  }
})

test('AC22: diff text with markup shows as text, highlighted or not, and adds no element', async () => {
  const img = '<img src=x onerror=alert(1)>'
  const fn = (path, lang) => file(path, { lang, rows: [row(path, 'add', null, 1, img)] })
  await openFiles(reviewPage({}, { files: [fn('a.py', 'py'), fn('b', null)] }))
  expect(tr('a.py:new:1').lastElementChild.textContent).toBe(img)
  expect(tr('b:new:1').lastElementChild.textContent).toBe(img)
  expect(document.querySelector('main img')).toBeNull()
})

test("AC23: a row's comments show in the <tr> after it; orphans show after the file's last row with their line", async () => {
  const rowsWithComment = APP_ROWS.map((r) => (r.anchor === 'app.py:new:2' ? { ...r, comments: [comment(88, 2)] } : r))
  await openFiles(reviewPage({}, { files: [appFile({ rows: rowsWithComment, orphans: [comment(88, 40)] })] }))
  const under = tr('app.py:new:2').nextElementSibling
  expect(under.id).toBe('')
  expect(under.textContent).toContain('security')
  expect(within(under).getByText('host').tagName).toBe('STRONG')
  expect(under.nextElementSibling).toBe(tr('app.py:old:2'))
  const last = fileRows('app.py').at(-1)
  expect(last.previousElementSibling).toBe(tr('app.py:old:2'))
  expect(last.textContent.startsWith('security on line 40 (new)')).toBe(true)
  expect(last.textContent).toContain('Use host')
})

test('AC24: a line number opens one inline form after the row and its comments; another moves it; Cancel sends nothing', async () => {
  const rowsWithComment = APP_ROWS.map((r) => (r.anchor === 'app.py:new:2' ? { ...r, comments: [comment(88, 2)] } : r))
  const { fetch } = await openFiles(reviewPage({}, { files: [appFile({ rows: rowsWithComment })] }))
  fireEvent.click(within(tr('app.py:new:2')).getByRole('link', { name: '2' }))
  const formRow = tr('app.py:new:2').nextElementSibling.nextElementSibling
  expect(inlineBoxes()).toEqual([within(formRow).getByLabelText('Comment on app.py line 2 (new)')])

  fireEvent.click(within(tr('app.py:old:2')).getByRole('link', { name: '2' }))
  expect(inlineBoxes()).toHaveLength(1)
  const box = screen.getByLabelText('Comment on app.py line 2 (old)')
  expect(inlineBoxes()).toEqual([box])
  expect(box.closest('tr').previousElementSibling).toBe(tr('app.py:old:2'))

  fireEvent.click(within(box.closest('form')).getByRole('button', { name: 'Cancel' }))
  expect(inlineBoxes()).toEqual([])
  expect(fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toEqual([])
})

test('AC25: an inline comment posts on the selected round at its line and side, reloads, closes, and shows under the row', async () => {
  const { fetch, responses } = await openFiles(reviewPage({}, { files: [appFile()] }), {
    [`POST ${COMMENTS}`]: [201, { id: 91 }],
  })
  fireEvent.click(within(tr('app.py:new:2')).getByRole('link', { name: '2' }))
  const box = screen.getByLabelText('Comment on app.py line 2 (new)')
  const button = within(box.closest('form')).getByRole('button', { name: 'Comment' })
  expect(button.disabled).toBe(true)
  fireEvent.change(box, { target: { value: 'Use X' } })
  expect(button.disabled).toBe(false)
  const mine = comment(91, 2, { author: 'me', body_md: 'Use X', body_html: '<p>Use X</p>\n' })
  const withMine = APP_ROWS.map((r) => (r.anchor === 'app.py:new:2' ? { ...r, comments: [mine] } : r))
  responses[`GET ${PAGE}`] = [200, reviewPage({}, { files: [appFile({ rows: withMine })] })]
  fireEvent.click(button)
  await waitFor(() => expect(loads(fetch)).toBe(2))
  expect(sent(fetch, COMMENTS)).toEqual({ round: 2, author: 'me', path: 'app.py', line: 2, side: 'new', body_md: 'Use X' })
  postedBeforeReload(fetch, COMMENTS)
  await waitFor(() => expect(within(tr('app.py:new:2').nextElementSibling).getByText('Use X').tagName).toBe('P'))
  expect(within(tr('app.py:new:2').nextElementSibling).getByText('me').tagName).toBe('STRONG')
  expect(inlineBoxes()).toEqual([])
})

test('AC26: a refused inline comment shows its detail inside the form, which stays open with the text', async () => {
  const { fetch } = await openFiles(reviewPage({}, { files: [appFile()] }), {
    [`POST ${COMMENTS}`]: [422, { detail: 'app.py is not in round 2' }],
  })
  fireEvent.click(within(tr('app.py:new:2')).getByRole('link', { name: '2' }))
  const box = screen.getByLabelText('Comment on app.py line 2 (new)')
  fireEvent.change(box, { target: { value: 'Use X' } })
  fireEvent.click(within(box.closest('form')).getByRole('button', { name: 'Comment' }))
  const alert = await within(box.closest('form')).findByRole('alert')
  expect(alert.textContent).toBe('app.py is not in round 2')
  expect(inlineBoxes()).toEqual([box])
  expect(box.value).toBe('Use X')
  sent(fetch, COMMENTS)
  expect(loads(fetch)).toBe(1)
})

test('AC27: a deep link scrolls its row into view once the view-model has loaded', async () => {
  const scrolled = []
  Element.prototype.scrollIntoView = function () {
    scrolled.push(this)
  }
  try {
    await open(reviewPage({}, { files: [appFile()] }), '/tasks/12/review?tab=files#app.py:new:2')
    await waitFor(() => expect(scrolled).toEqual([tr('app.py:new:2')]))
    expect(inlineBoxes()).toEqual([])
  } finally {
    delete Element.prototype.scrollIntoView // jsdom has none
  }
})

test('AC28: Files changed with no rounds says No rounds yet. and has no tree or table', async () => {
  await openFiles(noRounds())
  expect(screen.getByText('No rounds yet.')).toBeTruthy()
  expect(screen.queryByRole('navigation', { name: 'Files' })).toBeNull()
  expect(document.querySelector('main table')).toBeNull()
})

// --- 047: Review changes and Commit it yourself -------------------------------------------

const titleRow = () => screen.getByRole('heading', { level: 1 }).parentElement
/** Review changes' popover, shown as a click would, with hidePopover stubbed: jsdom has no Popover API. */
function reviewChanges() {
  const popover = document.getElementById(headerButton('Review changes').getAttribute('popovertarget'))
  popover.style.display = 'grid' // jsdom's UA sheet hides it while closed
  popover.hidePopover = vi.fn()
  return popover
}
const radio = (popover, name) => within(popover).getByRole('radio', { name })
const submitReview = (popover) => within(popover).getByRole('button', { name: 'Submit review' })
const summaryBox = (popover) => within(popover).getByLabelText('Summary')
const chosen = (popover) => within(popover).getAllByRole('radio').filter((r) => r.checked).map((r) => r.value)

test('047 FE9: no Approve, Request changes, or Summary outside a popover; Review changes on the title row opens one holding them', async () => {
  await open(reviewPage())
  expect(screen.queryAllByRole('button', { name: /^(Approve|Request changes)$/, hidden: true })).toEqual([])
  const button = within(titleRow()).getByRole('button', { name: 'Review changes' })
  const popover = document.getElementById(button.getAttribute('popovertarget'))
  expect(popover.getAttribute('popover')).toBe('auto')
  const summaries = screen.getAllByLabelText('Summary')
  expect(summaries).toHaveLength(1)
  expect(summaries[0].tagName).toBe('TEXTAREA')
  expect(summaries[0].closest('[popover]')).toBe(popover)
  expect(summaries[0].hasAttribute('autofocus')).toBe(true)
  const radios = within(popover).getAllByRole('radio', { hidden: true })
  expect(radios.map((r) => r.labels[0].textContent)).toEqual(['Approve', 'Request changes'])
  expect(radios.map((r) => [within(popover).getByRole('radio', { name: r.labels[0].textContent, hidden: true }), r.name])).toEqual([
    [radios[0], 'decision'], [radios[1], 'decision'],
  ])
  expect(within(popover).getByRole('button', { name: 'Submit review', hidden: true })).toBeTruthy()
})

test('047 FE10: Review changes is enabled only in review with a round', async () => {
  const review = await open(reviewPage())
  expect(headerButton('Review changes').disabled).toBe(false)
  review.unmount()
  for (const page of [reviewPage({ status: 'in_progress', stage: 'build' }), reviewPage({ status: 'done', stage: null }), noRounds()]) {
    const { unmount } = await open(page)
    expect(headerButton('Review changes').disabled).toBe(true)
    unmount()
  }
})

test('047 FE11: Submit review waits for a radio; with Request changes it also waits for a summary', async () => {
  await open(reviewPage())
  const popover = reviewChanges()
  expect(chosen(popover)).toEqual([]) // Q5: neither starts chosen
  expect(submitReview(popover).disabled).toBe(true)
  fireEvent.click(radio(popover, 'Approve'))
  expect(submitReview(popover).disabled).toBe(false)
  fireEvent.click(radio(popover, 'Request changes'))
  expect(chosen(popover)).toEqual(['changes'])
  expect(submitReview(popover).disabled).toBe(true)
  fireEvent.change(summaryBox(popover), { target: { value: '  \n' } })
  expect(submitReview(popover).disabled).toBe(true)
  fireEvent.change(summaryBox(popover), { target: { value: 'Make it configurable' } })
  expect(submitReview(popover).disabled).toBe(false)
})

test('047 FE12, AC30: Approve sends the summary (blank as ""), reloads, hides the popover, and resets it', async () => {
  for (const [typed, body_md] of [['Ship it', 'Ship it'], ['', '']]) {
    const { fetch, unmount } = await open(reviewPage(), '/tasks/12/review', {
      [`POST ${APPROVE}`]: [200, { status: 'done', commit_hint: HINT }],
    })
    const popover = reviewChanges()
    if (typed) fireEvent.change(summaryBox(popover), { target: { value: typed } })
    fireEvent.click(radio(popover, 'Approve'))
    fireEvent.click(submitReview(popover))
    await waitFor(() => expect(loads(fetch)).toBe(2))
    expect(sent(fetch, APPROVE)).toEqual({ body_md })
    postedBeforeReload(fetch, APPROVE)
    expect(fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
    expect(popover.hidePopover).toHaveBeenCalledTimes(1)
    expect([summaryBox(popover).value, chosen(popover)]).toEqual(['', []])
    unmount()
  }
})

test('047 FE13, AC32: Request changes sends the summary, reloads, hides the popover, and empties it', async () => {
  const { fetch } = await open(reviewPage(), '/tasks/12/review', {
    [`POST ${CHANGES}`]: [202, { status: 'in_progress', stage: 'build', run_id: 41 }],
  })
  const popover = reviewChanges()
  fireEvent.change(summaryBox(popover), { target: { value: 'Make it configurable' } })
  fireEvent.click(radio(popover, 'Request changes'))
  fireEvent.click(submitReview(popover))
  await waitFor(() => expect(loads(fetch)).toBe(2))
  expect(sent(fetch, CHANGES)).toEqual({ body_md: 'Make it configurable' })
  postedBeforeReload(fetch, CHANGES)
  expect(popover.hidePopover).toHaveBeenCalledTimes(1)
  expect([summaryBox(popover).value, chosen(popover)]).toEqual(['', []])
})

test('047 FE14, AC33: a refused submit shows its detail in the popover, keeps it open with its input, and still reloads', async () => {
  const { fetch, responses } = await open(reviewPage(), '/tasks/12/review', {
    [`POST ${APPROVE}`]: [409, { detail: '#12 is not in review' }],
  })
  const popover = reviewChanges()
  fireEvent.change(summaryBox(popover), { target: { value: 'Ship it' } })
  fireEvent.click(radio(popover, 'Approve'))
  fireEvent.click(submitReview(popover))
  await waitFor(() => expect(loads(fetch)).toBe(2))
  expect(within(popover).getByRole('alert').textContent).toBe('#12 is not in review')
  expect(screen.getAllByRole('alert')).toHaveLength(1)
  expect(popover.hidePopover).not.toHaveBeenCalled()
  expect([summaryBox(popover).value, chosen(popover)]).toEqual(['Ship it', ['approve']])
  sent(fetch, APPROVE)

  // the next success clears it
  responses[`POST ${APPROVE}`] = [200, { status: 'done', commit_hint: HINT }]
  await waitFor(() => expect(submitReview(popover).disabled).toBe(false))
  fireEvent.click(submitReview(popover))
  await waitFor(() => expect(loads(fetch)).toBe(3))
  expect(screen.queryByRole('alert')).toBeNull()
  expect(popover.hidePopover).toHaveBeenCalledTimes(1)
})

test('AC31: a done task shows its commit commands under Commit it yourself; Approve leads there', async () => {
  const done = await open(reviewPage({ status: 'done', stage: null, commit_hint: HINT }))
  expect(screen.getByRole('heading', { name: 'Commit it yourself' })).toBeTruthy()
  expect(document.querySelector('main pre').textContent).toBe(HINT)
  done.unmount()

  const { fetch, responses } = await open(reviewPage(), '/tasks/12/review', {
    [`POST ${APPROVE}`]: [200, { status: 'done', commit_hint: HINT }],
  })
  expect(screen.queryByRole('heading', { name: 'Commit it yourself' })).toBeNull()
  expect(document.querySelector('main pre')).toBeNull()
  responses[`GET ${PAGE}`] = [200, reviewPage({ status: 'done', stage: null, commit_hint: HINT })]
  const popover = reviewChanges()
  fireEvent.click(radio(popover, 'Approve'))
  fireEvent.click(submitReview(popover))
  expect(await screen.findByRole('heading', { name: 'Commit it yourself' })).toBeTruthy()
  sent(fetch, APPROVE)
  expect(document.querySelector('main pre').textContent).toBe(HINT)
  expect(headerButton('Review changes').disabled).toBe(true)
})

const commit = () => section('Commit it yourself')
const NOTE = 'Selected. Press Ctrl+C (⌘C on a Mac) to copy.'

/** Opens a done task with `clipboard` as navigator.clipboard (undefined: none), and returns its Copy button. */
async function openDone(clipboard) {
  Object.defineProperty(navigator, 'clipboard', { value: clipboard, configurable: true })
  await open(reviewPage({ status: 'done', stage: null, commit_hint: HINT }))
  return within(commit()).getByRole('button', { name: 'Copy' })
}

test('047 FE15: Copy under Commit it yourself writes commit_hint to the clipboard once, then reads Copied', async () => {
  const writeText = vi.fn(async () => {})
  try {
    const copy = await openDone({ writeText })
    expect(within(commit()).getByRole('heading', { level: 2 }).compareDocumentPosition(copy) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    fireEvent.click(copy)
    await waitFor(() => expect(copy.textContent).toBe('Copied'))
    expect(writeText.mock.calls).toEqual([[HINT]])
    expect(commit().textContent).not.toContain(NOTE)
  } finally {
    delete navigator.clipboard
  }
})

test('047 FE16: without a clipboard, or when writeText rejects, Copy selects the commands and says how to copy them', async () => {
  for (const clipboard of [undefined, { writeText: vi.fn(async () => Promise.reject(new Error('denied'))) }]) {
    window.getSelection().removeAllRanges()
    try {
      const copy = await openDone(clipboard)
      fireEvent.click(copy)
      await waitFor(() => expect(within(commit()).getByRole('status').textContent).toBe(NOTE))
      expect(window.getSelection().toString()).toBe(HINT)
      expect(copy.textContent).toBe('Copy')
      if (clipboard) expect(clipboard.writeText.mock.calls).toEqual([[HINT]])
    } finally {
      delete navigator.clipboard
      cleanup()
    }
  }
})

// --- States ------------------------------------------------------------------------------

test("AC34: the API's 404s show the not-found state with their detail", async () => {
  mockFetch({ [`GET /api/pages/tasks/99/review`]: [404, { detail: 'Task #99 not found' }] })
  const missing = renderAt('/tasks/99/review')
  expect(await screen.findByRole('heading', { name: 'Task #99 not found' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Go to the dashboard' }).getAttribute('href')).toBe('/')
  missing.unmount()

  mockFetch({ [`GET ${PAGE}?round=9`]: [404, { detail: '#12 has no round 9' }] })
  renderAt('/tasks/12/review?round=9')
  expect(await screen.findByRole('heading', { name: '#12 has no round 9' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Go to the dashboard' }).getAttribute('href')).toBe('/')
})

test('AC35: a failed first load shows only its alert; a failed reload after an action keeps the page', async () => {
  mockFetch({ [`GET ${PAGE}`]: [500, { detail: 'boom' }] })
  const failed = renderAt('/tasks/12/review')
  expect((await screen.findByRole('alert')).textContent).toBe('boom')
  expect(screen.queryByRole('heading', { level: 1 })).toBeNull()
  failed.unmount()

  const { fetch, responses } = await open(reviewPage(), '/tasks/12/review', {
    [`POST ${APPROVE}`]: [200, { status: 'done', commit_hint: HINT }],
  })
  responses[`GET ${PAGE}`] = [500, { detail: 'database is locked' }]
  const popover = reviewChanges()
  fireEvent.click(radio(popover, 'Approve'))
  fireEvent.click(submitReview(popover))
  expect((await screen.findByRole('alert')).textContent).toBe('database is locked')
  expect(loads(fetch)).toBe(2)
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('#12 Rate-limit login')
  expect(section('Rounds')).toBeTruthy()
})
