import { render, screen } from '@testing-library/react'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createElement } from 'react'
import { expect, test } from 'vitest'
import * as actionButton from './ActionButton.jsx'
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
