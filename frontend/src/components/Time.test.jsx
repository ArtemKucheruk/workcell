import { cleanup, render } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { Time } from './Time.jsx'

beforeEach(() => {
  vi.stubEnv('TZ', 'Asia/Tokyo') // UTC+9, as in the page tests
  vi.setSystemTime(new Date('2026-10-20T12:00:00+09:00'))
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

/** The <time> a render of `props` gives: its text, datetime, and title. */
function shown(props) {
  const { container, unmount } = render(<Time {...props} />)
  const time = container.querySelector('time')
  const out = [time.textContent, time.getAttribute('datetime'), time.getAttribute('title')]
  unmount()
  return out
}

test('046 FE1: relative is just now, Nm ago, Nh ago, yesterday, Nd ago, then the local date, with the local time in title', () => {
  const cases = [
    ['2026-10-20 12:00:30', 'just now'], // the future
    ['2026-10-20 11:59:31', 'just now'],
    ['2026-10-20 11:55:00', '5m ago'],
    ['2026-10-20 11:00:00', '1h ago'],
    ['2026-10-19 12:30:00', '23h ago'],
    ['2026-10-19 11:00:00', 'yesterday'],
    ['2026-10-18 23:00:00', '2d ago'],
    ['2026-10-14 09:00:00', '6d ago'],
    ['2026-10-13 23:59:00', '2026-10-13'],
  ]
  const iso = (local) => new Date(`${local.replace(' ', 'T')}+09:00`).toISOString()
  expect(cases.map(([local]) => shown({ iso: iso(local), relative: true }))).toEqual(
    cases.map(([local, text]) => [text, iso(local), local.slice(0, 16)]),
  )
  // without `relative`: the local YYYY-MM-DD HH:MM as before, and no title
  expect(shown({ iso: '2026-10-20T02:55:00Z' })).toEqual(['2026-10-20 11:55', '2026-10-20T02:55:00Z', null])
})
