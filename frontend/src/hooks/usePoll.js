import { useEffect, useState } from 'react'

/**
 * Calls `fn` on mount, then `interval` ms after each call settles, so calls never overlap.
 * No interval: one call (Q5). `fn` must be stable (useCallback); a new `fn` restarts the loop.
 * A failure keeps the last data beside `error`; the next success clears `error`.
 */
export function usePoll(fn, interval) {
  const [state, setState] = useState({})
  useEffect(() => {
    let alive = true
    let timer
    const tick = () =>
      fn()
        .then((data) => alive && setState({ data }), (error) => alive && setState((s) => ({ ...s, error })))
        .finally(() => {
          if (alive && interval) timer = setTimeout(tick, interval)
        })
    tick()
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [fn, interval])
  // 050 Q8: Preline's plugins bind to what newly loaded data renders; a failure keeps the data, so it runs nothing
  useEffect(() => {
    if (state.data !== undefined) window.HSStaticMethods?.autoInit()
  }, [state.data])
  return state
}
