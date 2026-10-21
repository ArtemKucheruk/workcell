import { useEffect, useId, useRef, useState } from 'react'
import { ActionButton } from './ActionButton.jsx'
import { ErrorMessage } from './ErrorMessage.jsx'
import { button, danger, section } from './styles.js'

/** 049 Q12: what each delete removes, and what stays. */
export const PROJECT_TEXT =
  'This removes its tasks, with their runs, rounds and their files, verdicts, comments, decisions, status history, and ' +
  'transcript records, from the app. The repo, its worktrees and branches, run logs, and copied transcript files stay on disk.'
export const WORKSPACE_TEXT = 'This removes the workspace from the app. It must hold no projects: move or delete them first.'

/**
 * 049 FE11–FE15, Q11, Q12: a modal confirm, shown through showModal as it mounts, so Cancel, first, takes focus.
 * `remove` is the delete call; a refusal shows inside and the dialog stays. On success it closes, then `onDeleted`
 * runs (a navigation). `onClose` follows every close, Cancel and Esc included, so the opener can unmount it.
 */
export function DeleteDialog({ title, text, remove, onDeleted, onClose }) {
  const id = useId()
  const dialog = useRef(null)
  const [error, setError] = useState(null)

  // StrictMode runs this twice; showModal on an open dialog throws in older browsers
  useEffect(() => {
    if (!dialog.current.open) dialog.current.showModal()
  }, [])

  async function confirm() {
    setError(null)
    try {
      await remove()
    } catch (err) {
      setError(err)
      return
    }
    dialog.current.close('deleted')
    onDeleted()
  }

  // 048 Q8: centered (preflight drops the UA's auto margin), on the drawer's backdrop
  return (
    <dialog
      ref={dialog}
      aria-labelledby={`${id}-title`}
      aria-describedby={`${id}-text`}
      onClose={(event) => {
        // React passes a dialog's close up the tree: inside the drawer it would also run the drawer's onClose
        event.stopPropagation()
        onClose(event.currentTarget.returnValue === 'deleted')
      }}
      className="m-auto w-md max-w-[90vw] rounded-lg border border-line bg-surface p-5 text-left text-base font-normal text-fg shadow-xl backdrop:bg-surface/80"
    >
      <div className="grid gap-3">
        <h2 id={`${id}-title`} className="m-0 wrap-anywhere">
          {title}
        </h2>
        <p id={`${id}-text`}>{text}</p>
        {error && <ErrorMessage error={error} />}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={() => dialog.current.close()} className={button}>
            Cancel
          </button>
          <ActionButton action={confirm} className={danger}>
            Delete
          </ActionButton>
        </div>
      </div>
    </dialog>
  )
}

/** 049 FE19, FE23: a settings page's last section; its button opens the delete dialog. */
export function DangerZone({ label, summary, ...dialog }) {
  const id = useId()
  const [asking, setAsking] = useState(false)
  return (
    <section aria-labelledby={id} className={section}>
      <h2 id={id} className="m-0">
        Danger zone
      </h2>
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-danger p-4">
        <p>{summary}</p>
        <button type="button" onClick={() => setAsking(true)} className={danger}>
          {label}
        </button>
      </div>
      {asking && <DeleteDialog {...dialog} onClose={() => setAsking(false)} />}
    </section>
  )
}
