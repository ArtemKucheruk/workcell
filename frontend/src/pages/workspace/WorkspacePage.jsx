import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { workspacePage } from '../../api/pages.js'
import { createWorkspace } from '../../api/workspaces.js'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { button, field, muted } from '../../components/styles.js'
import { Time } from '../../components/Time.jsx'
import { usePoll } from '../../hooks/usePoll.js'

const num = 'text-right tabular-nums'

/** Q9: + Workspace. The API returns the existing workspace's id when the name is taken (§6.1). */
function NewWorkspace() {
  const navigate = useNavigate()
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    const form = event.currentTarget
    setBusy(true)
    try {
      const { id } = await createWorkspace(new FormData(form).get('name'))
      setError(null)
      form.reset()
      navigate(`/workspaces/${id}`)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} className="mt-8 flex flex-wrap items-center gap-2">
      <input
        type="text"
        name="name"
        required
        pattern=".*\S.*"
        title="A name that isn't blank"
        aria-label="New workspace name"
        placeholder="New workspace"
        className={field}
      />
      <button disabled={busy} className={button}>
        + Workspace
      </button>
      {error && <ErrorMessage error={error} />}
    </form>
  )
}

/** docs/ui.md §8 item 2. */
export function WorkspacePage() {
  const { id } = useParams()
  const load = useCallback(() => workspacePage(id), [id])
  const { data: page, error } = usePoll(load)
  const name = page?.workspace.name
  useEffect(() => {
    if (name) document.title = `${name} · Claude Factories`
  }, [name])

  if (error) return error.status === 404 ? <NotFound detail={error.message} /> : <ErrorMessage error={error} />
  if (!page) return <p className={muted}>Loading…</p>
  return (
    <>
      <nav aria-label="Breadcrumb" className="text-sm">
        <Link to="/">Claude Factories</Link>
      </nav>
      <h1 className="mb-4">{name}</h1>
      {page.projects.length ? (
        <div className="overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th scope="col">Project</th><th scope="col">Path</th><th scope="col">Backlog</th>
                <th scope="col">In progress</th><th scope="col">Review</th><th scope="col">Done</th>
                <th scope="col">Factory</th><th scope="col">Last activity</th>
              </tr>
            </thead>
            <tbody>
              {page.projects.map((p) => (
                <tr key={p.id}>
                  <td><Link to={`/projects/${p.id}`}>{p.name}</Link></td>
                  <td className={`font-mono text-sm ${muted}`}>{p.path}</td>
                  <td className={num}>{p.backlog}</td>
                  <td className={num}>{p.in_progress}</td>
                  <td className={num}>{p.review}</td>
                  <td className={num}>{p.done}</td>
                  <td>{p.factory}</td>
                  <td><Time iso={p.last_activity} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>
          No projects yet. Run <code>{`fctl connect --workspace ${name}`}</code> inside a repo.
        </p>
      )}
      <NewWorkspace />
    </>
  )
}
