import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router'
import { boardPage } from '../../api/pages.js'
import { runNext, runTask } from '../../api/runs.js'
import { createTask, moveTask } from '../../api/tasks.js'
import { ActionButton } from '../../components/ActionButton.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { ProjectHeader } from '../../components/ProjectHeader.jsx'
import { button, field, muted, smallButton } from '../../components/styles.js'
import { Time } from '../../components/Time.jsx'
import { usePoll } from '../../hooks/usePoll.js'

const COLUMNS = { backlog: 'Backlog', in_progress: 'In progress', review: 'Review', done: 'Done' }
const SHORT = { security: 'sec', ux: 'ux', ui: 'ui', code: 'co' }
const SYMBOL = { PASS: '✓', CHANGES: '✗', pending: '·' }

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`

/** §8.1, as project.html: running, else stalled, else escalated, else waiting, else the stage. */
function StatusLine({ card, running, retry }) {
  const stage = card.stage ? ` · ${card.stage}` : ''
  if (running) return <p className="text-sm text-success">{`● running${stage}`}</p>
  if (card.stalled) {
    return (
      <p className="flex items-center justify-between gap-2 text-sm">
        <span><strong>stalled</strong>{stage}</span>
        {retry}
      </p>
    )
  }
  if (card.escalated) return <p className="text-sm font-semibold text-danger">⚠ NEEDS YOU — escalated</p>
  if (card.waiting) return <p className="text-sm"><strong>waiting on you</strong></p>
  return card.stage && <p className={`text-sm ${muted}`}>{card.stage}</p>
}

/** Q7: the chips stay on this page; `r2 sec✓ ux✓ ui· co✗`, then `+A −D`. Done cards show their rounds. */
function Rounds({ card }) {
  if (card.round == null) return null
  if (card.status === 'done') return <p className={`text-sm ${muted}`}>{plural(card.round, 'round')}</p>
  return (
    <>
      <p className="text-sm">
        {`r${card.round}`}
        {Object.entries(card.verdicts ?? {}).map(([who, verdict]) => (
          <Fragment key={who}>
            {' '}
            <span title={`${who}: ${verdict}`}>{`${SHORT[who] ?? who}${SYMBOL[verdict] ?? verdict}`}</span>
          </Fragment>
        ))}
      </p>
      <p className={`text-sm tabular-nums ${muted}`}>{`+${card.additions} −${card.deletions}`}</p>
    </>
  )
}

function Card({ card, canRun, onRun, onDragStart, onDragEnd }) {
  const running = card.status === 'in_progress' && card.run?.status === 'running'
  const runButton = (label) => (
    <ActionButton action={() => onRun(card.id)} disabled={!canRun} className={smallButton} aria-describedby={`task-${card.id}`}>
      {label}
    </ActionButton>
  )
  return (
    <li
      draggable="true"
      onDragStart={(event) => onDragStart(event, card.id)}
      onDragEnd={onDragEnd}
      // 040: a space before ${, or Tailwind's scanner reads `ring-line$` and generates no ring-line
      className={`grid cursor-grab gap-1 rounded-md bg-surface p-3 shadow-sm ring-1 ring-line ${
        card.escalated ? 'border-l-4 border-danger' : ''
      }`}
    >
      <Link id={`task-${card.id}`} to={`/tasks/${card.id}`} draggable="false" className="font-medium">
        {`#${card.id} ${card.title}`}
      </Link>
      <StatusLine card={card} running={running} retry={runButton('Retry')} />
      <Rounds card={card} />
      {running && card.started_at && (
        <p className={`text-sm ${muted}`}>
          started <Time iso={card.started_at} timeOnly />
        </p>
      )}
      {card.status === 'backlog' && <p className="text-right">{runButton('Run')}</p>}
    </li>
  )
}

/** Q11: + New task in a <details>; a 201 resets and closes it, an error keeps it open with the input. */
function NewTask({ projectId, onDone }) {
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  async function submit(event) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    setBusy(true)
    try {
      await createTask(projectId, { title: data.get('title'), description_md: data.get('description_md') })
      setError(null)
      form.reset()
      form.closest('details').open = false
      onDone()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <details className="relative">
      <summary className={`${button} list-none [&::-webkit-details-marker]:hidden`}>+ New task</summary>
      <form
        onSubmit={submit}
        className="absolute z-10 mt-2 grid w-96 max-w-[90vw] gap-2 rounded-md border border-line bg-surface p-3 shadow-lg"
      >
        <label className="grid gap-1">
          Title
          <input type="text" name="title" required pattern=".*\S.*" title="A title that isn't blank" className={field} />
        </label>
        <label className="grid gap-1">
          Description
          <textarea name="description_md" rows={4} placeholder="Markdown" className={field} />
        </label>
        <button disabled={busy} className={`${button} justify-self-start`}>
          Add task
        </button>
        {error && <ErrorMessage error={error} />}
      </form>
    </details>
  )
}

/** docs/ui.md §8 item 3, §8.1. */
export function BoardPage() {
  const { id } = useParams()
  // Q3: bumping `tick` gives usePoll a new load function, which restarts its loop with a fetch at once;
  // `tick` is in the deps for that alone
  const [tick, setTick] = useState(0)
  const refresh = useCallback(() => setTick((n) => n + 1), [])
  const load = useCallback(() => boardPage(id), [id, tick])
  const { data: page, error } = usePoll(load, 3000)
  const [actionError, setActionError] = useState(null)
  const dragged = useRef(null)
  const name = page?.project.name
  useEffect(() => {
    if (name) document.title = `${name} · Claude Factories`
  }, [name])

  // Q5: a 404 is always not-found; other errors replace the page only until the first good load
  if (error?.status === 404) return <NotFound detail={error.message} />
  if (!page) return error ? <ErrorMessage error={error} /> : <p className={muted}>Loading…</p>
  const { project } = page

  /** Q3, Q9: Run, Retry, Run next, and moves share the board's alert; a move refreshes even when refused. */
  async function boardAction(call, refreshOnError = false) {
    try {
      await call()
    } catch (err) {
      setActionError(err)
      if (refreshOnError) refresh()
      return
    }
    setActionError(null)
    refresh()
  }

  function dragStart(event, taskId) {
    dragged.current = taskId
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(taskId)) // Firefox starts no drag without data
  }

  // Q1: the gap is before the first card whose midpoint is below the pointer, else at the end
  function drop(event, status, cards) {
    const taskId = dragged.current
    if (taskId == null) return
    event.preventDefault()
    const rects = [...event.currentTarget.querySelectorAll('li')].map((li) => li.getBoundingClientRect())
    let i = rects.findIndex((r) => r.top + r.height / 2 > event.clientY)
    if (i < 0) i = cards.length
    const before = cards[i - 1]
    const after = cards[i]
    if (before?.id === taskId || after?.id === taskId) return // the gap next to itself: nothing moves
    // ponytail: midpoints at one spot run out of float precision after ~50 drops; renumber if that happens
    const position = before && after ? (before.position + after.position) / 2
      : before ? before.position + 1
      : after ? after.position - 1
      : 1
    boardAction(() => moveTask(taskId, status, position), true)
  }

  return (
    <>
      {/* 042: Code, Create factory, Import, Project context, and Move live on the project's other pages */}
      <ProjectHeader project={project} factory={page.factory}>
        <NewTask projectId={project.id} onDone={refresh} />
        <ActionButton action={() => boardAction(() => runNext(project.id))} disabled={!page.can_run}>
          Run next ▶
        </ActionButton>
        {page.hint && <p className={`basis-full text-sm ${muted}`}>{page.hint}</p>}
      </ProjectHeader>
      {error && <ErrorMessage error={error} />}
      {actionError && <ErrorMessage error={actionError} />}
      <div className="mt-2 grid items-start gap-4 md:grid-cols-4">
        {Object.entries(COLUMNS).map(([status, label]) => {
          const cards = page.columns[status] ?? []
          return (
            <section
              key={status}
              aria-labelledby={`column-${status}`}
              onDragOver={(event) => dragged.current != null && event.preventDefault()}
              onDrop={(event) => drop(event, status, cards)}
              className="grid min-h-32 content-start gap-2 rounded-lg bg-raised p-3"
            >
              <h2 id={`column-${status}`} className="m-0 text-base">
                {label} <span className={`font-normal ${muted}`}>{cards.length}</span>
              </h2>
              {cards.length ? (
                <ol className="grid gap-2">
                  {cards.map((card) => (
                    <Card
                      key={card.id}
                      card={card}
                      canRun={page.can_run}
                      onRun={(taskId) => boardAction(() => runTask(taskId))}
                      onDragStart={dragStart}
                      onDragEnd={() => (dragged.current = null)}
                    />
                  ))}
                </ol>
              ) : status === 'backlog' ? (
                <p className={`text-sm ${muted}`}>
                  No tasks. Add one with + New task, or run <code>fctl task add "title"</code> in the repo.
                </p>
              ) : (
                <p className={`text-sm ${muted}`}>No tasks</p>
              )}
            </section>
          )
        })}
      </div>
    </>
  )
}
