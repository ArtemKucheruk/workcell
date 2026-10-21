import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { addFactory, deleteFactory, listFactories, saveFactory } from '../../api/factories.js'
import { boardPage } from '../../api/pages.js'
import { DeleteDialog } from '../../components/DeleteDialog.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { ProjectHeader } from '../../components/ProjectHeader.jsx'
import { Rename } from '../../components/Rename.jsx'
import { Block, ButtonBlock, ProjectHeaderSkeleton, Skeleton } from '../../components/Skeleton.jsx'
import { Time } from '../../components/Time.jsx'
import { button, field, muted, popover, smallButton } from '../../components/styles.js'
import { usePoll } from '../../hooks/usePoll.js'

/** Q16: what Delete removes, and what stays. */
const DELETE_TEXT =
  "This removes the factory's design from the app. Files in the repo, such as the ones Create factory wrote, stay."

const NEW = 'new-factory'

/**
 * FE3, Q15: + New factory's native popover, like + New task. The server judges the name (blank, taken), and its refusal
 * shows inside, which stays open with what was typed; a 201 opens the designer.
 */
function NewFactory({ projectId }) {
  const navigate = useNavigate()
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    try {
      const made = await addFactory(projectId, new FormData(event.currentTarget).get('name'))
      navigate(`/projects/${projectId}/factories/${made.id}`)
    } catch (err) {
      setError(err)
      setBusy(false)
    }
  }
  return (
    <>
      <button type="button" popoverTarget={NEW} className={`${button} [anchor-name:--new-factory]`}>
        + New factory
      </button>
      <div
        id={NEW}
        popover="auto"
        className={`${popover} w-80 max-w-[90vw] p-3 [position-anchor:--new-factory] [position-area:bottom_span-left]`}
      >
        <form onSubmit={submit} className="grid gap-2">
          <label className="grid gap-1">
            Name
            {/* board Q10: the autofocus attribute, which the popover focuses as it opens */}
            <input ref={(el) => el?.setAttribute('autofocus', '')} type="text" name="name" className={field} />
          </label>
          <button disabled={busy} className={`${button} justify-self-start`}>
            Create
          </button>
          {error && <ErrorMessage error={error} />}
        </form>
      </div>
    </>
  )
}

/** FE2, FE4: a factory's row. Rename swaps the name for the 049 field; after a save or Esc, focus is back on Rename. */
function FactoryRow({ projectId, factory, onReload, onDelete }) {
  const [renaming, setRenaming] = useState(false)
  const rename = useRef(null)
  const n = factory.nodes
  return (
    <tr>
      <td className="wrap-anywhere">
        {renaming ? (
          <Rename
            label={`Rename ${factory.name}`}
            name={factory.name}
            save={async (name) => {
              await saveFactory(factory.id, { name })
              onReload()
            }}
            onClose={(focus) => {
              setRenaming(false)
              if (focus) rename.current.focus()
            }}
          />
        ) : (
          <Link to={`/projects/${projectId}/factories/${factory.id}`}>{factory.name}</Link>
        )}
      </td>
      <td className={`tabular-nums ${muted}`}>{`${n} ${n === 1 ? 'node' : 'nodes'}`}</td>
      <td className={muted}>
        <Time iso={factory.updated_at} relative />
      </td>
      <td>
        <div className="flex justify-end gap-2">
          <button
            ref={rename}
            type="button"
            aria-label={`Rename ${factory.name}`}
            onClick={() => setRenaming(true)}
            className={smallButton}
          >
            Rename
          </button>
          <button
            type="button"
            aria-label={`Delete ${factory.name}`}
            onClick={(event) => onDelete(factory, event.currentTarget)}
            className={`${smallButton} text-danger`}
          >
            Delete
          </button>
        </div>
      </td>
    </tr>
  )
}

/** 046 Q5: the header with + New factory, then the table's head and two rows. */
function FactoriesSkeleton() {
  return (
    <Skeleton>
      <ProjectHeaderSkeleton>
        <ButtonBlock className="w-32" />
      </ProjectHeaderSkeleton>
      <div className="grid gap-3">
        <Block className="h-6 w-72 max-w-full" />
        <Block className="h-7 w-full" />
        <Block className="h-7 w-full" />
      </div>
    </Skeleton>
  )
}

/** docs/ui.md §8 item 14. Q18: the header's board view-model and the list load once each; the list reloads after an action. */
function Factories({ id }) {
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((n) => n + 1), [])
  const { data: page, error: pageError } = usePoll(useCallback(() => boardPage(id), [id]))
  // board Q3: `tick` is in the deps only to hand usePoll a new load, which fetches at once
  const { data: factories, error } = usePoll(useCallback(() => listFactories(id), [id, tick]))
  const [deleting, setDeleting] = useState(null) // {factory, opener}
  const name = page?.project.name
  useEffect(() => {
    if (name) document.title = `${name} · Factories · Claude Factories`
  }, [name])

  const missing = [pageError, error].find((e) => e?.status === 404)
  if (missing) return <NotFound detail={missing.message} />
  if (!page || !factories) {
    const failed = pageError ?? error
    return failed ? <ErrorMessage error={failed} /> : <FactoriesSkeleton />
  }
  return (
    <>
      <ProjectHeader project={page.project} factory={page.factory}>
        <NewFactory projectId={page.project.id} />
      </ProjectHeader>
      {error && <ErrorMessage error={error} />}
      {factories.length ? (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th>Name</th>
                <th>Nodes</th>
                <th>Updated</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {factories.map((factory) => (
                <FactoryRow
                  key={factory.id}
                  projectId={page.project.id}
                  factory={factory}
                  onReload={reload}
                  onDelete={(f, opener) => setDeleting({ factory: f, opener })}
                />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className={muted}>No factories yet.</p>
      )}
      {deleting && (
        <DeleteDialog
          title={`Delete factory ${deleting.factory.name}?`}
          text={DELETE_TEXT}
          remove={() => deleteFactory(deleting.factory.id)}
          onDeleted={reload}
          onClose={(deleted) => {
            setDeleting(null)
            // the row is gone, so focus goes to + New factory, as the board's delete does
            const next = deleted ? document.querySelector(`[popovertarget="${NEW}"]`) : deleting.opener
            next?.focus()
          }}
        />
      )}
    </>
  )
}

/** Keyed by id, so another project's list starts with no dialog or rename open. */
export function FactoriesPage() {
  const { id } = useParams()
  return <Factories key={id} id={id} />
}
