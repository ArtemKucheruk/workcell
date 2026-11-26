import { useEffect, useId, useRef, useState } from 'react'
import { field, popover } from './styles.js'

// 107 AC17: the active option is raised; the selected one also gets a check, so color isn't its only signal
const option =
  'flex cursor-pointer items-start gap-2 rounded px-2 py-1 text-left wrap-anywhere data-active:bg-raised aria-selected:font-semibold'

const chevron = (
  <svg aria-hidden="true" viewBox="0 0 24 24" className="size-4 shrink-0 text-muted" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="m6 9 6 6 6-6" />
  </svg>
)

/**
 * 107: the one dropdown, a button showing the current option and a listbox popup on the theme's tokens, in place of the
 * OS-rendered native select; the WAI-ARIA select-only combobox, so focus stays on the button and `aria-activedescendant`
 * names the active option. `options` is `[{ value, label }]` (Q4) and `onChange(value)` gets the value as a string (Q3).
 * Controlled with `value`, else uncontrolled from `defaultValue`, with `name` submitted through a hidden input (AC11).
 * Name it with `id` plus a `<label htmlFor>`, or `aria-labelledby`/`aria-label`, never a wrapping label, which would add
 * the option's text to the name (Q2).
 *
 * 107 Q1: hand-written, not Preline's HSSelect, which builds and owns its own DOM after autoInit and fights a
 * React-controlled value and re-renders.
 * Q6, AC15: the popup is a native popover anchored as `Menu.jsx`'s are, so it sits in the top layer where no
 * overflow-hidden ancestor clips it. The open state lives in React; the popover API is called only where it exists
 * (not in jsdom), and its `toggle` event (the button's popovertarget, light dismiss) syncs the state back.
 */
export function Select({
  options,
  value,
  defaultValue,
  onChange,
  name,
  disabled,
  id,
  className = '',
  'aria-label': ariaLabel,
  'aria-labelledby': labelledBy,
}) {
  const auto = useId().replace(/[^\w-]/g, '')
  const listId = `${auto}-listbox`
  const optionId = (i) => `${auto}-option-${i}`
  const trigger = useRef(null)
  const list = useRef(null)
  const typed = useRef({ text: '', at: 0 })
  const controlled = value !== undefined
  const [inner, setInner] = useState(defaultValue === undefined ? undefined : String(defaultValue))
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(null) // null: the selected option
  const current = controlled ? String(value) : inner
  const found = options.findIndex((o) => String(o.value) === current)
  const index = found === -1 ? 0 : found // AC14: as a native select, an unknown value shows the first option
  const shown = options.length ? String(options[index].value) : ''
  const at = active ?? index
  const last = options.length - 1

  function hide(focus) {
    setOpen(false)
    setActive(null)
    if (focus) trigger.current?.focus()
  }

  function commit(i) {
    const picked = String(options[i].value)
    if (picked === shown) return // AC7: re-picking the selected option is no change
    if (!controlled) setInner(picked)
    onChange?.(picked)
  }

  // AC6: the next option starting with what was typed in the last 500 ms; one letter, or one letter repeated, cycles
  function typeAhead(key) {
    const now = Date.now()
    const t = typed.current
    t.text = now - t.at > 500 ? key : t.text + key
    t.at = now
    const text = t.text.toLowerCase()
    const one = [...text].every((c) => c === text[0])
    const prefix = one ? text[0] : text
    const start = one ? at + 1 : at
    for (let k = 0; k < options.length; k++) {
      const i = (start + k) % options.length
      if (String(options[i].label).toLowerCase().startsWith(prefix)) return i
    }
    return -1
  }

  function keyDown(event) {
    const { key } = event
    if (disabled || event.altKey || event.ctrlKey || event.metaKey || !options.length) return
    if (key.length === 1 && (key !== ' ' || typed.current.text && Date.now() - typed.current.at <= 500)) {
      event.preventDefault()
      const i = typeAhead(key)
      if (i === -1) return
      if (open) setActive(i)
      else commit(i)
      return
    }
    typed.current.text = '' // any other key ends the typed string
    if (!open) {
      // AC4: preventDefault, so Enter and Space don't also click the button's popovertarget
      if (['Enter', ' ', 'ArrowDown', 'ArrowUp'].includes(key)) {
        event.preventDefault()
        setOpen(true)
      }
      return
    }
    const moves = { ArrowDown: Math.min(at + 1, last), ArrowUp: Math.max(at - 1, 0), Home: 0, End: last }
    if (key in moves) {
      event.preventDefault()
      setActive(moves[key])
    } else if (key === 'Enter' || key === ' ') {
      event.preventDefault()
      commit(at)
      hide()
    } else if (key === 'Escape') {
      // AC8: only this popup closes, not a dialog or popover around it
      event.preventDefault()
      event.stopPropagation()
      hide()
    } else if (key === 'Tab') {
      hide() // AC9: focus moves on as usual
    }
  }

  // Q6: React's state drives the popover where the API exists
  useEffect(() => {
    const popup = list.current
    if (!popup?.showPopover) return
    const isOpen = popup.matches(':popover-open')
    if (open && !isOpen) popup.showPopover()
    if (!open && isOpen) popup.hidePopover()
  }, [open])

  useEffect(() => {
    const popup = list.current
    const sync = (event) => {
      setOpen(event.newState === 'open')
      if (event.newState !== 'open') setActive(null)
    }
    popup.addEventListener('toggle', sync)
    return () => popup.removeEventListener('toggle', sync)
  }, [])

  // AC3: a press outside closes it (the browser's light dismiss does too, where it has popovers)
  useEffect(() => {
    if (!open) return
    const outside = (event) => {
      if (!trigger.current?.contains(event.target) && !list.current?.contains(event.target)) hide()
    }
    document.addEventListener('pointerdown', outside)
    return () => document.removeEventListener('pointerdown', outside)
  }, [open])

  // Q8: the active option stays in view in a scrolling list
  useEffect(() => {
    if (open) document.getElementById(optionId(at))?.scrollIntoView?.({ block: 'nearest' })
  }, [open, at]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <button
        ref={trigger}
        type="button"
        id={id}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open && options.length ? optionId(at) : undefined}
        aria-label={ariaLabel}
        aria-labelledby={labelledBy}
        disabled={disabled}
        value={shown}
        popoverTarget={listId}
        style={{ anchorName: `--${listId}` }}
        onClick={() => {
          if (!list.current.showPopover) open ? hide() : setOpen(true) // jsdom: no popovertarget to toggle it
        }}
        onKeyDown={keyDown}
        onKeyUp={(event) => event.key === ' ' && event.preventDefault()} // Firefox clicks a button on Space's keyup
        className={`${field} inline-flex min-w-0 cursor-pointer items-center justify-between gap-2 text-left disabled:cursor-not-allowed ${className}`}
      >
        <span className="min-w-0 truncate">{options[index]?.label}</span>
        {chevron}
      </button>
      {name && <input type="hidden" name={name} value={shown} disabled={disabled} />}
      {/* spans, so it can sit in a <p>; Q8: at least the button's width, at most the viewport's, scrolling past 18rem */}
      <span
        ref={list}
        id={listId}
        role="listbox"
        popover="auto"
        aria-labelledby={labelledBy ?? (ariaLabel ? undefined : id)}
        aria-label={ariaLabel}
        style={{ positionAnchor: `--${listId}` }}
        className={`${popover} max-h-72 max-w-[calc(100vw-1rem)] min-w-[anchor-size(width)] cursor-default overflow-y-auto p-1 font-normal open:grid [position-area:bottom_span-right]`}
      >
        {open &&
          options.map((o, i) => (
            <span
              key={String(o.value)}
              id={optionId(i)}
              role="option"
              aria-selected={i === index}
              data-active={i === at || undefined}
              data-value={String(o.value)}
              className={option}
              onPointerDown={(event) => event.preventDefault()} // focus stays on the button
              onMouseDown={(event) => event.preventDefault()}
              onMouseMove={() => i !== at && setActive(i)} // Q9
              onClick={() => {
                commit(i)
                hide(true)
              }}
            >
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                className={`mt-0.5 size-4 shrink-0 text-accent ${i === index ? '' : 'invisible'}`}
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
              >
                <path d="M20 6 9 17l-5-5" />
              </svg>
              <span className="min-w-0">{o.label}</span>
            </span>
          ))}
      </span>
    </>
  )
}
