import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, test } from 'vitest'
import { cls } from '../test/render.jsx'
import { ActionButton } from './ActionButton.jsx'
import { button as buttonStyle, smallButton } from './styles.js'

afterEach(cleanup)

/** Renders Go with an action that stays pending until the returned `settle` is called. */
function pending(props = {}) {
  let settle
  const action = () => new Promise((resolve) => (settle = resolve))
  render(<ActionButton action={action} {...props}>Go</ActionButton>)
  return { button: screen.getByRole('button', { name: 'Go' }), settle: () => act(async () => settle()) }
}

const spinners = (button) => button.querySelectorAll('[aria-hidden="true"]')
const classes = (root) => [root, ...root.querySelectorAll('*')].flatMap((el) => el.className.split(/\s+/)).filter(Boolean)

test('046 FE18: while its action is pending the button is disabled, aria-busy, with one motion-safe spinner, its name and className kept', async () => {
  for (const [props, className] of [[{}, buttonStyle], [{ className: smallButton }, smallButton]]) {
    const { button, settle } = pending(props)
    fireEvent.click(button)
    expect(button.disabled).toBe(true)
    expect(button.getAttribute('aria-busy')).toBe('true')
    expect(spinners(button)).toHaveLength(1)
    expect(spinners(button)[0].className).toMatch(cls('motion-safe:animate-spin'))
    expect(classes(button).filter((c) => /(^|:)animate-/.test(c) && !c.startsWith('motion-safe:'))).toEqual([])
    expect(screen.getByRole('button', { name: 'Go' })).toBe(button)
    expect(button.className).toBe(className) // 040 FE6
    await settle()
    cleanup()
  }
})

test('046 FE19: once the action settles the spinner and aria-busy are gone and it is enabled; disabled alone shows no spinner', async () => {
  const { button, settle } = pending()
  fireEvent.click(button)
  await settle()
  expect(button.disabled).toBe(false)
  expect(button.hasAttribute('aria-busy')).toBe(false)
  expect(spinners(button)).toHaveLength(0)
  expect(classes(button).filter((c) => /(^|:)animate-/.test(c))).toEqual([])
  cleanup()

  const off = pending({ disabled: true }).button
  expect(off.disabled).toBe(true)
  expect(off.hasAttribute('aria-busy')).toBe(false)
  expect(spinners(off)).toHaveLength(0)
})
