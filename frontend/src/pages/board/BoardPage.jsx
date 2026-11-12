import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { Link, useParams } from 'react-router'
import { boardPage } from '../../api/pages.js'
import { runNext, runTask } from '../../api/runs.js'
import { createTask, deleteTask, editTask, moveTask } from '../../api/tasks.js'
import { ActionButton } from '../../components/ActionButton.jsx'
import { LABELS, RunningBadge, Stage } from '../../components/Badge.jsx'
import { Chip } from '../../components/Chip.jsx'
import { ErrorMessage, OfflineBanner } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { ProjectHeader } from '../../components/ProjectHeader.jsx'
import { Block, ButtonBlock, ProjectHeaderSkeleton, Skeleton } from '../../components/Skeleton.jsx'
import { button, danger, field, muted, popover, smallButton } from '../../components/styles.js'
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

/** 094: a padlock, drawn in currentColor; the text beside it carries the meaning. */
function LockIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" fill="currentColor" className="mt-0.5 size-3.5 shrink-0">
      <path d="M5 7V5a3 3 0 0 1 6 0v2h.5A1.5 1.5 0 0 1 13 8.5v5a1.5 1.5 0 0 1-1.5 1.5h-7A1.5 1.5 0 0 1 3 13.5v-5A1.5 1.5 0 0 1 4.5 7H5Zm1.5 0h3V5a1.5 1.5 0 0 0-3 0v2Z" />
    </svg>
  )
}

/**
 * 094 AC22, AC23, Q7: a lock and `Blocked by #12, #14`, naming the blockers that aren't done. Each id links to its task;
 * its `<title> · <Status>` is the link's description, always in the DOM, and shown above it on hover or focus. It
 * appears at once, never animated, so reduced motion needs nothing more.
 */
function Blocked({ card }) {
  const open = card.blocked_by.filter((b) => b.status !== 'done')
  return (
    <p className={`flex items-start gap-1.5 text-sm ${muted}`}>
      <LockIcon />
      <span>
        {'Blocked by '}
        {open.map((b, i) => (
          <Fragment key={b.id}>
            {i > 0 && ', '}
            <span className="group relative">
              <Link to={`/tasks/${b.id}`} draggable="false" aria-describedby={`blocker-${card.id}-${b.id}`}>
                {`#${b.id}`}
              </Link>
              <span
                id={`blocker-${card.id}-${b.id}`}
                role="tooltip"
                className="pointer-events-none invisible absolute bottom-full left-0 z-10 mb-1 w-max max-w-60 rounded-md border border-line bg-surface px-2 py-1 text-xs text-fg shadow-md group-focus-within:visible group-hover:visible"
              >
                {`${b.title} · ${LABELS[b.status] ?? b.status}`}
              </span>
            </span>
          </Fragment>
        ))}
      </span>
    </p>
  )
}

// Q9: tokens only, each class in full for Tailwind's scanner. Hover darkens the ring; keyboard focus on the card's link or a
// button in it (its Move menu too) thickens it in accent; the dragged card dims, fading (046 Q8). The drop line is the marked card's ::before
// (the gap above it) or ::after (the gap below the last card), absolute in the 8 px gap, so it takes no room (FE6).
// 094 Q6: the background and shadow are the Card's, so a blocked card can sit flat on the column's raised color instead
const cardLook = [
  'relative grid cursor-grab gap-1 rounded-md p-3 ring-1 ring-line hover:shadow-md hover:ring-muted',
  'has-focus-visible:ring-2 has-focus-visible:ring-accent data-dragging:opacity-50 motion-safe:transition-opacity',
  'data-[drop=before]:before:absolute data-[drop=before]:before:inset-x-0 data-[drop=before]:before:-top-1.25 data-[drop=before]:before:h-0.5 data-[drop=before]:before:bg-accent',
  'data-[drop=after]:after:absolute data-[drop=after]:after:inset-x-0 data-[drop=after]:after:-bottom-1.25 data-[drop=after]:after:h-0.5 data-[drop=after]:after:bg-accent',
].join(' ')

/**
 * Q4: a native popover of plain buttons; each hides it natively as it's chosen (FE10). `nudges` are Up and Down.
 * 048 FE1, FE12: then a divider, Edit, and Delete, which a running card disables (Q10).
 */
function MoveMenu({ card, moves, nudges, running, onEdit, onDelete }) {
  const id = `move-${card.id}`
  const item = (label, pick, { className = '', ...more } = {}) => (
    <button
      key={label}
      type="button"
      popoverTarget={id}
      popoverTargetAction="hide"
      onClick={pick}
      className={`cursor-pointer rounded px-2 py-1 text-left text-sm enabled:hover:bg-raised disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      {...more}
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
        <hr className="my-1 border-line" />
        {item('Edit', () => onEdit(card))}
        {item('Delete', () => onDelete(card), {
          disabled: running,
          title: running ? 'Stop the run to delete this task' : undefined,
          className: 'text-danger',
        })}
      </div>
    </>
  )
}

function Card({ card, canRun, runTitle, onRun, moves, nudges, onEdit, onDelete, dragging, drop, onDragStart, onDragEnd }) {
  const running = card.status === 'in_progress' && card.run?.status === 'running'
  // 094 Q6: every column but Done; the text keeps its tokens, which clear 4.5:1 on raised. Q10: Run stays enabled
  const blocked = card.blocked && card.status !== 'done'
  const runButton = (label) => (
    <ActionButton
      action={() => onRun(card.id)}
      disabled={!canRun}
      title={runTitle}
      className={smallButton}
      aria-describedby={`task-${card.id}`}
    >
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
      className={`${cardLook} ${blocked ? 'bg-raised' : 'bg-surface shadow-sm'} ${card.escalated ? 'border-l-4 border-danger' : ''}`}
    >
      <Link id={`task-${card.id}`} to={`/tasks/${card.id}`} draggable="false" className="font-medium">
        {`#${card.id} ${card.title}`}
      </Link>
      {blocked && <Blocked card={card} />}
      <StatusLine card={card} running={running} retry={runButton('Retry')} />
      <Rounds card={card} />
      {running && card.started_at && (
        <p className={`text-sm ${muted}`}>
          started <Time iso={card.started_at} relative />
        </p>
      )}
      <div className="flex justify-end gap-2">
        <MoveMenu card={card} moves={moves} nudges={nudges} running={running} onEdit={onEdit} onDelete={onDelete} />
        {card.status === 'backlog' && runButton('Run')}
      </div>
    </li>
  )
}

/** The selector of card `id`'s Move button, not its menu's items. */
const moveButton = (id) => `[popovertarget="move-${id}"]:not([popovertargetaction])`

/**
 * Q10, Q11: the + New task form; a success resets and hides its popover, an error keeps it open with the input.
 * 048 Q5, Q6: given `card`, the same form edits it: labelled `Edit #id`, filled from the card, and sent with Save.
 * The inputs are uncontrolled, so a poll never refills them (FE6). `onDone` gets the title as stored, trimmed.
 */
function TaskForm({ projectId, card, onDone }) {
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  async function submit(event) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    const fields = { title: data.get('title'), description_md: data.get('description_md') }
    setBusy(true)
    try {
      await (card ? editTask(card.id, fields) : createTask(projectId, fields))
      setError(null)
      form.reset()
      form.closest('[popover]').hidePopover?.() // Q12: jsdom has no Popover API
      onDone(fields.title.trim())
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={submit} aria-labelledby={card ? 'task-form-label' : undefined} className="grid gap-2">
      {card && <p id="task-form-label" className={`text-xs ${muted}`}>{`Edit #${card.id}`}</p>}
      <label className="grid gap-1">
        Title
        <input
          // Q10: the autofocus attribute, which the popover focuses as it opens; React's autoFocus only focuses on mount
          ref={(el) => el?.setAttribute('autofocus', '')}
          type="text"
          name="title"
          defaultValue={card?.title}
          required
          pattern=".*\S.*"
          title="A title that isn't blank"
          className={field}
        />
      </label>
      <label className="grid gap-1">
        Description
        <textarea name="description_md" defaultValue={card?.description_md} rows={4} placeholder="Markdown" className={field} />
      </label>
      <button disabled={busy} className={`${button} justify-self-start`}>
        {card ? 'Save' : 'Add task'}
      </button>
      {error && <ErrorMessage error={error} />}
    </form>
  )
}

/**
 * Q10: + New task opens the form in a native popover. 048 Q6: `editing` is the card Edit was chosen on, as it was then;
 * the form remounts, empty or filled, only when that changes. + New task always opens it empty, even over an open Edit.
 * Q9: closed by Esc or a click outside with focus lost (on body or in the hidden popover), focus goes to the card's
 * Move button for an Edit, else to + New task. The browser does that itself only for a popover its invoker opened, and
 * + New task over an Edit cancels that invoker (round-1 review-ui).
 */
function NewTask({ projectId, editing, setEditing, onCreated, onSaved }) {
  function create(event) {
    if (!editing) return
    event.preventDefault() // the popover is open on the Edit: keep it open, in create mode
    flushSync(() => setEditing(null))
    document.querySelector('#new-task [name="title"]').focus()
  }
  function toggled(event) {
    if (event.newState !== 'closed') return
    const lost = document.activeElement
    if (!lost || lost === document.body || event.currentTarget.contains(lost)) {
      document.querySelector(editing ? moveButton(editing.id) : '[popovertarget="new-task"]')?.focus()
    }
    if (editing) setEditing(null)
  }
  return (
    <>
      <button type="button" popoverTarget="new-task" onClick={create} className={`${button} [anchor-name:--new-task]`}>
        + New task
      </button>
      <div
        id="new-task"
        popover="auto"
        onToggle={toggled}
        className={`${popover} w-96 max-w-[90vw] p-3 [position-anchor:--new-task] [position-area:bottom_span-right]`}
      >
        <TaskForm
          key={editing ? `edit-${editing.id}` : 'new'}
          projectId={projectId}
          card={editing}
          onDone={editing ? (title) => onSaved(editing, title) : onCreated}
        />
      </div>
    </>
  )
}

/** 048 FE8, FE9, FE11, Q8: the delete dialog's body; a refusal shows inside it, which stays open. */
function DeleteTask({ card, onCancel, onDeleted }) {
  const [error, setError] = useState(null)
  async function remove() {
    setError(null)
    try {
      await deleteTask(card.id)
    } catch (err) {
      setError(err)
      return
    }
    onDeleted(card)
  }
  return (
    <div className="grid gap-3">
      <h2 id="delete-task" className="m-0">{`Delete #${card.id} ${card.title}?`}</h2>
      <p id="delete-task-text">
        This removes its runs, rounds and their files, verdicts, comments, decisions, status history, and transcript records
        from the app. Its worktree, branch, run logs, and copied transcript files stay on disk.
      </p>
      {error && <ErrorMessage error={error} />}
      {/* Cancel first, so showModal focuses it */}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} className={button}>
          Cancel
        </button>
        <ActionButton action={remove} className={danger}>
          Delete
        </ActionButton>
      </div>
    </div>
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

/** 046 Q5, FE16: the header with + New task and Run next, then the four columns at an empty column's height. */
function BoardSkeleton() {
  return (
    <Skeleton>
      <ProjectHeaderSkeleton>
        <ButtonBlock className="w-28" />
        <ButtonBlock className="w-28" />
      </ProjectHeaderSkeleton>
      <div className="mt-2 grid items-start gap-4 md:grid-cols-4">
        {Object.keys(LABELS).map((status) => (
          <div key={status} className="grid min-h-32 content-start rounded-lg bg-raised p-3">
            <Block className="h-6 w-28" />
          </div>
        ))}
      </div>
    </Skeleton>
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
  const [said, setSaid] = useState('') // Q5: the status region's words
  // `dragged` is the card and its column, read by drop; `drag` is what renders: the card's id, `dim`, and the column and gap
  // under the pointer (`over`, `gap`)
  const dragged = useRef(null)
  const [drag, setDrag] = useState(null)
  const refocus = useRef(null)
  const [editing, setEditing] = useState(null) // 048: the card the + New task form edits, else null
  const [doomed, setDoomed] = useState(null) // 048: the card the delete dialog is about
  const dialog = useRef(null)
  const name = page?.project.name
  useEffect(() => {
    if (name) document.title = `${name} · Claude Factories`
  }, [name])
  // Q6: after a menu move's reload, focus the card's Move button, in its new column or in place
  useEffect(() => {
    if (refocus.current == null) return
    document.querySelector(moveButton(refocus.current))?.focus()
    refocus.current = null
  }, [page])

  // Q5: a 404 is always not-found; other errors replace the page only until the first good load, then show as the
  // offline banner (046 Q4)
  if (error?.status === 404) return <NotFound detail={error.message} />
  if (!page) return error ? <ErrorMessage error={error} /> : <BoardSkeleton />
  const { project } = page
  // 096 Q9: at or over the run cap, one muted header line and the same text as the title of every disabled Run
  const capHint =
    page.runs_active >= page.max_concurrent_runs ? `${page.runs_active} of ${page.max_concurrent_runs} runs active` : undefined

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

  // 048 Q7: Edit and Delete leave the board alert alone; their refusals show in the form or dialog, their successes here

  /** FE2: the form renders in edit mode before the popover shows, so its autofocus lands on the card's Title. */
  function edit(card) {
    flushSync(() => setEditing(card))
    document.getElementById('new-task').showPopover()
  }

  /** FE3, FE4: the form has hidden itself; announce, reload, and give focus back to the card's Move button. */
  function saved(card, title) {
    setEditing(null)
    setSaid(`Saved #${card.id} ${title}.`)
    refocus.current = card.id
    refresh()
  }

  /** FE8: the dialog's body renders before showModal, which then focuses its first button, Cancel. */
  function askDelete(card) {
    flushSync(() => setDoomed(card))
    dialog.current.returnValue = ''
    dialog.current.showModal()
  }

  function deleted(card) {
    setSaid(`Deleted #${card.id} ${card.title}.`)
    dialog.current.close('deleted')
    refresh()
  }

  /** FE9, FE10, Q9: Cancel, Esc, or a delete closed it: focus goes to + New task once the card is gone, else to its Move button. */
  function deleteClosed(event) {
    const gone = event.currentTarget.returnValue === 'deleted'
    document.querySelector(gone ? '[popovertarget="new-task"]' : moveButton(doomed.id))?.focus()
    setDoomed(null)
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
        <NewTask projectId={project.id} editing={editing} setEditing={setEditing} onCreated={refresh} onSaved={saved} />
        <ActionButton action={() => boardAction(() => runNext(project.id))} disabled={!page.can_run} title={capHint}>
          Run next ▶
        </ActionButton>
        {page.hint && <p className={`basis-full text-sm ${muted}`}>{page.hint}</p>}
        {capHint && <p className={`basis-full text-sm ${muted}`}>{capHint}</p>}
        {/* 058 FE5, FE6: the last automatic sync's refusal, muted like the hint and not an alert: polls repeat it */}
        {page.factory_error && <p className={`basis-full text-sm ${muted}`}>{`factory/: ${page.factory_error}`}</p>}
      </ProjectHeader>
      {error && <OfflineBanner />}
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
                      runTitle={capHint}
                      onRun={(taskId) => boardAction(() => runTask(taskId))}
                      {...menu(card, status, cards)}
                      onEdit={edit}
                      onDelete={askDelete}
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
      {/* 048 Q8: centered (preflight drops the UA's auto margin), on the drawer's backdrop */}
      <dialog
        ref={dialog}
        aria-labelledby="delete-task"
        aria-describedby="delete-task-text"
        onClose={deleteClosed}
        className="m-auto w-md max-w-[90vw] rounded-lg border border-line bg-surface p-5 text-fg shadow-xl backdrop:bg-surface/80"
      >
        {doomed && <DeleteTask card={doomed} onCancel={() => dialog.current.close()} onDeleted={deleted} />}
      </dialog>
    </>
  )
}
