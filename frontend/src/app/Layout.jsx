import { useEffect, useRef, useState } from 'react'
import { Outlet, useLocation, useMatches } from 'react-router'
import { getAuth } from '../api/auth.js'
import { sidebarPage } from '../api/pages.js'
import { button } from '../components/styles.js'
import { usePoll } from '../hooks/usePoll.js'
import { Sidebar } from './Sidebar.jsx'

const KEY = 'sidebar.workspace'

/** Q3, Q5: what the path says: the sidebar's query, from an all-digit id only, and the project or workspace shown. */
function routeIds(pathname) {
  const id = (re) => re.exec(pathname)?.[1]
  const task = id(/^\/tasks\/(\d+)(?:\/review)?\/?$/)
  const transcript = id(/^\/transcripts\/(\d+)\/?$/)
  return {
    query: task ? { task } : transcript ? { transcript } : undefined,
    project: id(/^\/projects\/(\d+)(?:\/(?:code|reviews|context|settings))?\/?$/),
    workspace: id(/^\/workspaces\/(\d+)\/?$/),
  }
}

// Q6: storage that throws (blocked, private mode) reads as empty and drops the write; the list still switches
function stored() {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}
function store(id) {
  try {
    localStorage.setItem(KEY, String(id))
  } catch {
    // nothing to keep it in
  }
}

/** docs/ui.md §8, §8.4: the sidebar beside main from md up, below md a <dialog> drawer behind Menu. */
export function Layout() {
  // 039 Q7: every 3 s, so the badge follows a login finished anywhere; while loading or on a failed first
  // load there's no badge, and the page reports the backend
  const { data: auth } = usePoll(getAuth, 3000)
  const location = useLocation()
  const { pathname, search } = location
  const wide = useMatches().some((match) => match.handle?.wide)
  const [sidebar, setSidebar] = useState({})
  const [selected, setSelected] = useState(null)
  const [open, setOpen] = useState(() => new Set())
  const [drawer, setDrawer] = useState(false)
  const menu = useRef(null)
  const dialog = useRef(null)

  function select(id) {
    setSelected(id)
    store(id)
  }

  function toggle(id) {
    setOpen((was) => {
      const next = new Set(was)
      if (!next.delete(id)) next.add(id)
      return next
    })
  }

  // Q11: one fetch per pathname or search change, never polled; Q12: a failure stays until the next one
  useEffect(() => {
    let alive = true
    const ids = routeIds(pathname)
    sidebarPage(ids.query).then(
      (data) => {
        if (!alive) return
        const { workspaces, current } = data
        const listed = (id) => (id == null ? undefined : workspaces.find((w) => String(w.id) === String(id))?.id)
        const owner = workspaces.find((w) => w.projects.some((p) => String(p.id) === ids.project))?.id
        // Q5: the route's project or workspace, else the task's, else the last one shown, else the first
        const chosen = owner ?? listed(ids.workspace) ?? listed(current?.workspace_id) ?? listed(stored())
        const workspace = chosen ?? workspaces[0]?.id
        const project = ids.project ? Number(ids.project) : current?.project_id
        setSidebar({ data })
        if (workspace != null) select(workspace)
        // Q10: the current project opens itself; the others keep whatever state they had
        if (project != null) setOpen((was) => new Set(was).add(project))
      },
      (error) => alive && setSidebar({ error }),
    )
    return () => {
      alive = false
    }
  }, [pathname, search])

  // Q11: any navigation closes the drawer, a link to the page it's on included
  useEffect(() => {
    if (dialog.current.open) dialog.current.close()
  }, [location])

  function openDrawer() {
    setDrawer(true)
    dialog.current.showModal()
  }

  // the close event, from Esc, the backdrop, or a navigation: focus goes back to Menu
  function drawerClosed() {
    setDrawer(false)
    menu.current.focus()
  }

  const props = { auth, sidebar, selected, onSelect: select, open, onToggle: toggle }
  return (
    <div className="md:flex">
      <div className="sticky top-0 hidden h-screen w-60 shrink-0 overflow-y-auto border-r border-line bg-raised md:block">
        <Sidebar {...props} />
      </div>
      <div className="min-w-0 flex-1">
        <button
          ref={menu}
          type="button"
          aria-haspopup="dialog"
          onClick={openDrawer}
          className={`${button} mx-6 mt-4 md:hidden`}
        >
          <span aria-hidden="true">☰ </span>
          Menu
        </button>
        {/* Q14: the board, review, and code pages take the full width; text pages keep a readable one */}
        <main className={wide ? 'px-6 py-6' : 'mx-auto max-w-6xl px-6 py-6'}>
          <Outlet />
        </main>
      </div>
      <dialog
        ref={dialog}
        aria-label="Menu"
        onClose={drawerClosed}
        // the backdrop: a click whose target is the dialog itself, since the sidebar fills its box
        onClick={(event) => event.target === event.currentTarget && event.currentTarget.close()}
        className="h-dvh max-h-none w-72 max-w-[85vw] border-r border-line bg-raised text-fg shadow-xl backdrop:bg-surface/80"
      >
        {drawer && <Sidebar {...props} />}
      </dialog>
    </div>
  )
}
