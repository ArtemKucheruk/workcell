import { screen, waitFor, within } from '@testing-library/react'
import { expect, test } from 'vitest'
import { expectSkeleton, fetched, mockFetch, renderAt } from '../../test/render.jsx'

const API = '/api/docs/fctl'
/** 029's FctlDoc: body_html with heading ids, and its headings. */
const DOC = {
  body_html: '<h2 id="install">Install</h2>\n<p>uv tool install</p>\n<h2 id="fctl-serve">fctl serve</h2>\n'
    + '<h2 id="fctl-submit">fctl submit</h2>\n',
  headings: [
    { id: 'install', text: 'Install', level: 2 },
    { id: 'fctl-serve', text: 'fctl serve', level: 2 },
    { id: 'fctl-submit', text: 'fctl submit', level: 2 },
  ],
}

/** Renders `at` with /api/docs/fctl answering `hit`, and waits for the h1. */
async function open(hit = [200, DOC], at = '/docs/fctl') {
  const fetch = mockFetch({ [`GET ${API}`]: hit })
  const view = renderAt(at)
  await screen.findByRole('heading', { level: 1, name: 'fctl reference' })
  return { fetch, ...view }
}
const contents = () => screen.queryByRole('navigation', { name: 'Contents' })
const loads = (fetch) => fetched(fetch).filter((url) => url === API)

/** Runs `fn` with a recording Element.prototype.scrollIntoView, which jsdom lacks; the elements it was called on. */
async function scrolls(fn) {
  const scrolled = []
  Element.prototype.scrollIntoView = function () {
    scrolled.push(this)
  }
  try {
    await fn()
    await new Promise((r) => setTimeout(r, 50)) // let the effect run, if it would
    return scrolled
  } finally {
    delete Element.prototype.scrollIntoView
  }
}

test('AC16: fetches once, no polling; the h1, the title, and body_html through Markdown', async () => {
  const { fetch } = await open()
  const main = screen.getByRole('main')
  const serve = await within(main).findByRole('heading', { level: 2, name: 'fctl serve' })
  expect(serve.id).toBe('fctl-serve')
  expect(serve.closest('.markdown')).toBeTruthy()
  await waitFor(() => expect(document.title).toBe('fctl reference · Claude Factories'))
  await new Promise((r) => setTimeout(r, 50)) // no polling, so nothing more arrives
  expect(loads(fetch)).toEqual([API])
})

test('AC17: Contents has one link per heading, in order, named by text, to #id', async () => {
  await open()
  const links = await waitFor(() => within(contents()).getAllByRole('link'))
  expect(links.map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
    ['Install', '#install'], ['fctl serve', '#fctl-serve'], ['fctl submit', '#fctl-submit'],
  ])
})

test('AC18: a heading text with markup shows as literal text, with no <b> in the nav', async () => {
  await open([200, { body_html: '<h2 id="b-x-b">&lt;b&gt;x&lt;/b&gt;</h2>\n', headings: [{ id: 'b-x-b', text: '<b>x</b>', level: 2 }] }])
  const link = await waitFor(() => within(contents()).getByRole('link', { name: '<b>x</b>' }))
  expect(link.textContent).toBe('<b>x</b>')
  expect(contents().querySelector('b')).toBeNull()
})

test('AC19: a deep link scrolls its heading into view once the content has rendered', async () => {
  const scrolled = await scrolls(async () => {
    await open([200, DOC], '/docs/fctl#fctl-submit')
    await waitFor(() => expect(document.getElementById('fctl-submit')).toBeTruthy())
  })
  expect(scrolled).toEqual([document.getElementById('fctl-submit')])
})

test('AC19: a malformed or unknown hash throws nothing and scrolls nothing', async () => {
  for (const hash of ['#%E0', '#nope']) {
    const scrolled = await scrolls(async () => {
      const { unmount } = await open([200, DOC], `/docs/fctl${hash}`)
      await waitFor(() => expect(contents()).toBeTruthy())
      await new Promise((r) => setTimeout(r, 50))
      unmount()
    })
    expect(scrolled).toEqual([])
  }
})

test('AC20, 046 FE14: a skeleton before the response; a 500 shows its detail in an alert, with no Contents', async () => {
  mockFetch({}).mockImplementation(() => new Promise(() => {})) // nothing ever answers
  const { unmount } = renderAt('/docs/fctl')
  expectSkeleton(await screen.findByRole('status'))
  expect(contents()).toBeNull()
  unmount()

  await open([500, { detail: 'boom' }])
  expect((await screen.findByRole('alert')).textContent).toBe('boom')
  expect(contents()).toBeNull()
  expect(screen.queryByRole('status')).toBeNull()
})
