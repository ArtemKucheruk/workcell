import { screen, within } from '@testing-library/react'
import { expect, test } from 'vitest'
import { expectSkeleton, mockFetch, renderAt } from '../test/render.jsx'

// every page's route, and the static h1 the two that have one render above their skeleton
const ROUTES = [
  ['/'], ['/workspaces/2'], ['/projects/3'], ['/projects/3/reviews'], ['/projects/3/code'], ['/projects/3/context'],
  ['/projects/3/settings'], ['/tasks/12'], ['/tasks/12/review'], ['/transcripts/5'],
  ['/docs/fctl', 'fctl reference'], ['/settings', 'Settings'],
]

test('046 FE14: while the first request is pending, each page is one skeleton status, alone in main but for a static h1', async () => {
  for (const [path, h1] of ROUTES) {
    mockFetch({}).mockImplementation(() => new Promise(() => {})) // nothing ever answers
    const { unmount } = renderAt(path)
    const main = screen.getByRole('main')
    const skeleton = await within(main).findByRole('status')
    expectSkeleton(skeleton)
    const others = [...main.children].filter((el) => el !== skeleton).map((el) => `${el.tagName} ${el.textContent}`)
    expect([path, skeleton.parentElement === main, others]).toEqual([path, true, h1 ? [`H1 ${h1}`] : []])
    unmount()
  }
})
