import { muted } from './styles.js'

/** 043: the one set of status labels, in the board's column order (Q9). */
export const LABELS = { backlog: 'Backlog', in_progress: 'In progress', review: 'Review', done: 'Done' }

// Q3: every class written out in full, for Tailwind's scanner. The border sits on filled pills too, so all pills are one height.
const pill = 'inline-flex items-center gap-1 rounded-full border px-2 text-xs/5 font-medium whitespace-nowrap'
const TONE = {
  backlog: 'border-muted text-muted',
  in_progress: 'border-accent text-accent',
  review: 'border-warning text-warning',
  done: 'border-success text-success',
}

/** Q3: a status is an outlined pill in its token; an unknown one shows as it is, muted. */
export function StatusPill({ status }) {
  return <span className={`${pill} ${TONE[status] ?? TONE.backlog}`}>{LABELS[status] ?? status}</span>
}

/** Q1, Q3: the two states that wait on me are filled, with the surface color as text. */
export const WaitingPill = () => <span className={`${pill} border-warning bg-warning text-surface`}>waiting on you</span>
export const EscalatedPill = () => <span className={`${pill} border-danger bg-danger text-surface`}>escalated</span>

/** 056 Q11: the Claude account runs use, on Settings; outlined accent like the other state pills. */
export const ActivePill = () => <span className={`${pill} border-accent text-accent`}>active</span>

/** 057: the Context page's first card, which can't be moved or deleted; a fact, not a state, so muted. */
export const PinnedPill = () => <span className={`${pill} border-muted text-muted`}>Pinned</span>

/** Q4: a kind of In progress, so accent. The dot pulses only when the system allows motion. */
export function RunningBadge() {
  return (
    <span className={`${pill} border-accent text-accent`}>
      <span aria-hidden="true" className="motion-safe:animate-pulse">●</span>
      {' running'}
    </span>
  )
}

/** Q6: human_review and escalated as their pills, any other stage as muted text, null as nothing. */
export function Stage({ stage }) {
  if (stage === 'human_review') return <WaitingPill />
  if (stage === 'escalated') return <EscalatedPill />
  return stage ? <span className={muted}>{stage}</span> : null
}

/** Q6: the status pill, then the stage; replaces 023's StatusLine on the task and review headers and the dashboard. */
export function TaskState({ task }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <StatusPill status={task.status} />
      {task.stage && ' '}
      <Stage stage={task.stage} />
    </span>
  )
}
