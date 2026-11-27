import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useOutletContext, useParams } from 'react-router'
import { workspacePage } from '../../api/pages.js'
import { deleteWorkspace, renameWorkspace } from '../../api/workspaces.js'
import { DangerZone, WORKSPACE_TEXT } from '../../components/DeleteDialog.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { Block, ButtonBlock, Skeleton } from '../../components/Skeleton.jsx'
import { button, field, muted, section } from '../../components/styles.js'
import { usePoll } from '../../hooks/usePoll.js'

/** 049 FE21: the name, sent as typed; on success the field takes the stored (trimmed) name, and a refusal keeps it. */
function NameForm({ workspace, onSaved }) {
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  async function submit(event) {
    event.preventDefault()
    const input = event.currentTarget.elements.namedItem('name')
    setBusy(true)
    setSaved(false)
    try {
      input.value = (await renameWorkspace(workspace.id, input.value)).name
      setError(null)
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={submit} onInput={() => setSaved(false)} className="grid gap-2">
      <label htmlFor="workspace-name" className={muted}>
        Name
      </label>
      <div className="flex flex-wrap items-center gap-3">
        <input id="workspace-name" name="name" defaultValue={workspace.name} className={`${field} w-full max-w-md`} />
        <button disabled={busy} className={button}>
          Save
        </button>
        <span aria-live="polite" className={muted}>
          {saved ? 'Saved.' : ''}
        </span>
      </div>
      {error && <ErrorMessage error={error} />}
    </form>
  )
}

/** 046 Q5: the h1, the Name label, field, and Save, then the Projects heading and two rows. */
function WorkspaceSettingsSkeleton() {
  return (
    <Skeleton>
      <Block className="mb-6 h-8 w-48" />
      <div className="grid max-w-3xl gap-8">
        <div className="grid gap-2">
          <Block className="h-6 w-16" />
          <div className="flex gap-3">
            <Block className="h-8.5 w-full max-w-md" />
            <ButtonBlock className="w-16" />
          </div>
        </div>
        <div className={section}>
          <Block className="h-7 w-28" />
          <Block className="h-6 w-80 max-w-full" />
          <Block className="h-6 w-72 max-w-full" />
        </div>
      </div>
    </Skeleton>
  )
}

/** docs/ui.md §8 item 13, Q14: loaded once, and reloaded after a rename. No breadcrumb. */
function WorkspaceSettings({ id }) {
  const { reloadSidebar } = useOutletContext()
  const navigate = useNavigate()
  // board Q3: bumping `tick` hands usePoll a new load, which fetches at once
  const [tick, setTick] = useState(0)
  const load = useCallback(() => workspacePage(id), [id, tick])
  const { data: page, error } = usePoll(load)
  const name = page?.workspace.name
  useEffect(() => {
    if (name) document.title = `${name} · Settings · Workcell`
  }, [name])

  if (error?.status === 404) return <NotFound detail={error.message} />
  if (!page) return error ? <ErrorMessage error={error} /> : <WorkspaceSettingsSkeleton />
  return (
    <>
      <h1 className="mb-6 wrap-anywhere">{name}</h1>
      {error && <ErrorMessage error={error} />}
      <div className="grid max-w-3xl gap-8">
        <NameForm
          workspace={page.workspace}
          onSaved={() => {
            setTick((n) => n + 1)
            reloadSidebar() // Q13: no navigation, so the sidebar's name follows here
          }}
        />
        <section aria-labelledby="workspace-projects" className={section}>
          <h2 id="workspace-projects" className="m-0">
            Projects
          </h2>
          {/* Q14: each to its Settings, where Move and Delete live */}
          {page.projects.length ? (
            <ul className="grid gap-1">
              {page.projects.map((p) => (
                <li key={p.id} className="flex flex-wrap items-baseline gap-x-3">
                  <Link to={`/projects/${p.id}/settings`}>{p.name}</Link>
                  <span className={`font-mono text-sm wrap-anywhere ${muted}`}>{p.path}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className={muted}>No projects.</p>
          )}
        </section>
        <DangerZone
          label="Delete workspace"
          summary="Delete this workspace from the app. It must hold no projects."
          title={`Delete workspace ${name}?`}
          text={WORKSPACE_TEXT}
          remove={() => deleteWorkspace(page.workspace.id)}
          onDeleted={() => navigate('/')}
        />
      </div>
    </>
  )
}

/** Keyed by id, so another workspace starts with its own Name field and no earlier refusal. */
export function WorkspaceSettingsPage() {
  const { id } = useParams()
  return <WorkspaceSettings key={id} id={id} />
}
