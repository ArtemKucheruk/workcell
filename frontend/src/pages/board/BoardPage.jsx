import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router'
import { boardPage } from '../../api/pages.js'
import { runNext, runTask } from '../../api/runs.js'
import { createTask, moveTask } from '../../api/tasks.js'
import { ActionButton } from '../../components/ActionButton.jsx'
import { LABELS, RunningBadge, Stage } from '../../components/Badge.jsx'
import { Chip } from '../../components/Chip.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { ProjectHeader } from '../../components/ProjectHeader.jsx'
import { button, field, muted, smallButton } from '../../components/styles.js'
import { Time } from '../../components/Time.jsx'
import { usePoll } from '../../hooks/usePoll.js'

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`

/**
 * §8.1: running (the badge, then the stage), else stalled with Retry, else the stage's pill or muted text.
 * 043 Q5: no status pill, since the column names it; dto/pages.py's `waiting` and `escalated` are exactly those stages.
 */
function StatusLine({ card, running, retry }) {
  if (card.stalled) {
    return (
      <p className="flex items-center justify-between gap-2 text-sm">
        <span><strong>stalled</strong>{card.stage && ` · ${card.stage}`}</span>
        {retry}
      </p>
    )
  }
  if (!running && !card.stage) return null
  return (
    <p className="flex flex-wrap items-center gap-1.5 text-sm">
      {running && <RunningBadge />}
      {running && card.stage && ' '}
      <Stage stage={card.stage} />
    </p>
  )
}

/** 043 Q2: `r2` then the shared chips, in a wrapping row, then `+A −D`. Done cards show their rounds. */
function Rounds({ card }) {
  if (card.round == null) return null
  if (card.status === 'done') return <p className={`text-sm ${muted}`}>{plural(card.round, 'round')}</p>
  return (
    <>
      <p className="flex flex-wrap gap-x-2 text-sm">
        <span className={muted}>{`r${card.round}`}</span>
        {Object.entries(card.verdicts ?? {}).map(([who, verdict]) => (
          <Fragment key={who}>
            {' '}
            <Chip n={card.round} who={who} verdict={verdict} />
          </Fragment>
        ))}
      </p>
      <p className={`text-sm tabular-nums ${muted}`}>{`+${card.additions} −${card.deletions}`}</p>
    </>
  )
}

// Q9: tokens only, each class in full for Tailwind's scanner. Hover darkens the ring; keyboard focus on the card's link or a
// button in it (its Move menu too) thickens it in accent; the dragged card dims. The drop line is the marked card's ::before
// (the gap above it) or ::after (the gap below the last card), absolute in the 8 px gap, so it takes no room (FE6).
const cardLook = [
  'relative grid cursor-grab gap-1 rounded-md bg-surface p-3 shadow-sm ring-1 ring-line hover:shadow-md hover:ring-muted',
  'has-focus-visible:ring-2 has-focus-visible:ring-accent data-dragging:opacity-50',
  'data-[drop=before]:before:absolute data-[drop=before]:before:inset-x-0 data-[drop=before]:before:-top-1.25 data-[drop=before]:before:h-0.5 data-[drop=before]:before:bg-accent',
  'data-[drop=after]:after:absolute data-[drop=after]:after:inset-x-0 data-[drop=after]:after:-bottom-1.25 data-[drop=after]:after:h-0.5 data-[drop=after]:after:bg-accent',
].join(' ')

// Q10: below its button where the browser has anchor positioning, flipped when it would leave the viewport; else the UA's
// centered placement, which needs m-auto back after preflight's margin reset
const popover = [
  'm-auto rounded-md border border-line bg-surface text-fg shadow-lg',
  'supports-[position-area:bottom]:m-0 supports-[position-area:bottom]:mt-1 [position-try-fallbacks:flip-block,flip-inline]',
].join(' ')

/** Q4: a native popover of plain buttons; each hides it natively as it's chosen (FE10). `nudges` are Up and Down. */
function MoveMenu({ card, moves, nudges }) {
  const id = `move-${card.id}`
  const item = (label, pick) => (
    <button
      key={label}
      type="button"
      popoverTarget={id}
      popoverTargetAction="hide"
      onClick={pick}
      className="cursor-pointer rounded px-2 py-1 text-left text-sm hover:bg-raised"
    >
      {label}
    </button>
  )
  return (
    <>
      {/* ponytail: an inline anchor name per card; `anchor-scope` would let one static class do it once it's widely supported */}
      <button
        type="button"
        popoverTarget={id}
        aria-describedby={`task-${card.id}`}
        style={{ anchorName: `--${id}` }}
        className={smallButton}
      >
        Move
      </button>
      <div
        id={id}
        popover="auto"
        style={{ positionAnchor: `--${id}` }}
        className={`${popover} w-44 cursor-default p-1 open:grid [position-area:bottom_span-left]`}
      >
        <p className={`px-2 py-1 text-xs ${muted}`}>{`Move #${card.id}`}</p>
        {moves.map(([label, pick]) => item(label, pick))}
        {nudges.length > 0 && <hr className="my-1 border-line" />}
        {nudges.map(([label, pick]) => item(label, pick))}
      </div>
    </>
  )
}

function Card({ card, canRun, onRun, moves, nudges, dragging, drop, onDragStart, onDragEnd }) {
  const running = card.status === 'in_progress' && card.run?.status === 'running'
  const runButton = (label) => (
    <ActionButton action={() => onRun(card.id)} disabled={!canRun} className={smallButton} aria-describedby={`task-${card.id}`}>
      {label}
    </ActionButton>
  )
  return (
    <li
      draggable="true"
      data-dragging={dragging || undefined}
      data-drop={drop}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      // 040: a space before ${, or Tailwind's scanner reads `ring-line$` and generates no ring-line
      className={`${cardLook} ${card.escalated ? 'border-l-4 border-danger' : ''}`}
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
      <div className="flex justify-end gap-2">
        <MoveMenu card={card} moves={moves} nudges={nudges} />
        {card.status === 'backlog' && runButton('Run')}
      </div>
    </li>
  )
}

/** Q10, Q11: + New task opens its form in a popover; a 201 resets and hides it, an error keeps it open with the input. */
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
      form.closest('[popover]').hidePopover?.() // Q12: jsdom has no Popover API
      onDone()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <button type="button" popoverTarget="new-task" className={`${button} [anchor-name:--new-task]`}>
        + New task
      </button>
      <div
        id="new-task"
        popover="auto"
        className={`${popover} w-96 max-w-[90vw] p-3 [position-anchor:--new-task] [position-area:bottom_span-right]`}
      >
        <form onSubmit={submit} className="grid gap-2">
          <label className="grid gap-1">
            Title
            <input
              // Q10: the autofocus attribute, which the popover focuses as it opens; React's autoFocus only focuses on mount
              ref={(el) => el?.setAttribute('autofocus', '')}
              type="text"
              name="title"
              required
              pattern=".*\S.*"
              title="A title that isn't blank"
              className={field}
            />
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
      </div>
    </>
  )
}

/** Q1: the gap before the first card whose midpoint is below the pointer, else after the last. Reads only the cards (FE7). */
function gapAt(event) {
  const cards = [...event.currentTarget.querySelectorAll('ol > li')]
  const i = cards.findIndex((li) => {
    const r = li.getBoundingClientRect()
    return r.top + r.height / 2 > event.clientY
  })
  return i < 0 ? cards.length : i
}

/** Q1: the position for gap `i` in `cards`, or null when the gap is next to card `taskId` itself, so nothing would move. */
function position(cards, i, taskId) {
  const before = cards[i - 1]
  const after = cards[i]
  if (before?.id === taskId || after?.id === taskId) return null
  // ponytail: midpoints at one spot run out of float precision after ~50 drops; renumber if that happens
  return before && after ? (before.position + after.position) / 2
    : before ? before.position + 1
    : after ? after.position - 1
    : 1
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
  const [said, setSaid] = useState('') // Q5: the status region's words
  // `dragged` is the card and its column, read by drop; `drag` is what renders: the card's id, `dim`, and the column and gap
  // under the pointer (`over`, `gap`)
  const dragged = useRef(null)
  const [drag, setDrag] = useState(null)
  const refocus = useRef(null)
  const name = page?.project.name
  useEffect(() => {
    if (name) document.title = `${name} · Claude Factories`
  }, [name])
  // Q6: after a menu move's reload, focus the card's Move button, in its new column or in place
  useEffect(() => {
    if (refocus.current == null) return
    document.querySelector(`[popovertarget="move-${refocus.current}"]:not([popovertargetaction])`)?.focus()
    refocus.current = null
  }, [page])

  // Q5: a 404 is always not-found; other errors replace the page only until the first good load
  if (error?.status === 404) return <NotFound detail={error.message} />
  if (!page) return error ? <ErrorMessage error={error} /> : <p className={muted}>Loading…</p>
  const { project } = page

  /**
   * Q1, Q3, Q9: Run, Retry, Run next, and moves share the board's alert. Starting one empties the alert and the status
   * region at once; a refusal fills the alert, a success the status region (Q5). A move reloads even when refused, and a
   * menu move then gets its focus back (Q6).
   */
  async function boardAction(call, { said = '', reload = false, focus = null } = {}) {
    setActionError(null)
    setSaid('')
    let ok = true
    try {
      await call()
    } catch (err) {
      ok = false
      setActionError(err)
    }
    if (ok) setSaid(said)
    if (!ok && !reload) return
    refocus.current = focus
    refresh()
  }

  /** The one move path, for drops and the Move menu: `Moved #3 Task 3 <words>.` */
  function move(card, status, at, words, focus = null) {
    boardAction(() => moveTask(card.id, status, at), { said: `Moved #${card.id} ${card.title} ${words}.`, reload: true, focus })
  }

  /** FE9: the other columns, each to its bottom (Q2); in Backlog, Up and Down one place, at the midpoint rule's position (Q3). */
  function menu(card, from, cards) {
    const moves = Object.entries(LABELS)
      .filter(([status]) => status !== from)
      .map(([status, label]) => {
        const there = page.columns[status] ?? []
        return [label, () => move(card, status, position(there, there.length, card.id), `to ${label}`, card.id)]
      })
    const k = cards.indexOf(card)
    const nudges = []
    if (from === 'backlog' && k > 0) nudges.push(['Up', () => move(card, from, position(cards, k - 1, card.id), 'up', card.id)])
    if (from === 'backlog' && k < cards.length - 1) {
      nudges.push(['Down', () => move(card, from, position(cards, k + 2, card.id), 'down', card.id)])
    }
    return { moves, nudges }
  }

  function dragStart(event, card, from) {
    dragged.current = { card, from }
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(card.id)) // Firefox starts no drag without data
    setDrag({ id: card.id })
    // Q9: dim after this event, once the browser has taken the drag image, so the image isn't dimmed too
    setTimeout(() => setDrag((d) => (d?.id === card.id ? { ...d, dim: true } : d)))
  }

  function dragOver(event, status) {
    if (dragged.current == null) return
    event.preventDefault()
    const gap = gapAt(event)
    setDrag((d) => (d?.over === status && d.gap === gap ? d : { ...d, over: status, gap })) // re-render only when the gap changes
  }

  // FE3: leaving the column, not moving between its children; relatedTarget is null when the pointer leaves the window
  function dragLeave(event) {
    if (!event.currentTarget.contains(event.relatedTarget)) setDrag((d) => d && { ...d, over: null })
  }

  function drop(event, status, cards) {
    if (dragged.current == null) return
    event.preventDefault()
    setDrag(null)
    const { card, from } = dragged.current
    const at = position(cards, gapAt(event), card.id)
    if (at != null) move(card, status, at, `${from === status ? 'within' : 'to'} ${LABELS[status]}`)
  }

  function dragEnd() {
    dragged.current = null
    setDrag(null)
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
      <p role="status" className="sr-only">
        {said}
      </p>
      <div className="mt-2 grid items-start gap-4 md:grid-cols-4">
        {Object.entries(LABELS).map(([status, label]) => {
          const cards = page.columns[status] ?? []
          // FE4, FE5: the gap under the pointer gets a line only where a drop would move the card
          const over = drag?.over === status
          const gap = over && position(cards, drag.gap, drag.id) != null ? drag.gap : null
          return (
            <section
              key={status}
              aria-labelledby={`column-${status}`}
              data-over={over || undefined}
              onDragOver={(event) => dragOver(event, status)}
              onDragLeave={dragLeave}
              onDrop={(event) => drop(event, status, cards)}
              className="grid min-h-32 content-start gap-2 rounded-lg bg-raised p-3 data-over:ring-2 data-over:ring-accent"
            >
              <h2 id={`column-${status}`} className="m-0 text-base">
                {label} <span className={`font-normal ${muted}`}>{cards.length}</span>
              </h2>
              {cards.length ? (
                // Q8: from md up the list scrolls under its heading. 12rem is main's padding, the header with its hint, and
                // the column's heading; -m/p give the rings and the drop line room inside the scroller, which would clip them
                <ol className="-m-1.5 grid gap-2 p-1.5 md:max-h-[calc(100dvh-12rem)] md:overflow-y-auto">
                  {cards.map((card, i) => (
                    <Card
                      key={card.id}
                      card={card}
                      canRun={page.can_run}
                      onRun={(taskId) => boardAction(() => runTask(taskId))}
                      {...menu(card, status, cards)}
                      dragging={drag?.dim && drag.id === card.id}
                      drop={i === gap ? 'before' : gap === cards.length && i === gap - 1 ? 'after' : undefined}
                      onDragStart={(event) => dragStart(event, card, status)}
                      onDragEnd={dragEnd}
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
