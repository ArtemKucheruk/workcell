import { useState } from 'react'
import { button } from './styles.js'

/** 022 Q9, 023 Q9: Run, Retry, Stop, and Run next, disabled while their request is in flight. `action` never rejects. */
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
    <button type="button" onClick={click} disabled={disabled || busy} className={className} {...rest}>
      {children}
    </button>
  )
}
