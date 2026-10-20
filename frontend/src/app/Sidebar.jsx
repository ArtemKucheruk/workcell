import { useId, useRef, useState } from 'react'
import { Link, NavLink } from 'react-router'
import { planName } from '../api/auth.js'
import { ErrorMessage } from '../components/ErrorMessage.jsx'
import { useNewWorkspace, WorkspaceNameField } from '../components/NewWorkspace.jsx'
import { field, muted, smallButton } from '../components/styles.js'

// 041: a row of the sidebar, a link or a button; it hovers on `surface`, the column being `raised`
const row = 'flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left hover:bg-surface hover:no-underline'

// Q9: NavLink marks the current page itself; the others drop the base `a` accent
const navLink = ({ isActive }) => `${row} ${isActive ? 'bg-surface font-medium text-accent' : 'text-fg'}`

/** docs/ui.md §8, Q8: the login runs will use, as handlers/pages.py claude_login words it; 039: a link to Settings. */
function AuthBadge({ auth }) {
  if (!auth.runs_enabled) {
    return (
      <Link to="/settings" className="text-sm font-semibold text-danger">
        API key — runs disabled
      </Link>
    )
  }
  return (
    <Link to="/settings" className="text-sm text-muted">
      {`Claude: ${planName(auth.plan)} ✓`}
    </Link>
  )
}

/** Q8: a disclosure for the name field and Create; Cancel or Esc hides them and returns focus to the button. */
function AddWorkspace() {
  const [adding, setAdding] = useState(false)
  const toggle = useRef(null)
  const { submit, error, busy } = useNewWorkspace(() => setAdding(false))
  const hide = () => {
    setAdding(false)
    toggle.current.focus()
  }
  return (
    <>
      <button
        ref={toggle}
        type="button"
        aria-expanded={adding}
        onClick={() => setAdding(!adding)}
        className={`${row} cursor-pointer text-muted hover:text-fg`}
      >
        + New workspace
      </button>
      {adding && (
        <form
          onSubmit={submit}
          onKeyDown={(event) => {
            if (event.key !== 'Escape') return
            event.preventDefault() // else the same Esc also closes a modal drawer
            hide()
          }}
          className="grid gap-2 px-2"
        >
          <WorkspaceNameField autoFocus className={`${field} w-full`} />
          <div className="flex gap-2">
            <button disabled={busy} className={smallButton}>
              Create
            </button>
            <button type="button" onClick={hide} className={smallButton}>
              Cancel
            </button>
          </div>
          {error && <ErrorMessage error={error} />}
        </form>
      )}
    </>
  )
}

/**
 * 042 FE34, FE35: a project's pages, in order; Reviews carries its count of tasks waiting on me or escalated, when above 0.
 * 043 Q7: the count is the filled warning pill, never danger, since every task it counts waits on me.
 */
const pages = (project) => [
  [`/projects/${project.id}`, 'Board'],
  [`/projects/${project.id}/code`, 'Code'],
  [
    `/projects/${project.id}/reviews`,
    <>
      Reviews
      {project.review > 0 && (
        <>
          {' '}
          <span className="ml-auto min-w-5 rounded-full bg-warning px-1.5 text-center text-xs/5 font-medium text-surface tabular-nums">{project.review}</span>
        </>
      )}
    </>,
  ],
  [`/projects/${project.id}/context`, 'Context'],
  [`/projects/${project.id}/settings`, 'Settings'],
]

/** FE11, Q10: each project discloses its pages; the list stays in the DOM so aria-controls always resolves. */
function Projects({ workspace, open, onToggle }) {
  const id = useId()
  if (!workspace.projects.length) {
    return (
      <p className={`px-2 ${muted}`}>
        No projects. Run <code>{`fctl connect --workspace ${workspace.name}`}</code> in a repo.
      </p>
    )
  }
  return (
    <ul className="grid gap-0.5">
      {workspace.projects.map((project) => {
        const expanded = open.has(project.id)
        const links = `${id}-project-${project.id}`
        return (
          <li key={project.id}>
            <button
              type="button"
              aria-expanded={expanded}
              aria-controls={links}
              onClick={() => onToggle(project.id)}
              className={`${row} cursor-pointer font-medium`}
            >
              <span aria-hidden="true" className={`w-3 shrink-0 text-muted transition-transform ${expanded ? 'rotate-90' : ''}`}>
                ▸
              </span>
              <span className="truncate">{project.name}</span>
            </button>
            <ul id={links} hidden={!expanded} className="ml-5 grid gap-0.5 border-l border-line pl-1">
              {pages(project).map(([to, label]) => (
                <li key={to}>
                  <NavLink to={to} end className={navLink}>
                    {label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </li>
        )
      })}
    </ul>
  )
}

/**
 * docs/ui.md §8.4: the app name, the workspace area, then Dashboard, the fctl reference, and the badge.
 * Q15: one landmark with no headings. Layout owns the state, so the column and the drawer show the same thing.
 */
export function Sidebar({ auth, sidebar, selected, onSelect, open, onToggle }) {
  const selectId = useId()
  const { data, error } = sidebar
  const workspace = data?.workspaces.find((w) => w.id === selected)
  return (
    <nav aria-label="Sidebar" className="flex min-h-full flex-col gap-6 p-4 text-sm">
      <Link to="/" className="px-2 text-base font-semibold text-inherit hover:no-underline">
        Claude Factories
      </Link>
      {/* Q12: nothing while loading; a failure is muted, as the page reports a backend that's down */}
      <div className="grid gap-2">
        {error && <p className={`px-2 ${muted}`}>Projects didn't load</p>}
        {data &&
          (data.workspaces.length ? (
            <div className="grid gap-1 px-2">
              <label htmlFor={selectId} className={`text-xs font-medium ${muted}`}>
                Workspace
              </label>
              <select
                id={selectId}
                value={selected ?? ''}
                onChange={(event) => onSelect(Number(event.target.value))}
                className={`${field} w-full`}
              >
                {data.workspaces.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <p className={`px-2 ${muted}`}>
              No workspaces yet. Run <code>{'fctl connect --workspace <name>'}</code> in a repo, or add one with + New
              workspace.
            </p>
          ))}
        {data && <AddWorkspace />}
        {workspace && <Projects workspace={workspace} open={open} onToggle={onToggle} />}
      </div>
      <div className="mt-auto grid gap-2 border-t border-line pt-4">
        <ul className="grid gap-0.5">
          <li>
            <NavLink to="/" end className={navLink}>
              Dashboard
            </NavLink>
          </li>
          <li>
            <NavLink to="/docs/fctl" end className={navLink}>
              fctl reference
            </NavLink>
          </li>
        </ul>
        {auth && (
          <p className="px-2">
            <AuthBadge auth={auth} />
          </p>
        )}
      </div>
    </nav>
  )
}
