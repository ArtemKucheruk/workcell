// Shared by the Layout and page tests: a fetch mock keyed by "METHOD url", and the app's routes in a memory router.
import { act, cleanup, render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, expect, vi } from 'vitest'
import { routes } from '../app/routes.jsx'

afterEach(cleanup)

/**
 * `responses` maps "GET /api/auth" to [status, body], or to an Error for a rejected fetch.
 * A string body goes out as is (not JSON). Anything unlisted is a 404 {"detail":"Not Found"}.
 */
export function mockFetch(responses) {
  const fetch = vi.fn(async (url, init = {}) => {
    const hit = responses[`${init.method ?? 'GET'} ${url}`] ?? [404, { detail: 'Not Found' }]
    if (hit instanceof Error) throw hit
    const [status, body] = hit
    return new Response(typeof body === 'string' ? body : JSON.stringify(body), { status })
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}

export function renderAt(path) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  return { router, ...render(<RouterProvider router={router} />) }
}

/** Matches the innermost element whose whole text is `text`, across inline children like <code>. */
export const fullText = (text) => (_, el) =>
  el?.textContent === text && ![...el.children].some((child) => child.textContent === text)

/** The URLs fetch was called with, in order. */
export const fetched = (fetch) => fetch.mock.calls.map(([url]) => url)

/** 046: a class token in a className. */
export const cls = (name) => new RegExp(`(^|\\s)${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(\\s|$)`)

/**
 * 046 FE14: a skeleton is a status whose only text is an sr-only `Loading…`, whose other children are all
 * aria-hidden, and which holds nothing to navigate or focus by.
 */
export function expectSkeleton(status) {
  expect(status.getAttribute('role')).toBe('status')
  expect(status.textContent).toBe('Loading…')
  const [label, ...rest] = status.children
  expect(label.textContent).toBe('Loading…')
  expect(label.className).toMatch(cls('sr-only'))
  expect(rest.length).toBeGreaterThan(0)
  expect(rest.filter((el) => el.getAttribute('aria-hidden') !== 'true')).toEqual([])
  const named = 'h1, h2, h3, h4, h5, h6, [role=heading], a, button, input, select, textarea, [tabindex]'
  expect(status.querySelectorAll(named)).toHaveLength(0)
}

/** 046: the status elements that read exactly `Offline — retrying`. */
export const offline = () => screen.queryAllByRole('status').filter((el) => el.textContent === 'Offline — retrying')

/**
 * 046 FE9–FE13, under fake timers over a page that loaded `responses[key]`: a 502 and then a rejected fetch each show
 * one muted, fixed `Offline — retrying` status, with no alert and no detail, and the same node through a second failed
 * poll (FE12), while `stays()` still finds the page; the next good poll removes it. Then a 404 is the not-found page.
 */
export async function expectOfflineBanner(responses, key, stays) {
  const poll = () => act(() => vi.advanceTimersByTimeAsync(3000))
  const good = responses[key]
  for (const failure of [[502, { detail: 'Backend unreachable at http://127.0.0.1:4545' }], new TypeError('Failed to fetch')]) {
    responses[key] = failure
    await poll()
    const banner = offline()
    expect(banner).toHaveLength(1)
    expect(banner[0].className).toMatch(cls('text-muted'))
    expect(banner[0].className).toMatch(cls('fixed'))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(document.body.textContent).not.toMatch(/Backend unreachable|Failed to fetch/)
    stays()
    await poll()
    expect(offline()).toHaveLength(1)
    expect(offline()[0]).toBe(banner[0])
    responses[key] = good
    await poll()
    expect(offline()).toEqual([])
    stays()
  }
  responses[key] = [404, { detail: 'Not Found' }]
  await poll()
  expect(screen.getByRole('heading', { level: 1, name: 'Not Found' })).toBeTruthy()
  expect(offline()).toEqual([])
}
