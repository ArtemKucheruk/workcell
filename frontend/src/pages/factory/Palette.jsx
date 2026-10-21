import { useId, useState } from 'react'
import { AGENTS, CONDITIONS, Icon, KINDS, tint } from './graph.jsx'

/** The dataTransfer type a palette drag carries; the flow's drop reads it back. */
export const DRAG = 'application/x-factory-node'

const GROUPS = [
  ['Agents', AGENTS],
  ['Conditions', CONDITIONS],
]

// §8.7: open from md up, collapsed below it; jsdom has no matchMedia, so tests start open
const wide = () => window.matchMedia?.('(min-width: 48rem)').matches ?? true

/**
 * FE12–FE14: the palette, beside the flow from md up and above it below. `«` collapses it to a rail with `»`. Each item
 * drags onto the flow, or a click (Enter, Space) calls `onAdd(type)`, which adds it at the viewport's center.
 */
export function Palette({ onAdd }) {
  const [open, setOpen] = useState(wide)
  const id = useId()
  return (
    <div className={`shrink-0 border-b border-line bg-raised md:border-r md:border-b-0 ${open ? 'md:w-52' : ''} md:overflow-y-auto`}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        aria-label="Palette"
        title={open ? 'Hide the palette' : 'Show the palette'}
        onClick={() => setOpen(!open)}
        className="m-2 cursor-pointer rounded-md px-2 py-1 text-sm font-medium text-muted hover:bg-surface hover:text-fg"
      >
        {/* the rail beside the flow has room for » alone; below md the bar spans the page */}
        <span aria-hidden="true">
          {open ? '« Palette' : <>»<span className="md:hidden"> Palette</span></>}
        </span>
      </button>
      <div id={id} hidden={!open} className="grid gap-4 px-2 pb-3 max-md:grid-cols-2">
        {GROUPS.map(([heading, types]) => (
          <section key={heading} aria-labelledby={`${id}-${heading}`} className="grid content-start gap-1">
            <h2 id={`${id}-${heading}`} className="m-0 px-2 text-xs font-semibold text-muted">
              {heading}
            </h2>
            <ul className="grid gap-0.5">
              {types.map((type) => (
                <li key={type}>
                  <button
                    type="button"
                    draggable
                    onDragStart={(event) => {
                      event.dataTransfer.setData(DRAG, type)
                      event.dataTransfer.effectAllowed = 'move'
                    }}
                    onClick={() => onAdd(type)}
                    className="flex w-full cursor-grab items-center gap-2 rounded-md px-2 py-1 text-left text-sm hover:bg-surface active:cursor-grabbing"
                  >
                    <Icon type={type} className={tint(type)} />
                    {KINDS[type].label}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  )
}
