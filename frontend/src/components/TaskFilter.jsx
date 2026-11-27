import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { Select } from './Select.jsx'
import { field, muted } from './styles.js'

/** The text field's id: Clear filter focuses it (117 AC8). */
export const FILTER_ID = 'task-filter'

/**
 * 117 AC2, AC3, Q2: does `card` pass the filter? `q` is the raw text, trimmed and case-folded here; `#12` is id 12 only,
 * `12` is id 12 or a title containing it, anything else a title substring. `module` is '' (all), 'none', or a module id.
 */
export function matches(card, q, module) {
  if (module === 'none' ? card.module != null : module && String(card.module?.id) !== module) return false
  const text = q.trim().toLowerCase()
  if (!text) return true
  const hash = /^#(\d+)$/.exec(text)
  if (hash) return card.id === Number(hash[1])
  if (/^\d+$/.test(text) && card.id === Number(text)) return true
  return card.title.toLowerCase().includes(text)
}

/**
 * 117 AC4: the filter's state, read from and written to `?q=` and `?module=` with `replace`, so typing adds no history
 * and the other params (Reviews' `tab`) stay. Q1: a `module` that is neither `none` nor one of `modules` is All modules.
 * AC10: `onChange(on, keep)` runs after the params change, never on a poll or the first render.
 */
export function useTaskFilter(modules, onChange) {
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const raw = params.get('module') ?? ''
  const module = raw === 'none' || modules.some((m) => String(m.id) === raw) ? raw : ''
  const on = q.trim() !== '' || module !== ''
  const keep = (card) => matches(card, q, module)

  function update(changes) {
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev)
        for (const [key, value] of Object.entries(changes)) value ? next.set(key, value) : next.delete(key)
        return next
      },
      { replace: true },
    )
  }

  const latest = useRef(onChange)
  latest.current = onChange
  const seen = useRef(`${q}\n${raw}`)
  useEffect(() => {
    const key = `${q}\n${raw}`
    if (key === seen.current) return
    seen.current = key
    latest.current?.(on, keep)
  }) // runs after every render, acting only when the params changed

  return {
    q,
    module,
    on,
    keep,
    setQ: (value) => update({ q: value }),
    setModule: (value) => update({ module: value }),
    clear() {
      update({ q: '', module: '' })
      document.getElementById(FILTER_ID)?.focus()
    },
  }
}

/** 117 AC8: `No tasks match.` and the like, with Clear filter. */
export function NoMatch({ text, filter, className = '' }) {
  return (
    <p className={`flex flex-wrap items-center gap-3 ${muted} ${className}`}>
      {text}
      <button type="button" onClick={filter.clear} className="cursor-pointer text-accent underline">
        Clear filter
      </button>
    </p>
  )
}

/**
 * 117 AC1, AC9: the filter bar, a search field and, when the project has modules, the Module Select. The field keeps
 * its own text so the caret never jumps while the URL catches up; a change of `?q=` from outside (Clear filter) resets it.
 */
export function TaskFilter({ filter, modules }) {
  const [text, setText] = useState(filter.q)
  useEffect(() => setText(filter.q), [filter.q])
  function type(value) {
    setText(value)
    filter.setQ(value)
  }
  return (
    <div className="mb-4 flex flex-wrap items-end gap-3">
      <div className="grid gap-1">
        <label htmlFor={FILTER_ID} className={`text-sm ${muted}`}>
          Filter by #id or title
        </label>
        <input
          id={FILTER_ID}
          type="search"
          value={text}
          onChange={(event) => type(event.target.value)}
          onKeyDown={(event) => {
            if (event.key !== 'Escape' || !text) return
            event.preventDefault()
            type('')
          }}
          className={`${field} w-64 max-w-full`}
        />
      </div>
      {modules.length > 0 && (
        <div className="grid gap-1">
          <label htmlFor="task-filter-module" className={`text-sm ${muted}`}>
            Module
          </label>
          <Select
            id="task-filter-module"
            value={filter.module}
            onChange={filter.setModule}
            options={[
              { value: '', label: 'All modules' },
              { value: 'none', label: 'No module' },
              ...modules.map((m) => ({ value: String(m.id), label: m.name })),
            ]}
          />
        </div>
      )}
    </div>
  )
}
