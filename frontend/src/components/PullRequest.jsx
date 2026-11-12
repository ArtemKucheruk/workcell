import { useEffect, useId, useState } from 'react'
import { createPr, mergePr, prState } from '../api/tasks.js'
import { ActionButton } from './ActionButton.jsx'
import { DeleteDialog } from './DeleteDialog.jsx'
import { ErrorMessage } from './ErrorMessage.jsx'
import { button, muted } from './styles.js'

/** 093 Q2: gh calls GitHub, so the PR's state is polled every 10 s, not the pages' 3 s. */
export const PR_POLL = 10000

// AC41: the state as text beside an icon; the color is never the only signal
const STATES = {
  OPEN: ['Open', '●', 'text-success'],
  MERGED: ['Merged', '✓', 'text-accent'],
  CLOSED: ['Closed', '✕', 'text-danger'],
}
const MERGE_HINT = { MERGED: 'Merged.', CLOSED: 'Closed on GitHub.' } // AC42; anything else is still loading

export const MERGE_TEXT =
  'This merges the PR on GitHub with a merge commit, fast-forwards main if that is safe, and deletes the worktree, ' +
  'the local branch, and the remote branch.'

/**
 * AC41: GET /pr on mount, then every PR_POLL ms while the state is OPEN or not yet known (a failure keeps polling);
 * it stops at MERGED or CLOSED. A new `tick` (after a merge) loads it again.
 */
function usePrState(id, url, tick) {
  const [found, setFound] = useState({ state: null, error: null })
  useEffect(() => {
    if (!url) return undefined
    let alive = true
    let timer
    const load = () =>
      prState(id).then(
        (state) => {
          if (!alive) return
          setFound({ state, error: null })
          if (state.state === 'OPEN') timer = setTimeout(load, PR_POLL)
        },
        (error) => {
          if (!alive) return
          setFound((old) => ({ ...old, error }))
          timer = setTimeout(load, PR_POLL)
        },
      )
    load()
    return () => {
      alive = false
      clearTimeout(timer)
    }
  }, [id, url, tick])
  return found
}

function checksText({ passed, failed, pending }) {
  return passed + failed + pending ? `checks: ${passed} passed, ${failed} failed, ${pending} pending` : 'no checks'
}

/**
 * 093: Create PR, or, once the task has a PR, its link, state, checks, and Merge PR (docs/ui.md §8 item 4, §8.2). `pr` is
 * the page's view-model field; `onChange` refetches the page. AC40: a refusal shows beside the buttons. AC43, AC44:
 * Merge PR confirms in the shared native dialog, where a refusal stays; a success lists the notes in a status region.
 */
export function PullRequest({ taskId, pr, onChange }) {
  const hintId = useId()
  const [error, setError] = useState(null)
  const [asking, setAsking] = useState(false)
  const [notes, setNotes] = useState(null)
  const [tick, setTick] = useState(0)
  const { state, error: stateError } = usePrState(taskId, pr.url, tick)

  async function create() {
    setError(null)
    try {
      await createPr(taskId)
    } catch (err) {
      setError(err)
      return
    }
    onChange()
  }

  const live = state?.state
  const shown = STATES[live]
  const mergeHint = live === 'OPEN' ? null : (MERGE_HINT[live] ?? 'Loading PR state…')
  const hint = pr.url ? mergeHint : pr.hint
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      {pr.url ? (
        <>
          <a href={pr.url} target="_blank" rel="noreferrer">
            {pr.number == null ? 'PR' : `PR #${pr.number}`}
            <span className="sr-only"> (opens in a new tab)</span>
          </a>
          {state && (
            <span className="text-sm">
              {shown ? (
                <>
                  <span aria-hidden="true" className={shown[2]}>
                    {shown[1]}
                  </span>{' '}
                  {shown[0]}
                </>
              ) : (
                live
              )}
              <span className={muted}>{` · ${checksText(state.checks)}`}</span>
            </span>
          )}
          {stateError && <span className="text-sm text-danger">{`PR state: ${stateError.message}`}</span>}
          <button
            type="button"
            onClick={() => setAsking(true)}
            disabled={live !== 'OPEN'}
            aria-describedby={hint ? hintId : undefined}
            className={button}
          >
            Merge PR
          </button>
        </>
      ) : (
        <ActionButton action={create} disabled={!pr.can_create} aria-describedby={hint ? hintId : undefined}>
          Create PR
        </ActionButton>
      )}
      {hint && (
        <span id={hintId} className={`text-sm ${muted}`}>
          {hint}
        </span>
      )}
      {error && <ErrorMessage error={error} />}
      <div role="status" className={notes ? 'basis-full text-sm' : 'sr-only'}>
        {notes && (
          <ul className="list-disc pl-5">
            {notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        )}
      </div>
      {asking && (
        <DeleteDialog
          title={`Merge PR #${pr.number}?`}
          text={MERGE_TEXT}
          confirmLabel="Merge PR"
          remove={async () => setNotes((await mergePr(taskId)).notes)}
          onDeleted={() => {
            setTick((n) => n + 1)
            onChange()
          }}
          onClose={() => setAsking(false)}
        />
      )}
    </div>
  )
}
