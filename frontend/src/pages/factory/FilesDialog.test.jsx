import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { FactoryResult } from '../../components/FactoryResult.jsx'
import { expectSkeleton, mockFetch } from '../../test/render.jsx'
import { FilesDialog } from './FilesDialog.jsx'

const XSS = '<img src=x onerror=alert(1)>'
/** The API contract's shape: SKILL.md first, then the agents. */
const FILES = [
  { path: '.claude/skills/factory/SKILL.md', content: '---\nname: factory\n---\n# /factory $ARGUMENTS\n\n## The loop\n1. `fctl show <id>`\n' },
  { path: '.claude/agents/spec-writer.md', content: '---\nname: spec-writer\ndescription: Writes the spec.\n---\nInput: a task id.\n' },
  { path: '.claude/agents/builder.md', content: `---\nname: builder\n---\nRun \`make check\`. ${XSS}\n` },
]
const GET = 'GET /api/factories/7/files'
const POST = 'POST /api/factories/7/write'
const OUT = {
  written: [FILES[0].path],
  skipped: [FILES[1].path, FILES[2].path],
  commit_hint: 'git add .claude/skills/factory .claude/agents && git commit -m "Add factory"',
}

/** Renders the dialog for factory 7 with `responses` over FILES' GET; waits for the file list. */
async function open(responses = {}) {
  const fetch = mockFetch({ [GET]: [200, FILES], ...responses })
  render(<FilesDialog id={7} unsaved={false} onClose={vi.fn()} />)
  const el = screen.getByRole('dialog', { name: 'Files' })
  const dialog = within(el)
  return { fetch, el, dialog }
}

const paths = (dialog) => dialog.getAllByRole('button').filter((b) => b.textContent.startsWith('.claude/'))
const current = (dialog) => paths(dialog).filter((b) => b.getAttribute('aria-current') === 'true')
const preview = (dialog, path) => dialog.getByRole('region', { name: path })
const writes = (fetch) => fetch.mock.calls.filter(([url, init]) => url === '/api/factories/7/write' && init?.method === 'POST')

test('FE2: each path is a button in order; the first is current, its content highlighted as markdown', async () => {
  const { dialog } = await open()
  expectSkeleton(dialog.getByRole('status')) // Q11: Loading… while the GET is out
  await dialog.findByRole('button', { name: FILES[0].path })
  expect(paths(dialog).map((b) => b.textContent)).toEqual(FILES.map((f) => f.path))
  expect(current(dialog).map((b) => b.textContent)).toEqual([FILES[0].path])
  const code = preview(dialog, FILES[0].path).querySelector('pre > code')
  expect(code.textContent).toBe(FILES[0].content)
  expect(code.querySelector('[class^="hljs-"]')).toBeTruthy()
  expect([...code.querySelectorAll('.hljs-section')].map((el) => el.textContent)).toContain('# /factory $ARGUMENTS')
})

test('FE3: clicking another path selects it, shows its content, and takes aria-current off the first', async () => {
  const { dialog } = await open()
  fireEvent.click(await dialog.findByRole('button', { name: FILES[1].path }))
  expect(current(dialog).map((b) => b.textContent)).toEqual([FILES[1].path])
  expect(dialog.getByRole('button', { name: FILES[0].path }).hasAttribute('aria-current')).toBe(false)
  expect(preview(dialog, FILES[1].path).textContent).toBe(FILES[1].content)
  expect(dialog.queryByRole('region', { name: FILES[0].path })).toBeNull()
})

test('FE4: content holding an <img onerror> shows as text, and no img element is added', async () => {
  const { dialog } = await open()
  fireEvent.click(await dialog.findByRole('button', { name: FILES[2].path }))
  expect(preview(dialog, FILES[2].path).textContent).toContain(XSS)
  expect(document.querySelector('img')).toBeNull()
})

test('FE5: Download .zip links to the zip with a download attribute', async () => {
  const { dialog } = await open()
  const link = await dialog.findByRole('link', { name: 'Download .zip' })
  expect(link.getAttribute('href')).toBe('/api/factories/7/download')
  expect(link.hasAttribute('download')).toBe(true)
})

test('FE6: Write to repo POSTs overwrite false with X-Requested-By; ticked, overwrite true', async () => {
  const { fetch, dialog } = await open({ [POST]: [200, OUT] })
  fireEvent.click(await dialog.findByRole('button', { name: 'Write to repo' }))
  await waitFor(() => expect(writes(fetch)).toHaveLength(1))
  await dialog.findByText('Commit them so runs can see the factory:')
  fireEvent.click(dialog.getByRole('checkbox', { name: 'Overwrite existing files' }))
  await waitFor(() => expect(dialog.getByRole('button', { name: 'Write to repo' }).disabled).toBe(false))
  fireEvent.click(dialog.getByRole('button', { name: 'Write to repo' }))
  await waitFor(() => expect(writes(fetch)).toHaveLength(2))
  expect(writes(fetch).map(([, init]) => JSON.parse(init.body))).toEqual([{ overwrite: false }, { overwrite: true }])
  for (const [, init] of writes(fetch)) expect(init.headers['X-Requested-By']).toBe('fctl')
})

test('FE7: a 200 write shows the shared result view: Wrote, Skipped, and the commit hint', async () => {
  const { el, dialog } = await open({ [POST]: [200, OUT] })
  fireEvent.click(await dialog.findByRole('button', { name: 'Write to repo' }))
  await dialog.findByText('Wrote 1 file:')
  expect(dialog.getByText('Skipped 2 existing files (tick Overwrite to replace them):')).toBeTruthy()
  const result = el.querySelector('[aria-live="polite"]')
  expect([...result.querySelectorAll('li > code')].map((c) => c.textContent)).toEqual([...OUT.written, ...OUT.skipped])
  expect(result.querySelector('pre > code').textContent).toBe(OUT.commit_hint)
  // the one shared component: the same markup FactoryResult renders on its own
  const { container } = render(<FactoryResult out={OUT} />)
  expect(result.innerHTML).toBe(container.innerHTML)
})

test('FE8: a refused write shows its detail as a red alert inside the dialog, which stays open with its list', async () => {
  const detail = '.claude/skills is a symlink'
  const { el, dialog } = await open({ [POST]: [409, { detail }] })
  fireEvent.click(await dialog.findByRole('button', { name: 'Write to repo' }))
  const alert = await dialog.findByRole('alert')
  expect(alert.textContent).toBe(detail)
  expect(alert.className).toContain('text-danger')
  expect(el.open).toBe(true)
  expect(paths(dialog).map((b) => b.textContent)).toEqual(FILES.map((f) => f.path))
})

test('FE9: a refused GET shows its detail as a red alert, with no file list, Download link, or Write button', async () => {
  const detail = 'agent linter needs a description'
  const { dialog } = await open({ [GET]: [422, { detail }] })
  const alert = await dialog.findByRole('alert')
  expect(alert.textContent).toBe(detail)
  expect(alert.className).toContain('text-danger')
  expect(dialog.queryAllByRole('listitem')).toEqual([])
  expect(dialog.queryByRole('link', { name: 'Download .zip' })).toBeNull()
  expect(dialog.queryByRole('button', { name: 'Write to repo' })).toBeNull()
  expect(dialog.getAllByRole('button').map((b) => b.textContent)).toEqual(['Close'])
})
