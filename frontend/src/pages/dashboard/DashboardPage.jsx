import { useCallback, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router'
import { dashboardPage } from '../../api/pages.js'
import { EscalatedPill, RunningBadge, TaskState, WaitingPill } from '../../components/Badge.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { Block, Skeleton } from '../../components/Skeleton.jsx'
import { muted } from '../../components/styles.js'
import { Time } from '../../components/Time.jsx'
import { usePoll } from '../../hooks/usePoll.js'

const num = 'text-right tabular-nums'

const TaskLink = ({ id, title }) => <Link to={`/tasks/${id}`}>{`#${id} ${title}`}</Link>
const ProjectLink = ({ id, name }) => <Link to={`/projects/${id}`}>{name}</Link>

/** Q7: the split is frontend-only; the backend's TILES keep their order. */
const GROUPS = [
  ['Attention', ['waiting', 'escalated', 'running']],
  ['Throughput', ['done_week', 'runs_week', 'backlog', 'in_progress', 'review', 'done']],
]
// Q6: an Attention count above 0 takes its token on the count and the border; class names in full for Tailwind's scanner
const HOT = {
  waiting: ['border-accent', 'text-accent'],
  escalated: ['border-danger', 'text-danger'],
  running: ['border-accent', 'text-accent'],
}

function Tiles({ tiles, counts, show }) {
  return (
    <div className="mt-8 grid gap-4">
      {GROUPS.map(([group, keys]) => (
        <div key={group}>
          <p id={`tiles-${group.toLowerCase()}`} className={`mb-1.5 text-xs font-semibold tracking-wide uppercase ${muted}`}>
            {group}
          </p>
          {/* both groups share one column grid, so their tiles line up */}
          <ul aria-labelledby={`tiles-${group.toLowerCase()}`} className="grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-3">
            {keys.map((key) => {
              const [border, count] = (counts[key] > 0 && HOT[key]) || ['border-line', '']
              return (
                <li key={key}>
                  <Link
                    to={`/?show=${key}`}
                    aria-current={key === show ? 'page' : undefined}
                    className={`group grid h-full gap-1 rounded-md border px-3 py-2 text-inherit hover:no-underline aria-[current=page]:border-accent aria-[current=page]:ring-1 aria-[current=page]:ring-accent ${border}`}
                  >
                    <span className={`text-sm group-hover:underline ${muted}`}>{tiles[key]}</span>{' '}
                    <strong className={`text-3xl tabular-nums ${count}`}>{counts[key]}</strong>
                  </Link>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
    </div>
  )
}

/** Q4: floored minutes, hours, or days since `since`, from the clock at render; the future (clock skew) reads 0m. */
function Age({ since }) {
  const m = Math.max(0, Math.floor((Date.now() - Date.parse(since)) / 60000))
  const text = m < 60 ? `${m}m` : m < 1440 ? `${Math.floor(m / 60)}h` : `${Math.floor(m / 1440)}d`
  return (
    <time dateTime={since} className="tabular-nums">
      {text}
    </time>
  )
}

/** Q3: links to the review, where Approve and Request changes are; an escalated row keeps the Reviews rows' red left bar. */
function NeedsRow({ task, escalated }) {
  return (
    <li
      className={`flex flex-wrap items-baseline gap-x-3 gap-y-1 border-l-4 bg-surface px-4 py-2.5 ${escalated ? 'border-danger' : 'border-transparent'}`}
    >
      <Link to={`/tasks/${task.id}/review`} className="font-medium wrap-anywhere">
        {`#${task.id} ${task.title}`}
      </Link>
      {escalated ? <EscalatedPill /> : <WaitingPill />}
      <span className={`ml-auto flex flex-wrap items-baseline gap-x-3 text-sm ${muted}`}>
        <ProjectLink id={task.project_id} name={task.project} />
        {task.round != null && <span>{`round ${task.round}`}</span>}
        <Age since={task.since} />
      </span>
    </li>
  )
}

/** Q2: escalated first, then waiting, each in the backend's newest-first order. Q10: ignores ?show=. */
function NeedsYou({ waiting, escalated }) {
  if (!waiting.length && !escalated.length) {
    return <p className={`rounded-md border border-line px-4 py-3 ${muted}`}>Nothing needs you.</p>
  }
  return (
    // the 1px gaps show the list's `line` background as dividers, as on the Reviews page
    <ul className="grid gap-px overflow-hidden rounded-md border border-line bg-line">
      {escalated.map((t) => (
        <NeedsRow key={t.id} task={t} escalated />
      ))}
      {waiting.map((t) => (
        <NeedsRow key={t.id} task={t} />
      ))}
    </ul>
  )
}

function Listed({ page }) {
  const { show, listed } = page
  if (show === 'runs_week') {
    if (!listed.length) return <p>No runs.</p>
    return (
      <table>
        <thead>
          <tr><th scope="col">Run</th><th scope="col">Task</th><th scope="col">Project</th><th scope="col">Status</th><th scope="col">Started</th></tr>
        </thead>
        <tbody>
          {listed.map((r) => (
            <tr key={r.id}>
              <td>{`run #${r.id}`}</td>
              <td><TaskLink id={r.task_id} title={r.title} /></td>
              <td><ProjectLink id={r.project_id} name={r.project} /></td>
              {/* 043 Q11: only a running run gets a badge; the outcomes stay plain text */}
              <td>{r.status === 'running' ? <RunningBadge /> : r.status}</td>
              <td><Time iso={r.started_at} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    )
  }
  if (!listed.length) return <p>No tasks.</p>
  return (
    <table>
      <thead>
        <tr><th scope="col">Task</th><th scope="col">Project</th><th scope="col">Status</th></tr>
      </thead>
      <tbody>
        {listed.map((t) => (
          <tr key={t.id}>
            <td><TaskLink id={t.id} title={t.title} /></td>
            <td><ProjectLink id={t.project_id} name={t.project} /></td>
            <td><TaskState task={t} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function OpenTasks({ open }) {
  if (!open.length) return <p>No open tasks.</p>
  return (
    // Q11: at every width; it scrolls only when the table is wider than the box
    <div className="overflow-x-auto">
      <table>
        <thead>
          <tr><th scope="col">Project</th><th scope="col">Backlog</th><th scope="col">In progress</th><th scope="col">Review</th></tr>
        </thead>
        {open.map((ws) => (
          <tbody key={ws.id}>
            <tr>
              <th colSpan={4} scope="rowgroup"><Link to={`/workspaces/${ws.id}`}>{ws.name}</Link></th>
            </tr>
            {ws.projects.map((p) => (
              <tr key={p.id}>
                <td className="pl-6"><ProjectLink id={p.id} name={p.name} /></td>
                <td className={num}>{p.backlog}</td>
                <td className={num}>{p.in_progress}</td>
                <td className={num}>{p.review}</td>
              </tr>
            ))}
          </tbody>
        ))}
      </table>
    </div>
  )
}

// in viewBox units, which are px until the svg shrinks to fit
const BAR = 8
const GAP = 4
const TALL = 40

/**
 * Q8: one bar per done task, oldest left (the table's reverse), height rounds / max. aria-hidden: the table has the
 * same numbers. BAR + GAP px per task, squeezed to the box's width when many tasks would overflow it.
 */
function Bars({ done, max }) {
  const step = BAR + GAP
  return (
    <svg
      aria-hidden="true"
      viewBox={`0 0 ${done.length * step - GAP} ${TALL}`}
      preserveAspectRatio="none"
      style={{ width: done.length * step - GAP }}
      className="h-10 max-w-full min-w-0 fill-accent"
    >
      {[...done].reverse().map((t, i) => {
        const h = (TALL * t.rounds) / max
        return (
          <rect key={t.id} x={i * step} y={TALL - h} width={BAR} height={h} rx={1}>
            <title>{`#${t.id} ${t.title}: ${t.rounds} ${t.rounds === 1 ? 'round' : 'rounds'}`}</title>
          </rect>
        )
      })}
    </svg>
  )
}

function Rounds({ done }) {
  if (!done.length) return <p>No tasks done in the last 30 days.</p>
  const rounds = done.map((t) => t.rounds)
  const max = Math.max(...rounds)
  return (
    <>
      <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
        <p>
          Average <strong>{(rounds.reduce((a, b) => a + b, 0) / rounds.length).toFixed(1)}</strong> · Max{' '}
          <strong>{max}</strong>
        </p>
        <Bars done={done} max={max} />
      </div>
      <table>
        <thead>
          <tr><th scope="col">Task</th><th scope="col">Project</th><th scope="col">Rounds</th><th scope="col">Done</th></tr>
        </thead>
        <tbody>
          {done.map((t) => (
            <tr key={t.id}>
              <td><TaskLink id={t.id} title={t.title} /></td>
              <td><ProjectLink id={t.project_id} name={t.project} /></td>
              <td className={num}>{t.rounds}</td>
              <td><Time iso={t.done_at} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

/** 046 Q5: the h1, a one-row Needs you box, and the two tile groups (3 and 6 tiles) in the tiles' grid. */
function DashboardSkeleton() {
  return (
    <Skeleton>
      <Block className="mb-4 h-8 w-40" />
      <Block className="mb-2 h-7 w-28" />
      <div className="rounded-md border border-line px-4 py-2.5">
        <Block className="h-6 w-80 max-w-full" />
      </div>
      <div className="mt-8 grid gap-4">
        {[3, 6].map((n) => (
          <div key={n}>
            <Block className="mb-1.5 h-4 w-20" />
            <div className="grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-3">
              {Array.from({ length: n }, (_, i) => (
                // a tile: py-2, a text-sm label, gap-1, a text-3xl count, and its border
                <Block key={i} className="h-19.5" />
              ))}
            </div>
          </div>
        ))}
      </div>
    </Skeleton>
  )
}

/** docs/ui.md §8 item 1. */
export function DashboardPage() {
  const [params] = useSearchParams()
  const show = params.get('show') ?? ''
  const load = useCallback(() => dashboardPage(show), [show])
  const { data: page, error } = usePoll(load)
  useEffect(() => {
    document.title = 'Claude Factories'
  }, [])

  if (error) return error.status === 404 ? <NotFound detail={error.message} /> : <ErrorMessage error={error} />
  if (!page) return <DashboardSkeleton />
  return (
    <>
      <h1 className="mb-4">Dashboard</h1>
      <section aria-labelledby="needs-you">
        <h2 id="needs-you" className="mt-0">
          Needs you
        </h2>
        <NeedsYou waiting={page.waiting} escalated={page.escalated} />
      </section>
      <Tiles tiles={page.tiles} counts={page.counts} show={page.show} />
      {page.show && (
        <section aria-labelledby="listed">
          <h2 id="listed">{page.tiles[page.show]}</h2>
          <Listed page={page} />
        </section>
      )}
      <section aria-labelledby="open-tasks">
        <h2 id="open-tasks">Open tasks</h2>
        <OpenTasks open={page.open_tasks} />
      </section>
      <section aria-labelledby="rounds">
        <h2 id="rounds">
          Rounds per task <span className={`text-sm font-normal ${muted}`}>done in the last 30 days</span>
        </h2>
        <Rounds done={page.done} />
      </section>
    </>
  )
}
