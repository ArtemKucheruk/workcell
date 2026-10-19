import { Link, Outlet } from 'react-router'
import { getAuth } from '../api/auth.js'
import { usePoll } from '../hooks/usePoll.js'

/** docs/ui.md §8, Q8: the login runs will use, as handlers/pages.py claude_login words it. */
function AuthBadge({ auth }) {
  if (!auth.runs_enabled) {
    return <p className="text-sm font-semibold text-red-700 dark:text-red-400">API key — runs disabled</p>
  }
  const plan = auth.plan ? auth.plan[0].toUpperCase() + auth.plan.slice(1).toLowerCase() : 'subscription'
  return <p className="text-sm text-gray-600 dark:text-gray-400">{`Claude: ${plan} ✓`}</p>
}

export function Layout() {
  // Q8: once per page load; while loading or on failure there's no badge, and the page reports the backend
  const { data: auth } = usePoll(getAuth)
  return (
    <>
      <header className="flex items-center justify-between gap-4 border-b border-gray-200 px-6 py-3 dark:border-gray-800">
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
