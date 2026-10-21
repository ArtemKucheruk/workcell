import { act, cleanup, render, renderHook } from '@testing-library/react'
import { createElement } from 'react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { usePoll } from './usePoll.js'

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

const flush = () => act(() => vi.advanceTimersByTimeAsync(0))
const advance = (ms) => act(() => vi.advanceTimersByTimeAsync(ms))

test('AC12: calls on mount, then 3000 ms after each call settles; stops after unmount', async () => {
  let n = 0
  // each call takes 1000 ms, so a fixed 3000 ms interval would call again at 3000 instead of 4000
  const fn = vi.fn(() => new Promise((resolve) => setTimeout(() => resolve(++n), 1000)))
  const { result, unmount } = renderHook(() => usePoll(fn, 3000))
  expect(fn).toHaveBeenCalledTimes(1)
  await advance(1000)
  expect(result.current).toEqual({ data: 1 })
  await advance(2999)
  expect(fn).toHaveBeenCalledTimes(1)
  await advance(1)
  expect(fn).toHaveBeenCalledTimes(2)
  await advance(1000)
  expect(result.current).toEqual({ data: 2 })
  unmount()
  await advance(20000)
  expect(fn).toHaveBeenCalledTimes(2)
})

test('AC13: a rejection sets error, the next success clears it; no interval calls once', async () => {
  const boom = new Error('boom')
  const fn = vi.fn().mockRejectedValueOnce(boom).mockResolvedValue('ok')
  const { result } = renderHook(() => usePoll(fn, 3000))
  await flush()
  expect(result.current.error).toBe(boom)
  await advance(3000)
  expect(result.current).toEqual({ data: 'ok' })

  const once = vi.fn().mockResolvedValue('x')
  const single = renderHook(() => usePoll(once))
  await advance(60000)
  expect(once).toHaveBeenCalledTimes(1)
  expect(single.result.current).toEqual({ data: 'x' })
})

test('050 FE19: autoInit runs after each render carrying newly loaded data; not before, on a failure, or on a re-render', async () => {
  const seen = [] // what the DOM showed at each call
  vi.stubGlobal('HSStaticMethods', { autoInit: vi.fn(() => seen.push(document.querySelector('output')?.textContent)) })
  // each load is a new object, as each fetch's JSON is
  const fn = vi.fn().mockResolvedValueOnce({ v: 'a' }).mockRejectedValueOnce(new Error('boom')).mockImplementation(async () => ({ v: 'b' }))
  function Probe() {
    const { data, error } = usePoll(fn, 3000)
    return createElement('output', null, `${data?.v ?? ''}${error ? ' failed' : ''}`)
  }
  const { rerender } = render(createElement(Probe))
  expect(seen).toEqual([])
  await flush()
  expect(seen).toEqual(['a']) // after the render that shows 'a'
  rerender(createElement(Probe))
  await advance(3000)
  expect(document.querySelector('output').textContent).toBe('a failed')
  expect(seen).toEqual(['a'])
  await advance(3000)
  expect(seen).toEqual(['a', 'b'])
  await advance(3000)
  expect(seen).toEqual(['a', 'b', 'b']) // 050 Q8: each poll is a new load
})

test('050 FE20: without Preline, window.HSStaticMethods is undefined and loading data throws nothing', async () => {
  expect(window.HSStaticMethods).toBeUndefined()
  const fn = vi.fn().mockResolvedValue('x')
  const { result } = renderHook(() => usePoll(fn))
  await flush()
  expect(result.current).toEqual({ data: 'x' })
})
