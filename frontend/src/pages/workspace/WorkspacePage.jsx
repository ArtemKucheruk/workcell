import { useCallback, useEffect } from 'react'
import { Link, useParams } from 'react-router'
import { workspacePage } from '../../api/pages.js'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { useNewWorkspace, WorkspaceNameField } from '../../components/NewWorkspace.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { Block, Skeleton } from '../../components/Skeleton.jsx'
import { button, field, muted } from '../../components/styles.js'
import { Time } from '../../components/Time.jsx'
import { usePoll } from '../../hooks/usePoll.js'

const num = 'text-right tabular-nums'

/** Q9: + Workspace. */
function NewWorkspace() {
  const { submit, error, busy } = useNewWorkspace()
  return (
    <form onSubmit={submit} className="mt-8 flex flex-wrap items-center gap-2">
      <WorkspaceNameField className={field} />
      <button disabled={busy} className={button}>
        + Workspace
      </button>
      {error && <ErrorMessage error={error} />}
    </form>
  )
}

/** 046 Q5: the h1, then the table's header row and three project rows. */
function WorkspaceSkeleton() {
  return (
    <Skeleton>
      <Block className="mb-4 h-8 w-48" />
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="border-b border-line py-1.5">
          <Block className="h-6" />
        </div>
      ))}
    </Skeleton>
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
  if (!page) return <WorkspaceSkeleton />
  return (
    <>
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
                  {/* 059 Q1: legacy can't run, so it's the one state in warning */}
                  <td className={p.factory === 'legacy' ? 'text-warning' : undefined}>{p.factory}</td>
                  <td><Time iso={p.last_activity} relative /></td>
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
