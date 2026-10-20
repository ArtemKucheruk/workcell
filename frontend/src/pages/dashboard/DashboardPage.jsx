import { useCallback, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router'
import { dashboardPage } from '../../api/pages.js'
import { RunningBadge, TaskState } from '../../components/Badge.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { muted } from '../../components/styles.js'
import { Time } from '../../components/Time.jsx'
import { usePoll } from '../../hooks/usePoll.js'

const num = 'text-right tabular-nums'

const TaskLink = ({ id, title }) => <Link to={`/tasks/${id}`}>{`#${id} ${title}`}</Link>
const ProjectLink = ({ id, name }) => <Link to={`/projects/${id}`}>{name}</Link>

function Tiles({ tiles, counts, show }) {
  return (
    <ul className="grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-3">
      {Object.entries(tiles).map(([key, label]) => (
        <li key={key}>
          <Link
            to={`/?show=${key}`}
            aria-current={key === show ? 'page' : undefined}
            className="group grid h-full gap-1 rounded-md border border-line px-3 py-2 text-inherit hover:no-underline aria-[current=page]:border-accent aria-[current=page]:ring-1 aria-[current=page]:ring-accent"
          >
            <span className={`text-sm group-hover:underline ${muted}`}>{label}</span>{' '}
            <strong className="text-3xl tabular-nums">{counts[key]}</strong>
          </Link>
        </li>
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
  )
}

function Rounds({ done }) {
  if (!done.length) return <p>No tasks done in the last 30 days.</p>
  const rounds = done.map((t) => t.rounds)
  return (
    <>
      <p>
        Average <strong>{(rounds.reduce((a, b) => a + b, 0) / rounds.length).toFixed(1)}</strong> · Max{' '}
        <strong>{Math.max(...rounds)}</strong>
      </p>
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

function Workspaces({ workspaces }) {
  if (!workspaces.length) {
    return (
      <p>
        No projects yet. Run <code>{'fctl connect --workspace <name>'}</code> inside a repo.
      </p>
    )
  }
  return (
    <ul className="grid gap-1">
      {workspaces.map((w) => (
        <li key={w.id}>
          <Link to={`/workspaces/${w.id}`}>{w.name}</Link>{' '}
          <span className={muted}>{w.projects === 1 ? '1 project' : `${w.projects} projects`}</span>
        </li>
      ))}
    </ul>
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
  if (!page) return <p className={muted}>Loading…</p>
  return (
    <>
      <h1 className="mb-4">Dashboard</h1>
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
      <section aria-labelledby="workspaces">
        <h2 id="workspaces">Workspaces</h2>
        <Workspaces workspaces={page.workspaces} />
      </section>
    </>
  )
}
