import { render, screen, within } from '@testing-library/react'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { expect, test } from 'vitest'
import { Breadcrumbs } from './Breadcrumbs.jsx'

test('047 FE1: a Breadcrumb nav holding an <ol>; every item but the last links to its `to`, the last is current text; › hidden', () => {
  const items = [{ label: 'personal', to: '/workspaces/2' }, { label: 'api', to: '/projects/3' }, { label: '#12', to: '/tasks/12' }, { label: 'Review' }]
  const router = createMemoryRouter([{ path: '*', element: <Breadcrumbs items={items} /> }])
  render(<RouterProvider router={router} />)
  const nav = screen.getByRole('navigation', { name: 'Breadcrumb' })
  expect(nav.textContent).toBe('personal › api › #12 › Review')
  const ol = nav.querySelector(':scope > ol')
  const lis = [...ol.children]
  expect(lis.map((li) => li.tagName)).toEqual(['LI', 'LI', 'LI', 'LI'])
  expect(within(nav).getAllByRole('link').map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
    ['personal', '/workspaces/2'], ['api', '/projects/3'], ['#12', '/tasks/12'],
  ])
  const last = within(lis[3]).getByText('Review')
  expect(last.tagName).not.toBe('A')
  expect(last.closest('a')).toBeNull()
  expect(last.getAttribute('aria-current')).toBe('page')
  expect(nav.querySelectorAll('[aria-current]')).toHaveLength(1)
  const separators = [...nav.querySelectorAll('[aria-hidden="true"]')]
  expect(separators.map((el) => el.textContent.trim())).toEqual(['›', '›', '›'])
  // every › is hidden, so the list items read as their labels alone
  const shown = (li) => [...li.childNodes].filter((n) => n.getAttribute?.('aria-hidden') !== 'true').map((n) => n.textContent).join('')
  expect(lis.map(shown)).toEqual(['personal', 'api', '#12', 'Review'])
})

test('047 FE17, 051 FE9: only the task, review, code, transcript, and factory designer pages render a Breadcrumb nav', () => {
  const src = path.join(path.dirname(fileURLToPath(import.meta.url)), '..')
  const users = fs
    .readdirSync(src, { recursive: true })
    .filter((f) => /\.jsx?$/.test(f) && !/\.test\./.test(f))
    .filter((f) => /Breadcrumbs|aria-label="Breadcrumb"/.test(fs.readFileSync(path.join(src, f), 'utf8')))
    .map((f) => f.split(path.sep).join('/'))
  expect(users.sort()).toEqual([
    'components/Breadcrumbs.jsx',
    'pages/code/CodePage.jsx',
    'pages/factory/FactoryPage.jsx',
    'pages/review/ReviewPage.jsx',
    'pages/task/TaskPage.jsx',
    'pages/transcript/TranscriptPage.jsx',
  ])
})
