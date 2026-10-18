// Shared by the Layout and page tests: a fetch mock keyed by "METHOD url", and the app's routes in a memory router.
import { cleanup, render } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, vi } from 'vitest'
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
