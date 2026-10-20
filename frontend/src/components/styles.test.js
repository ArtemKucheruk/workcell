import { render, screen } from '@testing-library/react'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { expect, test } from 'vitest'
import * as actionButton from './ActionButton.jsx'
import { OfflineBanner } from './ErrorMessage.jsx'
import * as styles from './styles.js'

const src = path.join(path.dirname(fileURLToPath(import.meta.url)), '..')
const sources = fs
  .readdirSync(src, { recursive: true })
  .filter((f) => /\.(jsx?|css)$/.test(f) && !/\.test\./.test(f) && !f.startsWith(`test${path.sep}`))

test('040 FE6: muted, field, button, and smallButton are declared only in styles.js', () => {
  const declared = sources.flatMap((f) =>
    [...fs.readFileSync(path.join(src, f), 'utf8').matchAll(/\b(?:const|let|var)\s+(muted|field|button|smallButton)\b/g)].map(
      (m) => `${f.split(path.sep).join('/')} ${m[1]}`,
    ),
  )
  expect(declared.sort()).toEqual(['button', 'field', 'muted', 'smallButton'].map((n) => `components/styles.js ${n}`))
  for (const name of ['muted', 'field', 'button', 'smallButton']) expect(styles[name]).toMatch(/\S/)
  expect(actionButton.button).toBeUndefined()
  render(createElement(actionButton.ActionButton, { action: () => {} }, 'Go'))
  expect(screen.getByRole('button', { name: 'Go' }).className).toBe(styles.button)
})

test('046 FE21: the chevron turns, and the dragged card, popovers, and the offline banner fade, each under motion-safe', () => {
  const tokens = (className) => className.split(/\s+/)
  const fadesIn = (className) => [
    tokens(className).includes('motion-safe:transition-opacity'),
    tokens(className).filter((t) => /^starting:(?:[\w-]+:)*opacity-0$/.test(t)).length,
  ]
  expect(fadesIn(styles.popover)).toEqual([true, 1])
  render(createElement(OfflineBanner))
  expect(fadesIn(screen.getByRole('status').className)).toEqual([true, 1])
  const source = (rel) => fs.readFileSync(path.join(src, rel), 'utf8')
  // the project disclosure's ▸, rotated while open
  const chevron = source('app/Sidebar.jsx').match(/className=\{`([^`]*)`\}>\s*▸/)[1]
  expect(tokens(chevron)).toContain('motion-safe:transition-transform')
  expect(tokens(chevron)).not.toContain('transition-transform')
  // the board card's li, which data-dragging dims
  const card = source('pages/board/BoardPage.jsx').match(/const cardLook = \[([\s\S]*?)\]\.join/)[1].replace(/['\n,]/g, ' ')
  expect(tokens(card)).toContain('motion-safe:transition-opacity')
  expect(tokens(card)).toContain('data-dragging:opacity-50')
})
