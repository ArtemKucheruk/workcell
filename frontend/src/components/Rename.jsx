import { useEffect, useRef, useState } from 'react'
import { ErrorMessage } from './ErrorMessage.jsx'
import { field } from './styles.js'

/**
 * 049 FE5–FE9, Q10: a name edited in place, focused with all of it selected. Enter sends `save` even unchanged; a refusal
 * shows under the input, which keeps the text. Esc or blur cancels with no request. `onClose(focus)` asks the row to
 * put focus on its `⋯` (after a save or Esc). 051: moved out of the sidebar unchanged, for the Factories list too.
 */
export function Rename({ label, name, save, onClose }) {
  const input = useRef(null)
  const busy = useRef(false)
  const [error, setError] = useState(null)
  useEffect(() => {
    input.current.focus()
    input.current.select()
  }, [])

  async function submit(event) {
    event.preventDefault()
    if (busy.current) return
    busy.current = true
    try {
      await save(input.current.value)
    } catch (err) {
      setError(err)
      return
    } finally {
      busy.current = false
    }
    onClose(true)
  }

  return (
    <form onSubmit={submit} className="grid min-w-0 flex-1 gap-1">
      <input
        ref={input}
        type="text"
        aria-label={label}
        defaultValue={name}
        onKeyDown={(event) => {
          if (event.key !== 'Escape') return
          event.preventDefault() // else the same Esc also closes a modal drawer
          onClose(true)
        }}
        onBlur={() => onClose(false)}
        className={`${field} w-full`}
      />
      {error && <ErrorMessage error={error} />}
    </form>
  )
}
