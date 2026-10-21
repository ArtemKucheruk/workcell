import { useEffect, useId, useRef, useState } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router'
import { planName } from '../api/auth.js'
import { deleteProject, patchProject } from '../api/projects.js'
import { deleteWorkspace, renameWorkspace } from '../api/workspaces.js'
import { DeleteDialog, PROJECT_TEXT, WORKSPACE_TEXT } from '../components/DeleteDialog.jsx'
import { ErrorMessage } from '../components/ErrorMessage.jsx'
import { useNewWorkspace, WorkspaceNameField } from '../components/NewWorkspace.jsx'
import { field, muted, popover, smallButton } from '../components/styles.js'

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

/**
 * 049 FE3, Q16: hidden by opacity only from md up, so Tab still reaches it; shown while its row (the `group/row`) is
 * hovered or holds focus, while its menu is open, and on touch screens, which can't hover. Below md, the drawer, it shows.
 */
const actionsButton = [
  'grid size-7 shrink-0 cursor-pointer place-items-center rounded-md text-muted hover:bg-line hover:text-fg motion-safe:transition-opacity',
  'md:opacity-0 md:group-hover/row:opacity-100 md:group-focus-within/row:opacity-100 md:group-has-[:popover-open]/row:opacity-100 md:pointer-coarse:opacity-100',
].join(' ')

// a menu item; buttons inherit the menu's fg, so Delete's text-danger has no color to fight
const menuItem = 'cursor-pointer rounded px-2 py-1 text-left hover:bg-raised hover:no-underline'

/** 049 FE1, FE2, Q9: `⋯` and its native popover menu, placed under it where the browser has anchor positioning (044 Q10). */
function Actions({ id, label, ref, children }) {
  return (
    <>
      <button ref={ref} type="button" popoverTarget={id} aria-label={label} style={{ anchorName: `--${id}` }} className={actionsButton}>
        ⋯
      </button>
      <div
        id={id}
        popover="auto"
        style={{ positionAnchor: `--${id}` }}
        className={`${popover} w-48 cursor-default p-1 open:grid [position-area:bottom_span-left]`}
      >
        {children}
      </div>
    </>
  )
}

/** A menu button: it hides its menu natively as it's chosen. */
function Item({ menu, onClick, className = '', children, ...rest }) {
  return (
    <button type="button" popoverTarget={menu} popoverTargetAction="hide" onClick={onClick} className={`${menuItem} ${className}`} {...rest}>
      {children}
    </button>
  )
}

/** FE4: a link navigates without hiding a popover, so it hides its own. */
function SettingsItem({ to }) {
  return (
    <Link to={to} onClick={(event) => event.currentTarget.closest('[popover]').hidePopover?.()} className={`${menuItem} text-fg`}>
      Settings
    </Link>
  )
}

/**
 * 049 FE5–FE9, Q10: a name edited in place, focused with all of it selected. Enter sends `save` even unchanged; a refusal
 * shows under the input, which keeps the text. Esc or blur cancels with no request. `onClose(focus)` asks the row to
 * put focus on its `⋯` (after a save or Esc).
 */
function Rename({ label, name, save, onClose }) {
  const input = useRef(null)
  const busy = useRef(false)
  const [error, setError] = useState(null)
  useEffect(() => {
    input.current.focus()
    input.current.select()
  }, [])

  async function submit(event) {
    event.preventDefault()
    if (busy.current) return
    busy.current = true
    try {
      await save(input.current.value)
    } catch (err) {
      setError(err)
      return
    } finally {
      busy.current = false
    }
    onClose(true)
  }

  return (
    <form onSubmit={submit} className="grid min-w-0 flex-1 gap-1">
      <input
        ref={input}
        type="text"
        aria-label={label}
        defaultValue={name}
        onKeyDown={(event) => {
          if (event.key !== 'Escape') return
          event.preventDefault() // else the same Esc also closes a modal drawer
          onClose(true)
        }}
        onBlur={() => onClose(false)}
        className={`${field} w-full`}
      />
      {error && <ErrorMessage error={error} />}
    </form>
  )
}

/**
 * 049 FE1, FE5–FE8, FE10–FE14: a project's disclosure and its `⋯` menu: Rename in place, Settings, Move to each other
 * workspace (Q9: left out with none), and Delete through the dialog.
 */
function ProjectRow({ project, menu, links, expanded, onToggle, workspace, others, onReload, onMoved, onError, go }) {
  const actions = useRef(null)
  const [renaming, setRenaming] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const caption = `${menu}-move`

  function closeRename(focus) {
    setRenaming(false)
    if (focus) actions.current.focus()
  }

  async function move(to) {
    onError(null)
    try {
      await patchProject(project.id, { workspace_id: to.id })
    } catch (err) {
      onError(err)
      return
    }
    onMoved()
  }

  return (
    <li>
      <div className={`group/row flex items-start gap-0.5 rounded-md ${renaming ? '' : 'hover:bg-surface'}`}>
        {/* the disclosure first in this file: 046 FE21 reads the turning chevron's classes from the source */}
        {!renaming ? (
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls={links}
            onClick={() => onToggle(project.id)}
            className={`${row} min-w-0 flex-1 cursor-pointer font-medium`}
          >
            <span aria-hidden="true" className={`w-3 shrink-0 text-muted motion-safe:transition-transform ${expanded ? 'rotate-90' : ''}`}>
              ▸
            </span>
            <span className="truncate">{project.name}</span>
          </button>
        ) : (
          <>
            {/* §8.4: the chevron stays, still, beside the field, at the disclosure's place and text line */}
            <span aria-hidden="true" className={`mt-1.25 ml-2 w-3 shrink-0 text-muted ${expanded ? 'rotate-90' : ''}`}>
              ▸
            </span>
            <Rename
              label={`Rename ${project.name}`}
              name={project.name}
              save={async (name) => {
                await patchProject(project.id, { name })
                onReload()
              }}
              onClose={closeRename}
            />
          </>
        )}
        <Actions ref={actions} id={menu} label={`Actions for ${project.name}`}>
          <Item menu={menu} onClick={() => setRenaming(true)}>
            Rename
          </Item>
          <SettingsItem to={`/projects/${project.id}/settings`} />
          {others.length > 0 && (
            <>
              <p id={caption} className={`px-2 pt-1 text-xs ${muted}`}>
                Move to workspace
              </p>
              <div className="grid pl-2">
                {others.map((w) => (
                  <Item key={w.id} menu={menu} onClick={() => move(w)} aria-describedby={caption} className="truncate">
                    {w.name}
                  </Item>
                ))}
              </div>
            </>
          )}
          <hr className="my-1 border-line" />
          <Item menu={menu} onClick={() => setDeleting(true)} className="text-danger">
            Delete
          </Item>
        </Actions>
      </div>
      <ul id={links} hidden={!expanded} className="ml-5 grid gap-0.5 border-l border-line pl-1">
        {pages(project).map(([to, label]) => (
          <li key={to}>
            <NavLink to={to} end className={navLink}>
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
      {deleting && (
        <DeleteDialog
          title={`Delete project ${project.name}?`}
          text={PROJECT_TEXT}
          remove={() => deleteProject(project.id)}
          onDeleted={() => go(`/workspaces/${workspace.id}`)}
          onClose={(deleted) => {
            setDeleting(false)
            if (!deleted) actions.current.focus()
          }}
        />
      )}
    </li>
  )
}

/** FE11, Q10: each project discloses its pages; the list stays in the DOM so aria-controls always resolves. */
function Projects({ workspace, open, onToggle, ...row }) {
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
      {workspace.projects.map((project) => (
        <ProjectRow
          key={project.id}
          project={project}
          // 049: useId's punctuation stripped, since the menu id is also an anchor name
          menu={`${id.replace(/[^\w-]/g, '')}-menu-${project.id}`}
          links={`${id}-project-${project.id}`}
          expanded={open.has(project.id)}
          onToggle={onToggle}
          workspace={workspace}
          {...row}
        />
      ))}
    </ul>
  )
}

/**
 * 049 FE2, FE9, FE15: the workspace `<select>` (or its rename field) and its `⋯` menu: Rename, Settings, and Delete.
 */
function WorkspaceRow({ workspaces, workspace, selected, onSelect, selectId, onReload, go }) {
  const menu = `${useId().replace(/[^\w-]/g, '')}-workspace-menu`
  const actions = useRef(null)
  const [renaming, setRenaming] = useState(false)
  const [deleting, setDeleting] = useState(false)

  function closeRename(focus) {
    setRenaming(false)
    if (focus) actions.current.focus()
  }

  return (
    <div className="group/row flex items-start gap-1">
      {renaming ? (
        <Rename
          label={`Rename workspace ${workspace.name}`}
          name={workspace.name}
          save={async (name) => {
            await renameWorkspace(workspace.id, name)
            onReload()
          }}
          onClose={closeRename}
        />
      ) : (
        <select
          id={selectId}
          value={selected ?? ''}
          onChange={(event) => onSelect(Number(event.target.value))}
          className={`${field} w-full min-w-0 flex-1`}
        >
          {workspaces.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
      )}
      {workspace && (
        <Actions ref={actions} id={menu} label={`Actions for workspace ${workspace.name}`}>
          <Item menu={menu} onClick={() => setRenaming(true)}>
            Rename
          </Item>
          <SettingsItem to={`/workspaces/${workspace.id}/settings`} />
          <hr className="my-1 border-line" />
          <Item menu={menu} onClick={() => setDeleting(true)} className="text-danger">
            Delete
          </Item>
        </Actions>
      )}
      {deleting && (
        <DeleteDialog
          title={`Delete workspace ${workspace.name}?`}
          text={WORKSPACE_TEXT}
          remove={() => deleteWorkspace(workspace.id)}
          onDeleted={() => go('/')}
          onClose={(deleted) => {
            setDeleting(false)
            if (!deleted) actions.current.focus()
          }}
        />
      )}
    </div>
  )
}

/**
 * docs/ui.md §8.4: the app name, the workspace area, then Dashboard, the fctl reference, and the badge.
 * Q15: one landmark with no headings. Layout owns the state, so the column and the drawer show the same thing.
 */
export function Sidebar({ auth, sidebar, selected, onSelect, open, onToggle, onReload }) {
  const selectId = useId()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { data, error } = sidebar
  const workspace = data?.workspaces.find((w) => w.id === selected)
  // 049 FE10: a refused move; the next load of the sidebar (a navigation or reload) clears it
  const [refusal, setRefusal] = useState(null)
  useEffect(() => setRefusal(null), [sidebar])

  // 049 Q13: a delete lands on another page, whose navigation reloads the sidebar; on the same page, reload it here
  const go = (to) => (to === pathname ? onReload() : navigate(to))
  const row = {
    others: data?.workspaces.filter((w) => w !== workspace) ?? [],
    onReload,
    onError: setRefusal,
    onMoved: () => {
      onReload()
      document.getElementById(selectId)?.focus()
    },
    go,
  }
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
              <WorkspaceRow
                workspaces={data.workspaces}
                workspace={workspace}
                selected={selected}
                onSelect={onSelect}
                selectId={selectId}
                onReload={onReload}
                go={go}
              />
            </div>
          ) : (
            <p className={`px-2 ${muted}`}>
              No workspaces yet. Run <code>{'fctl connect --workspace <name>'}</code> in a repo, or add one with + New
              workspace.
            </p>
          ))}
        {data && <AddWorkspace />}
        {refusal && (
          <div className="px-2">
            <ErrorMessage error={refusal} />
          </div>
        )}
        {workspace && <Projects workspace={workspace} open={open} onToggle={onToggle} {...row} />}
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
