import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { expect, test } from 'vitest'
import { mockFetch, renderAt } from '../test/render.jsx'
import { ProjectHeader } from './ProjectHeader.jsx'

const PROJECT = { id: 3, name: 'api', workspace_id: 2, workspace: 'personal' }

/** The header alone, in a router for its links. */
function header(props, children) {
  const { container } = render(
    <MemoryRouter>
      <ProjectHeader {...props}>{children}</ProjectHeader>
    </MemoryRouter>,
  )
  return container.querySelector('header')
}

test('FE1: ready shows the h1 api · personal, personal linking to its workspace, and Factory: ready ✓ as text', () => {
  const el = header({ project: PROJECT, factory: 'ready' })
  const h1 = within(el).getByRole('heading', { level: 1 })
  expect(h1.textContent).toBe('api · personal')
  expect(within(h1).getByRole('link', { name: 'personal' }).getAttribute('href')).toBe('/workspaces/2')
  const state = within(el).getByText('Factory: ready ✓')
  expect(state.closest('a')).toBeNull()
  expect(within(el).getAllByRole('link')).toHaveLength(1)
})

test('FE2: uncommitted and none link Factory: <state> to the project settings', () => {
  for (const factory of ['uncommitted', 'none']) {
    const el = header({ project: PROJECT, factory })
    const link = within(el).getByRole('link', { name: `Factory: ${factory}` })
    expect(link.getAttribute('href')).toBe('/projects/3/settings')
  }
})

test('059 FE1: legacy links Factory: legacy to the project settings, in warning', () => {
  const el = header({ project: PROJECT, factory: 'legacy' })
  const link = within(el).getByRole('link', { name: 'Factory: legacy' })
  expect(link.getAttribute('href')).toBe('/projects/3/settings')
  expect(link.className).toMatch(/(^|\s)text-warning(\s|$)/)
})

test("FE3: the page's own controls render after the factory state, inside the header", () => {
  const el = header({ project: PROJECT, factory: 'ready' }, <button type="button">Run next ▶</button>)
  const state = within(el).getByText('Factory: ready ✓')
  const control = within(el).getByRole('button', { name: 'Run next ▶' })
  expect(control.closest('header')).toBe(el)
  expect(state.compareDocumentPosition(control) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

test('FE4: a project with only id and name and no factory: the h1 is the name, with no workspace link or Factory', () => {
  const el = header({ project: { id: 3, name: 'api' } })
  expect(within(el).getByRole('heading', { level: 1 }).textContent).toBe('api')
  expect(within(el).queryAllByRole('link')).toEqual([])
  expect(el.textContent).not.toContain('Factory:')
})

test('FE5: each project page has one h1, api · personal, and Factory: ready ✓ in main', async () => {
  const project = { ...PROJECT, path: '/Users/me/api', default_branch: 'main', remote_url: null, test_cmd: 'pytest -q' }
  const board = {
    project, factory: 'ready', hint: null, can_run: true, workspaces: [{ id: 2, name: 'personal', projects: 1 }],
    columns: { backlog: [], in_progress: [], review: [], done: [] },
  }
  const code = {
    project: { id: 3, name: 'api', path: '/Users/me/api' }, error: null, branch: 'main', tree: { 'a.py': { path: 'a.py' } },
    shown: '', view: { note: 'No README.md in this project.' }, lang: null, readme_html: null,
  }
  mockFetch({
    'GET /api/pages/projects/3': [200, board],
    'GET /api/pages/projects/3/code': [200, code],
    'GET /api/projects/3/context': [200, { context_md: 'x', context_html: '<p>x</p>\n', bytes: 1, max_bytes: 16384 }],
    'GET /api/projects/3/context/items': [200, []], // 057 FE17: the Context page's cards
  })
  for (const path of ['/projects/3', '/projects/3/code', '/projects/3/reviews', '/projects/3/context', '/projects/3/settings']) {
    const { unmount } = renderAt(path)
    const main = within(screen.getByRole('main'))
    await waitFor(() => expect(main.getByText('Factory: ready ✓')).toBeTruthy())
    expect(main.getAllByRole('heading', { level: 1 }).map((h) => h.textContent)).toEqual(['api · personal'])
    unmount()
  }
})
