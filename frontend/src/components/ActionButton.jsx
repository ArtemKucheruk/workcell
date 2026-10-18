import { useState } from 'react'

export const button =
  'cursor-pointer rounded-md border border-gray-300 px-3 py-1 font-medium hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:hover:bg-gray-800'

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
