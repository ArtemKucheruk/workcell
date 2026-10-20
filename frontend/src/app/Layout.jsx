import { Link, Outlet } from 'react-router'
import { getAuth, planName } from '../api/auth.js'
import { usePoll } from '../hooks/usePoll.js'

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

export function Layout() {
  // 039 Q7: every 3 s, so the badge follows a login finished anywhere; while loading or on a failed first
  // load there's no badge, and the page reports the backend
  const { data: auth } = usePoll(getAuth, 3000)
  return (
    <>
      <header className="flex items-center justify-between gap-4 border-b border-line px-6 py-3">
        <Link to="/" className="font-semibold text-inherit">
          Claude Factories
        </Link>
        <div className="flex items-center gap-4">
          {/* docs/ui.md §8: every page header links to the fctl reference (Q7) */}
          <Link to="/docs/fctl" className="text-sm">
            fctl reference
          </Link>
          {auth && <AuthBadge auth={auth} />}
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-6">
        <Outlet />
      </main>
    </>
  )
}
