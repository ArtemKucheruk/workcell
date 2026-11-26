import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { useParams } from 'react-router'
import { addModule, deleteModule, listModules, saveModule } from '../../api/modules.js'
import { boardPage } from '../../api/pages.js'
import { DeleteDialog } from '../../components/DeleteDialog.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { ProjectHeader } from '../../components/ProjectHeader.jsx'
import { Block, ButtonBlock, ProjectHeaderSkeleton, Skeleton } from '../../components/Skeleton.jsx'
import { button, field, muted, popover, smallButton } from '../../components/styles.js'
import { usePoll } from '../../hooks/usePoll.js'

/** 112 AC19: what Delete removes, and what stays. */
const DELETE_TEXT = 'This removes the module from the app. Its tasks stay, without a module.'

/** AC16: `2 backlog · 1 in progress · 0 review · 7 done`. */
const countsText = (c) => `${c.backlog} backlog · ${c.in_progress} in progress · ${c.review} review · ${c.done} done`

/**
 * AC17, AC18: Name and Description, sent by `save({name, description_md})`. A refusal shows inside, which keeps what was
 * typed; a success runs `onDone`. `module` fills it for an Edit, whose Cancel and Esc run `onCancel`.
 */
function ModuleForm({ module, save, onDone, onCancel, submitLabel }) {
  const id = useId()
  const name = useRef(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (module) name.current.focus()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  async function submit(event) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    setBusy(true)
    try {
      await save({ name: data.get('name'), description_md: data.get('description_md') })
    } catch (err) {
      setError(err)
      setBusy(false)
      return
    }
    setError(null)
    setBusy(false)
    form.reset()
    onDone()
  }
  return (
    <form
      onSubmit={submit}
      onKeyDown={(event) => {
        if (event.key !== 'Escape' || !onCancel) return
        event.preventDefault()
        onCancel()
      }}
      className="grid gap-2"
    >
      <label htmlFor={`${id}-name`}>Name</label>
      <input
        id={`${id}-name`}
        // board Q10: the autofocus attribute, which a popover focuses as it opens; an Edit focuses it on mount
        ref={(el) => {
          name.current = el
          el?.setAttribute('autofocus', '')
        }}
        type="text"
        name="name"
        defaultValue={module?.name}
        aria-describedby={`${id}-hint`}
        className={field}
      />
      <p id={`${id}-hint`} className={`text-sm ${muted}`}>
        Letters, digits, - or _, up to 40, e.g. frontend.
      </p>
      <label className="grid gap-1">
        Description
        <textarea name="description_md" defaultValue={module?.description_md} rows={3} className={field} />
      </label>
      <div className="flex gap-2">
        <button disabled={busy} className={`${button} justify-self-start`}>
          {submitLabel}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className={button}>
            Cancel
          </button>
        )}
      </div>
      {error && <ErrorMessage error={error} />}
    </form>
  )
}

/** AC17: + New module's native popover, as + New workflow's; a created module hides it and reloads the list. */
function NewModule({ projectId, onCreated }) {
  return (
    <>
      <button type="button" popoverTarget="new-module" className={`${button} [anchor-name:--new-module]`}>
        + New module
      </button>
      <div
        id="new-module"
        popover="auto"
        className={`${popover} w-96 max-w-[90vw] p-3 [position-anchor:--new-module] [position-area:bottom_span-left]`}
      >
        <ModuleForm
          submitLabel="Create"
          save={(fields) => addModule(projectId, fields)}
          onDone={() => {
            document.getElementById('new-module').hidePopover?.() // jsdom has no Popover API
            onCreated()
          }}
        />
      </div>
    </>
  )
}

/** AC16, AC18, AC19: a module's row, or its Edit form in its place; after a save or Cancel, focus is back on Edit. */
function ModuleRow({ module, onReload, onDelete }) {
  const [editing, setEditing] = useState(false)
  const edit = useRef(null)
  const refocus = useRef(false)
  useEffect(() => {
    if (!editing && refocus.current) {
      refocus.current = false
      edit.current?.focus()
    }
  }, [editing])
  const close = () => {
    refocus.current = true
    setEditing(false)
  }
  if (editing) {
    return (
      <li aria-label={`Edit ${module.name}`} className="rounded-md border border-line p-3">
        <ModuleForm
          module={module}
          submitLabel="Save"
          save={(fields) => saveModule(module.id, fields)}
          onDone={() => {
            close()
            onReload()
          }}
          onCancel={close}
        />
      </li>
    )
  }
  return (
    <li className="flex flex-wrap items-start justify-between gap-3 rounded-md border border-line p-3">
      <div className="grid min-w-0 gap-1">
        <h3 className="m-0 text-base wrap-anywhere">{module.name}</h3>
        {module.description_md.trim() && <p className={`whitespace-pre-wrap wrap-anywhere ${muted}`}>{module.description_md}</p>}
        <p className="text-sm tabular-nums">{countsText(module.counts)}</p>
      </div>
      <div className="flex gap-2">
        <button
          ref={edit}
          type="button"
          aria-label={`Edit ${module.name}`}
          onClick={() => setEditing(true)}
          className={smallButton}
        >
          Edit
        </button>
        <button
          type="button"
          aria-label={`Delete ${module.name}`}
          onClick={(event) => onDelete(module, event.currentTarget)}
          className={`${smallButton} text-danger`}
        >
          Delete
        </button>
      </div>
    </li>
  )
}

/** 046 Q5: the header with + New module, then two rows. */
function ModulesSkeleton() {
  return (
    <Skeleton>
      <ProjectHeaderSkeleton>
        <ButtonBlock className="w-32" />
      </ProjectHeaderSkeleton>
      <div className="grid gap-3">
        <Block className="h-20 w-full" />
        <Block className="h-20 w-full" />
      </div>
    </Skeleton>
  )
}

/**
 * docs/ui.md §8 item 19, 112: the project's modules with their task counts, then No module. The header's board
 * view-model and the list load once each, and again after each action; never polled.
 */
function Modules({ id }) {
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((n) => n + 1), [])
  // board Q3: `tick` is in the deps only to hand usePoll a new load, which fetches at once
  const { data: page, error: pageError } = usePoll(useCallback(() => boardPage(id), [id, tick]))
  const { data: list, error } = usePoll(useCallback(() => listModules(id), [id, tick]))
  const [deleting, setDeleting] = useState(null) // {module, opener}
  const name = page?.project.name
  useEffect(() => {
    if (name) document.title = `${name} · Modules · Claude Factories`
  }, [name])

  const missing = [pageError, error].find((e) => e?.status === 404)
  if (missing) return <NotFound detail={missing.message} />
  if (!page || !list) {
    const failed = pageError ?? error
    return failed ? <ErrorMessage error={failed} /> : <ModulesSkeleton />
  }
  return (
    <>
      <ProjectHeader project={page.project} factory={page.factory}>
        <NewModule projectId={page.project.id} onCreated={reload} />
      </ProjectHeader>
      {error && <ErrorMessage error={error} />}
      <section aria-labelledby="modules-heading">
        <h2 id="modules-heading">Modules</h2>
        {list.modules.length === 0 && <p className={`mb-3 ${muted}`}>No modules yet.</p>}
        <ul className="grid gap-3">
          {list.modules.map((module) => (
            <ModuleRow
              key={module.id}
              module={module}
              onReload={reload}
              onDelete={(m, opener) => setDeleting({ module: m, opener })}
            />
          ))}
          <li aria-label="No module" className="grid gap-1 rounded-md border border-dashed border-line p-3">
            <h3 className="m-0 text-base">No module</h3>
            <p className="text-sm tabular-nums">{countsText(list.no_module)}</p>
          </li>
        </ul>
      </section>
      {deleting && (
        <DeleteDialog
          title={`Delete module ${deleting.module.name}?`}
          text={DELETE_TEXT}
          remove={() => deleteModule(deleting.module.id)}
          onDeleted={reload}
          onClose={(deleted) => {
            setDeleting(null)
            // the row is gone, so focus goes to + New module, as the Workflows page's delete does
            const next = deleted ? document.querySelector('[popovertarget="new-module"]') : deleting.opener
            next?.focus()
          }}
        />
      )}
    </>
  )
}

/** Keyed by id, so another project's list starts with no dialog or form open. */
export function ModulesPage() {
  const { id } = useParams()
  return <Modules key={id} id={id} />
}
