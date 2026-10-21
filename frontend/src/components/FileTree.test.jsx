import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test } from 'vitest'
import { FileTree } from './FileTree.jsx'

afterEach(cleanup)

/** The code page's current tree, as a flat list in its order. */
const FILES = [{ path: 'README.md' }, { path: 'src/a.py' }, { path: 'src/lib/b.py' }, { path: 'docs/guide.md' }]
const link = (file, name) => <a href={`#${file.path}`}>{name}</a>
const tree = (props = {}) => <FileTree files={FILES} renderFile={link} {...props} />

/** The tree as nested arrays: a file's text, or [directory, its entries]. */
const shape = (ul) =>
  [...ul.children].map((li) => {
    const button = li.querySelector(':scope > button')
    return button ? [button.textContent, shape(li.querySelector(':scope > ul'))] : li.textContent
  })
const root = () => document.querySelector('body > div > ul')
const dir = (name) => screen.getByRole('button', { name })
const expanded = (name) => dir(name).getAttribute('aria-expanded')
const found = (name) => screen.queryByRole('link', { name }) !== null

test('FE1: nested lists; a directory sits where its first file is', () => {
  const { unmount } = render(tree({ allOpen: true }))
  expect(shape(root())).toEqual(['README.md', ['src/', ['a.py', ['lib/', ['b.py']]]], ['docs/', ['guide.md']]])
  unmount()
  render(<FileTree files={[{ path: 'app/limits.py' }, { path: 'README.md' }, { path: 'app/auth.py' }]} renderFile={link} allOpen />)
  expect(shape(root())).toEqual([['app/', ['limits.py', 'auth.py']], 'README.md'])
})

test('FE2: each file is the page\'s element, given the file object as passed, extra fields included', () => {
  const files = FILES.map((file, i) => ({ ...file, additions: i * 10 }))
  render(
    <FileTree
      files={files}
      allOpen
      renderFile={(file, name) => <a href={'#' + file.path}>{`${name} +${file.additions}`}</a>}
    />,
  )
  expect(screen.getAllByRole('link').map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
    ['README.md +0', '#README.md'],
    ['a.py +10', '#src/a.py'],
    ['b.py +20', '#src/lib/b.py'],
    ['guide.md +30', '#docs/guide.md'],
  ])
})

test('FE3: a directory is one button with aria-expanded and aria-hidden SVGs; a file row an aria-hidden icon; no tree roles or Preline hooks', () => {
  render(tree({ current: 'src/a.py' }))
  expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual(['src/', 'lib/', 'docs/'])
  for (const button of document.querySelectorAll('button')) {
    expect(button.getAttribute('type')).toBe('button')
    expect(button.hasAttribute('aria-expanded')).toBe(true)
    const list = document.getElementById(button.getAttribute('aria-controls'))
    expect(list).toBe(button.nextElementSibling)
    const svgs = [...button.querySelectorAll('svg')]
    expect(svgs).toHaveLength(2) // the +/− glyph and the folder
    expect(svgs.map((svg) => svg.getAttribute('aria-hidden'))).toEqual(['true', 'true'])
  }
  expect(dir('src/').textContent).toBe('src/')
  for (const a of document.querySelectorAll('a')) {
    const icon = a.previousElementSibling
    expect(icon.tagName.toLowerCase()).toBe('svg')
    expect(icon.getAttribute('aria-hidden')).toBe('true')
  }
  const all = [...root().querySelectorAll('*'), root()]
  expect(all.filter((el) => ['tree', 'treeitem', 'group'].includes(el.getAttribute('role')))).toEqual([])
  expect(all.filter((el) => Number(el.getAttribute('tabindex')) < 0)).toEqual([])
  expect(all.filter((el) => [...el.classList].some((c) => c.startsWith('hs-')))).toEqual([])
  expect(all.filter((el) => el.getAttributeNames().some((a) => a.startsWith('data-hs')))).toEqual([])
})

test('FE4: the current path\'s directories are open; a closed directory\'s links are out of reach', () => {
  render(tree({ current: 'src/lib/b.py' }))
  expect([expanded('src/'), expanded('lib/'), expanded('docs/')]).toEqual(['true', 'true', 'false'])
  expect(found('b.py')).toBe(true)
  expect(found('guide.md')).toBe(false)
  expect(document.querySelector('a[href="#docs/guide.md"]').closest('[hidden]')).not.toBeNull()
})

test('FE5: an empty current path opens nothing; only README.md\'s link is found', () => {
  render(tree({ current: '' }))
  expect([...document.querySelectorAll('button')].map((b) => b.getAttribute('aria-expanded'))).toEqual(['false', 'false', 'false'])
  expect(screen.getAllByRole('link').map((a) => a.textContent)).toEqual(['README.md'])
})

test('FE6: all-open mode opens every directory and finds every link', () => {
  render(tree({ allOpen: true }))
  expect(screen.getAllByRole('button').map((b) => b.getAttribute('aria-expanded'))).toEqual(['true', 'true', 'true'])
  expect(screen.getAllByRole('link').map((a) => a.textContent)).toEqual(['README.md', 'a.py', 'b.py', 'guide.md'])
})

test('FE7: clicking docs/ opens it, clicking again closes it; src/ and lib/ never change', () => {
  render(tree({ current: 'src/lib/b.py' }))
  const others = () => [expanded('src/'), expanded('lib/')]
  fireEvent.click(dir('docs/'))
  expect(expanded('docs/')).toBe('true')
  expect(found('guide.md')).toBe(true)
  expect(others()).toEqual(['true', 'true'])
  fireEvent.click(dir('docs/'))
  expect(expanded('docs/')).toBe('false')
  expect(found('guide.md')).toBe(false)
  expect(others()).toEqual(['true', 'true'])
})

test('FE8: a new path opens its directories and keeps the rest; the same path again changes nothing', () => {
  const { rerender } = render(tree({ current: 'src/a.py' }))
  expect(screen.queryByRole('button', { name: 'lib/' }).getAttribute('aria-expanded')).toBe('false')
  fireEvent.click(dir('docs/'))
  rerender(tree({ current: 'src/lib/b.py' }))
  expect([expanded('src/'), expanded('lib/'), expanded('docs/')]).toEqual(['true', 'true', 'true'])
  fireEvent.click(dir('lib/'))
  expect(expanded('lib/')).toBe('false')
  rerender(tree({ current: 'src/lib/b.py' }))
  expect(expanded('lib/')).toBe('false')
  expect([expanded('src/'), expanded('docs/')]).toEqual(['true', 'true'])
})
