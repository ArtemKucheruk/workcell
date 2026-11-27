import { useCallback, useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { listModules } from '../../api/modules.js'
import { boardPage } from '../../api/pages.js'
import { EscalatedPill, WaitingPill } from '../../components/Badge.jsx'
import { Chip } from '../../components/Chip.jsx'
import { ErrorMessage, OfflineBanner } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { ProjectHeader } from '../../components/ProjectHeader.jsx'
import { Block, ProjectHeaderSkeleton, Skeleton, TabsSkeleton } from '../../components/Skeleton.jsx'
import { muted, tab } from '../../components/styles.js'
import { NoMatch, TaskFilter, useTaskFilter } from '../../components/TaskFilter.jsx'
import { usePoll } from '../../hooks/usePoll.js'

/** Q3: escalated, then waiting on me, then the rest (a manual move has no stage); sort is stable, so each group keeps the column's order. */
const rank = (card) => (card.escalated ? 0 : card.waiting ? 1 : 2)

/** Q4, 043: the board's pill for why an Open review waits; Closed rows and null stages have none. */
function State({ card }) {
  if (card.escalated) return <EscalatedPill />
  if (card.waiting) return <WaitingPill />
  return null
}

/** Q4: `#id title` and the state, then branch, round, the shared chips, and +/−; null parts are left out. */
function Row({ card, open }) {
  const bar = open && card.escalated
  return (
    // §8.1's red left bar; the others keep a clear one so titles line up. 040: a space before ${ for Tailwind's scanner
    <li className={`grid gap-1 border-l-4 bg-surface px-4 py-3 ${bar ? 'border-danger' : 'border-transparent'}`}>
      <p className="flex flex-wrap items-baseline gap-x-3">
        <Link to={`/tasks/${card.id}/review`} className="font-medium wrap-anywhere">
          {`#${card.id} ${card.title}`}
        </Link>
        {open && <State card={card} />}
      </p>
      {(card.branch || card.round != null) && (
        <p className={`flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm ${muted}`}>
          {card.branch && <code className="wrap-anywhere">{card.branch}</code>}
          {card.round != null && (
            <>
              <span>{`round ${card.round}`}</span>
              <span className="flex gap-2 text-fg">
                {Object.entries(card.verdicts ?? {}).map(([who, verdict]) => (
                  <Chip key={who} n={card.round} who={who} verdict={verdict} />
                ))}
              </span>
              <span className="tabular-nums">{`+${card.additions} −${card.deletions}`}</span>
            </>
          )}
        </p>
      )}
    </li>
  )
}

/** 046 Q5: the project header, the tabs, and a two-row list box. */
function ReviewsSkeleton() {
  return (
    <Skeleton>
      <ProjectHeaderSkeleton />
      <TabsSkeleton className="mb-4" />
      <div className="grid gap-px overflow-hidden rounded-md border border-line bg-line">
        {[0, 1].map((i) => (
          <div key={i} className="grid gap-1 bg-surface px-4 py-3">
            <Block className="h-6 w-72 max-w-full" />
            <Block className="h-5 w-96 max-w-full" />
          </div>
        ))}
      </div>
    </Skeleton>
  )
}

/** docs/ui.md §8 item 10, §8.5: the Review column as Open, the Done column as Closed. */
export function ReviewsPage() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const closed = params.get('tab') === 'closed' // Q5: any other tab is Open
  // Q6: the board's data, polled like the board; `tab` isn't a dep, so switching tabs fetches nothing
  const load = useCallback(() => boardPage(id), [id])
  const { data: page, error } = usePoll(load, 3000)
  // 117 Q1: the Module filter's options, loaded once as on the board; a failure hides the select
  const { data: modules } = usePoll(useCallback(() => listModules(id), [id]))
  // 117 AC10, Q4: a change of the filter, not a poll or a tab switch, says how many rows of the tab match
  const [said, setSaid] = useState('')
  const filter = useTaskFilter(modules?.modules ?? [], (on, keep) => {
    const n = (page?.columns[closed ? 'done' : 'review'] ?? []).filter(keep).length
    setSaid(on ? `${n} review${n === 1 ? ' matches' : 's match'}.` : '')
  })
  const name = page?.project.name
  useEffect(() => {
    if (name) document.title = `${name} · Reviews · Claude Factories`
  }, [name])

  if (error?.status === 404) return <NotFound detail={error.message} />
  if (!page) return error ? <ErrorMessage error={error} /> : <ReviewsSkeleton />
  const { project, columns } = page
  // 117 AC6: the tabs count, and list, only the matching rows
  const open = (columns.review ?? []).filter(filter.keep).sort((a, b) => rank(a) - rank(b))
  const done = (columns.done ?? []).filter(filter.keep)
  const rows = closed ? done : open
  const base = `/projects/${project.id}/reviews`
  // 117 AC7: each tab's link carries the filter, so switching tabs keeps it
  const keepFilter = new URLSearchParams()
  for (const key of ['q', 'module']) if (params.get(key)) keepFilter.set(key, params.get(key))
  const link = (more) => {
    const query = new URLSearchParams([...more, ...keepFilter]).toString()
    return query ? `${base}?${query}` : base
  }

  return (
    <>
      <ProjectHeader project={project} factory={page.factory} />
      {error && <OfflineBanner />}
      <p role="status" className="sr-only">
        {said}
      </p>
      <TaskFilter filter={filter} modules={modules?.modules ?? []} />
      <nav aria-label="Reviews tabs" className="mb-4 flex gap-4 border-b border-line">
        <Link to={link([])} aria-current={closed ? undefined : 'page'} className={tab}>
          {'Open '}
          <span className="tabular-nums">{open.length}</span>
        </Link>
        <Link to={link([['tab', 'closed']])} aria-current={closed ? 'page' : undefined} className={tab}>
          {'Closed '}
          <span className="tabular-nums">{done.length}</span>
        </Link>
      </nav>
      {filter.on && !rows.length ? (
        <NoMatch text="No reviews match." filter={filter} className="rounded-md border border-line px-4 py-8 justify-center" />
      ) : rows.length ? (
        // the 1px gaps show the list's `line` background as dividers, which a row's border colors can't touch
        <ul className="grid gap-px overflow-hidden rounded-md border border-line bg-line">
          {rows.map((card) => (
            <Row key={card.id} card={card} open={!closed} />
          ))}
        </ul>
      ) : (
        // Q12
        <p className={`rounded-md border border-line px-4 py-8 text-center ${muted}`}>
          {closed ? 'No closed reviews yet.' : 'Nothing waiting for review.'}
        </p>
      )}
    </>
  )
}
