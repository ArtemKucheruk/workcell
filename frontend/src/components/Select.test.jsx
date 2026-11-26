import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { useState } from 'react'
import { afterEach, expect, test, vi } from 'vitest'
import { Select } from './Select.jsx'
import { field } from './styles.js'

const FRUIT = [
  { value: 'apple', label: 'Apple' },
  { value: 'banana', label: 'Banana' },
  { value: 'blueberry', label: 'Blueberry' },
  { value: 'cherry', label: 'Cherry' },
]

const src = path.join(path.dirname(fileURLToPath(import.meta.url)), '..')

afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

// jsdom has no Popover API, so it counts a [popover]'s content as hidden
const option = (query) => screen.getByRole('option', { ...query, hidden: true })
const allOptions = () => screen.queryAllByRole('option', { hidden: true })
const box = () => screen.getByRole('combobox')
const expanded = () => box().getAttribute('aria-expanded')
const active = () => document.getElementById(box().getAttribute('aria-activedescendant'))?.textContent
const key = (k, init = {}) => fireEvent.keyDown(box(), { key: k, ...init })
const open = () => fireEvent.click(box())

function Controlled({ start = 'banana', onChange = () => {} }) {
  const [value, setValue] = useState(start)
  return (
    <>
      <Select aria-label="Fruit" options={FRUIT} value={value} onChange={(v) => (onChange(v), setValue(v))} />
      <button type="button" onClick={() => setValue('cherry')}>
        Parent
      </button>
    </>
  )
}

test('107 AC1: a combobox with a listbox popup, collapsed, showing the selected label, on the field class', () => {
  render(<Select aria-label="Fruit" options={FRUIT} value="banana" className="w-full" />)
  expect(screen.getAllByRole('combobox')).toHaveLength(1)
  expect([box().getAttribute('aria-haspopup'), expanded(), box().textContent]).toEqual(['listbox', 'false', 'Banana'])
  for (const c of `${field} w-full`.split(' ')) expect(box().classList).toContain(c)
})

test('107 AC2: a click opens the listbox it controls, one option each, the current one selected', () => {
  render(<Select aria-label="Fruit" options={FRUIT} value="banana" />)
  open()
  expect(expanded()).toBe('true')
  const list = screen.getByRole('listbox', { hidden: true })
  expect(list.id).toBe(box().getAttribute('aria-controls'))
  const options = allOptions()
  expect(options.map((o) => o.textContent)).toEqual(['Apple', 'Banana', 'Blueberry', 'Cherry'])
  expect(options.map((o) => o.getAttribute('aria-selected'))).toEqual(['false', 'true', 'false', 'false'])
})

test('107 AC3: a second click, or a press outside, closes it', () => {
  render(<Select aria-label="Fruit" options={FRUIT} value="banana" />)
  open()
  open()
  expect(expanded()).toBe('false')
  open()
  fireEvent.pointerDown(option({ name:'Cherry' })) // inside: stays open
  expect(expanded()).toBe('true')
  fireEvent.pointerDown(document.body)
  expect(expanded()).toBe('false')
  expect(allOptions()).toEqual([])
})

test('107 AC4: Enter, Space, or ArrowDown opens it on the selected option', () => {
  render(<Select aria-label="Fruit" options={FRUIT} value="blueberry" />)
  for (const k of ['Enter', ' ', 'ArrowDown']) {
    box().focus()
    key(k)
    expect([expanded(), active()]).toEqual(['true', 'Blueberry'])
    key('Escape')
  }
})

test('107 AC5: arrows move one option without wrapping; Home and End jump to the ends', () => {
  render(<Select aria-label="Fruit" options={FRUIT} value="banana" />)
  key('ArrowDown')
  key('ArrowDown')
  expect(active()).toBe('Blueberry')
  key('ArrowDown')
  key('ArrowDown')
  expect(active()).toBe('Cherry')
  key('Home')
  expect(active()).toBe('Apple')
  key('ArrowUp')
  expect(active()).toBe('Apple')
  key('End')
  expect(active()).toBe('Cherry')
  expect(option({ name:'Cherry' }).hasAttribute('data-active')).toBe(true)
})

test('107 AC6: type-ahead moves the active option when open and the selection when closed; it resets after 500 ms', async () => {
  vi.useFakeTimers()
  const onChange = vi.fn()
  render(<Controlled start="apple" onChange={onChange} />)
  key('c') // closed: selects
  expect([box().textContent, onChange.mock.calls]).toEqual(['Cherry', [['cherry']]])
  key('ArrowDown')
  key('b')
  key('l')
  expect(active()).toBe('Blueberry') // "bl", not the next b
  await act(() => vi.advanceTimersByTimeAsync(600))
  key('a')
  expect(active()).toBe('Apple')
  await act(() => vi.advanceTimersByTimeAsync(600))
  key('b')
  expect(active()).toBe('Banana')
  await act(() => vi.advanceTimersByTimeAsync(600))
  key('b')
  expect(active()).toBe('Blueberry') // one letter again cycles to the next b
  expect(onChange).toHaveBeenCalledTimes(1)
})

test('107 AC7: Enter or a click picks the option, closes, keeps focus, and calls onChange once; re-picking does not', () => {
  const onChange = vi.fn()
  render(<Controlled onChange={onChange} />)
  box().focus()
  key('ArrowDown')
  key('ArrowDown')
  key('Enter')
  expect([expanded(), box().textContent, document.activeElement]).toEqual(['false', 'Blueberry', box()])
  expect(onChange.mock.calls).toEqual([['blueberry']])
  open()
  fireEvent.click(option({ name:'Apple' }))
  expect([expanded(), box().textContent, document.activeElement]).toEqual(['false', 'Apple', box()])
  open()
  fireEvent.click(option({ name:'Apple' }))
  key('Enter')
  key('Enter')
  expect(onChange.mock.calls).toEqual([['blueberry'], ['apple']])
})

test('107 AC8: Esc closes without a change, focus on the combobox, and the key goes no further', () => {
  const onChange = vi.fn()
  const outer = vi.fn()
  render(
    <div onKeyDown={outer}>
      <Select aria-label="Fruit" options={FRUIT} value="banana" onChange={onChange} />
    </div>,
  )
  box().focus()
  key('ArrowDown')
  key('ArrowDown')
  key('Escape')
  expect([expanded(), box().textContent, document.activeElement]).toEqual(['false', 'Banana', box()])
  expect(onChange).not.toHaveBeenCalled()
  expect(outer.mock.calls.filter(([e]) => e.key === 'Escape')).toEqual([])
})

test('107 AC9: Tab closes it without stopping the focus moving on', () => {
  render(<Select aria-label="Fruit" options={FRUIT} value="banana" />)
  key('ArrowDown')
  const tab = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true })
  act(() => box().dispatchEvent(tab))
  expect([expanded(), tab.defaultPrevented]).toEqual(['false', false])
})

test('107 AC10: controlled, the label follows value, and a pick shows only once the parent takes it', () => {
  const onChange = vi.fn()
  const { rerender } = render(<Select aria-label="Fruit" options={FRUIT} value="banana" onChange={onChange} />)
  rerender(<Select aria-label="Fruit" options={FRUIT} value="cherry" onChange={onChange} />)
  expect(box().textContent).toBe('Cherry')
  open()
  fireEvent.click(option({ name:'Apple' }))
  expect([onChange.mock.calls, box().textContent]).toEqual([[['apple']], 'Cherry'])
  render(<Controlled />)
  fireEvent.click(screen.getByRole('button', { name: 'Parent' }))
  expect(screen.getAllByRole('combobox')[1].textContent).toBe('Cherry')
})

test('107 AC11: uncontrolled in a form, a hidden input submits the default, then the pick', () => {
  render(
    <form>
      <Select aria-label="Fruit" name="fruit" options={FRUIT} defaultValue="blueberry" />
    </form>,
  )
  const form = document.querySelector('form')
  expect(form.querySelector('input[type="hidden"][name="fruit"]')).toBeTruthy()
  expect(new FormData(form).get('fruit')).toBe('blueberry')
  open()
  fireEvent.click(option({ name:'Apple' }))
  expect([new FormData(form).get('fruit'), box().textContent]).toEqual(['apple', 'Apple'])
})

test('107 AC12: disabled can not open, looks disabled, and submits nothing', () => {
  render(
    <form>
      <Select aria-label="Fruit" name="fruit" options={FRUIT} defaultValue="banana" disabled />
    </form>,
  )
  expect(box().disabled).toBe(true)
  expect(box().className).toContain('disabled:opacity-50')
  open()
  key('ArrowDown')
  expect(expanded()).toBe('false')
  expect(new FormData(document.querySelector('form')).has('fruit')).toBe(false)
})

test('107 AC13: named by its label, aria-labelledby, or aria-label, never by its option', () => {
  render(
    <>
      <label htmlFor="pick">Pick</label>
      <Select id="pick" options={FRUIT} value="apple" />
      <span id="named">Round</span>
      <Select aria-labelledby="named" options={FRUIT} value="apple" />
      <Select aria-label="Fruit" options={FRUIT} value="apple" />
    </>,
  )
  expect(screen.getByRole('combobox', { name: 'Pick' }).id).toBe('pick')
  expect(screen.getByRole('combobox', { name: 'Round' })).toBeTruthy()
  expect(screen.getByRole('combobox', { name: 'Fruit' })).toBeTruthy()
  expect(screen.queryByRole('combobox', { name: /Apple/ })).toBeNull()
})

test('107 AC14: an unknown or missing value shows, and submits, the first option', () => {
  render(
    <form>
      <Select aria-label="A" options={FRUIT} value="kiwi" />
      <Select aria-label="B" name="fruit" options={FRUIT} />
    </form>,
  )
  const [a, b] = screen.getAllByRole('combobox')
  expect([a.textContent, b.textContent]).toEqual(['Apple', 'Apple'])
  expect(new FormData(document.querySelector('form')).get('fruit')).toBe('apple')
  fireEvent.click(a)
  expect(option({ name:'Apple' }).getAttribute('aria-selected')).toBe('true')
})

test('107 AC15: the listbox is an auto popover anchored to the combobox, as Menu is, at least as wide', () => {
  render(<Select aria-label="Fruit" options={FRUIT} value="apple" />)
  const list = screen.getByRole('listbox', { hidden: true })
  const anchor = box().style.anchorName
  expect(anchor).toMatch(/^--/)
  expect([list.getAttribute('popover'), list.style.positionAnchor]).toEqual(['auto', anchor])
  expect(box().getAttribute('popovertarget')).toBe(list.id)
  expect(list.className).toContain('min-w-[anchor-size(width)]')
  expect(list.className).toContain('[position-area:bottom_span-right]')
})

test('107 AC15, Q6: where the popover API exists, open state drives it and its toggle event syncs back', () => {
  render(<Select aria-label="Fruit" options={FRUIT} value="apple" />)
  const list = screen.getByRole('listbox', { hidden: true })
  let shown = false
  list.matches = (q) => (q === ':popover-open' ? shown : false)
  list.showPopover = vi.fn(() => (shown = true))
  list.hidePopover = vi.fn(() => (shown = false))
  key('ArrowDown')
  expect(list.showPopover).toHaveBeenCalledOnce()
  key('Escape')
  expect(list.hidePopover).toHaveBeenCalledOnce()
  open() // the button's popovertarget toggles it natively, not React
  expect(expanded()).toBe('false')
  act(() => list.dispatchEvent(Object.assign(new Event('toggle'), { newState: 'open' })))
  expect(expanded()).toBe('true')
  act(() => list.dispatchEvent(Object.assign(new Event('toggle'), { newState: 'closed' }))) // light dismiss
  expect(expanded()).toBe('false')
})

test('107 AC16: its only motion is motion-safe', () => {
  render(<Select aria-label="Fruit" options={FRUIT} value="apple" />)
  const classes = [box(), screen.getByRole('listbox', { hidden: true })].flatMap((el) => el.className.split(' '))
  const moving = classes.filter((c) => /transition|animate|duration/.test(c))
  expect(moving.length).toBeGreaterThan(0)
  expect(moving.every((c) => c.startsWith('motion-safe:'))).toBe(true)
})

test('107 AC26: no native <select> is left in frontend/src', () => {
  const files = readdirSync(src, { recursive: true }).filter((f) => /\.jsx?$/.test(f) && !/\.test\./.test(f))
  expect(files.filter((f) => /<select[\s>]/.test(readFileSync(path.join(src, f), 'utf8')))).toEqual([])
})

test('107 AC27: docs/ui.md and the code comments no longer describe a native select', () => {
  const ui = readFileSync(path.join(src, '..', '..', 'docs', 'ui.md'), 'utf8')
  expect(ui).not.toMatch(/native `?<select>|its <select>|workspace `<select>`/)
  expect(ui.match(/the shared Select/g).length).toBeGreaterThanOrEqual(5)
  for (const f of ['pages/task/TaskPage.jsx', 'app/Sidebar.jsx']) {
    expect(readFileSync(path.join(src, f), 'utf8')).not.toMatch(/native <select>|workspace `<select>`/)
  }
})

test('107 AC17: the selected option has a check, the active one a raised highlight, on the tokens only', () => {
  render(<Select aria-label="Fruit" options={FRUIT} value="banana" />)
  key('ArrowDown')
  key('ArrowDown')
  const [banana, blueberry] = [option({ name:'Banana' }), option({ name:'Blueberry' })]
  expect(banana.querySelector('svg').getAttribute('class')).not.toContain('invisible')
  expect(blueberry.querySelector('svg').getAttribute('class')).toContain('invisible')
  expect(blueberry.hasAttribute('data-active')).toBe(true)
  expect(blueberry.className).toContain('data-active:bg-raised')
  const source = readFileSync(path.join(src, 'components', 'Select.jsx'), 'utf8')
  expect(source).not.toMatch(/gray-|dark:/)
})
