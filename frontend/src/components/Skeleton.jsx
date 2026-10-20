import { Fragment } from 'react'

/**
 * 046 Q5: a page's first load. One polite status whose only words are the hidden `Loading…`; everything else is
 * aria-hidden blocks shaped like the top of the page, with the page's own grid and spacing classes, so the loaded page
 * takes their place without a jump. No headings, links, buttons, or fields inside.
 */
export function Skeleton({ children }) {
  return (
    <div role="status">
      <span className="sr-only">Loading…</span>
      <div aria-hidden="true">{children}</div>
    </div>
  )
}

/** A placeholder in tokens: `line` on surface, so it still shows on a raised column; the pulse holds still under reduced motion. */
export function Block({ className = '' }) {
  return <div className={`rounded bg-line motion-safe:animate-pulse ${className}`} />
}

// lines of body text: 16 px bars 8 px apart, one 24 px line each, ragged like prose
const WIDTHS = ['w-full', 'w-11/12', 'w-full', 'w-4/5', 'w-5/6', 'w-2/3']

export function Lines({ n = 4, className = '' }) {
  return (
    <div className={`grid gap-2 ${className}`}>
      {Array.from({ length: n }, (_, i) => (
        <Block key={i} className={`h-4 ${i === n - 1 ? 'w-1/2' : WIDTHS[i % WIDTHS.length]}`} />
      ))}
    </div>
  )
}

/** ProjectHeader's shape: the h1 (`name · workspace`), the factory state, then the page's own controls as `children`. */
export function ProjectHeaderSkeleton({ children }) {
  return (
    <div className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-2">
      <Block className="h-8 w-56" />
      <Block className="h-5 w-28" />
      {children}
    </div>
  )
}

/** A text-sm line: the breadcrumb, or a status line's pieces. */
export function Crumbs({ className = '' }) {
  return <Block className={`h-5 w-64 max-w-full ${className}`} />
}

/** The task, review, and transcript header: breadcrumb, the title row (`title` holds its right-hand side), and `children`. */
export function TitleSkeleton({ title, children }) {
  return (
    <div className="mb-6 grid gap-2">
      <Crumbs />
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <Block className="mr-auto h-8 w-80 max-w-full" />
        {title}
      </div>
      {children}
    </div>
  )
}

/** A button's height (34 px: a 24 px line, py-1, and its border). */
export function ButtonBlock({ className = 'w-20' }) {
  return <Block className={`h-8.5 ${className}`} />
}

/** A <dl> of `n` label and value rows, as on the two settings pages. */
export function Rows({ n }) {
  return (
    <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-1">
      {Array.from({ length: n }, (_, i) => (
        <Fragment key={i}>
          <Block className="h-6 w-28" />
          <Block className="h-6 w-64 max-w-full" />
        </Fragment>
      ))}
    </div>
  )
}

/** A tabs <nav>: a bottom rule under `n` tab-height labels. */
export function TabsSkeleton({ n = 2, className = '' }) {
  return (
    <div className={`flex gap-4 border-b border-line ${className}`}>
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="px-2 py-1">
          <Block className="h-6 w-24" />
        </div>
      ))}
    </div>
  )
}
