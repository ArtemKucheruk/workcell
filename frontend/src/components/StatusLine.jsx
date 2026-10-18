const LABELS = { backlog: 'Backlog', in_progress: 'In progress', review: 'Review', done: 'Done' }

/** 023 Q8: `<Status> · <stage>`, with human_review and escalated in task.html's words. Shared with the review page (024 Q9). */
export function StatusLine({ task }) {
  const label = LABELS[task.status] ?? task.status
  if (task.stage === 'escalated') {
    return (
      <span>
        {`${label} · `}
        <strong className="text-red-700 dark:text-red-400">⚠ NEEDS YOU — escalated</strong>
      </span>
    )
  }
  const stage = task.stage === 'human_review' ? 'waiting on you' : task.stage
  return <span>{stage ? `${label} · ${stage}` : label}</span>
}
