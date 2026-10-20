import { useState } from 'react'
import { button } from './styles.js'

/**
 * 022 Q9, 023 Q9: Run, Retry, Stop, and Run next, disabled while their request is in flight. `action` never rejects.
 * 046 Q7: while pending it's aria-busy, and a ring spinner in currentColor sits over the label, which turns transparent
 * but keeps the button's size and name. Both share one grid cell in an inner span, so `className` stays the one passed.
 */
export function ActionButton({ action, disabled, className = button, children, ...rest }) {
  const [busy, setBusy] = useState(false)
  async function click() {
    setBusy(true)
    try {
      await action()
    } finally {
      setBusy(false)
    }
  }
  return (
    <button
      type="button"
      onClick={click}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={className}
      {...rest}
    >
      <span className="inline-grid place-items-center">
        <span className={`col-start-1 row-start-1 ${busy ? 'opacity-0' : ''}`}>{children}</span>
        {busy && (
          <span
            aria-hidden="true"
            className="col-start-1 row-start-1 size-[1em] rounded-full border-2 border-current border-r-transparent motion-safe:animate-spin"
          />
        )}
      </span>
    </button>
  )
}
