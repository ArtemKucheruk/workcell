import { Link } from 'react-router'

/**
 * 042, docs/ui.md §8: the header the five project pages share. `<name> · <workspace>`, then the factory state
 * (Q7: text when ready, else a link to the Settings page that can create it), then the page's own controls.
 * Q2: the Code page passes only `{id, name}` until the board view-model arrives, so the h1 is the name alone.
 */
export function ProjectHeader({ project, factory, children }) {
  return (
    <header className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-2">
      <h1 className="wrap-anywhere">
        {project.name}
        {project.workspace && (
          <>
            {' · '}
            <Link to={`/workspaces/${project.workspace_id}`}>{project.workspace}</Link>
          </>
        )}
      </h1>
      {factory === 'ready' ? (
        <span className="text-sm text-success">Factory: ready ✓</span>
      ) : (
        factory && (
          <Link to={`/projects/${project.id}/settings`} className="text-sm font-medium text-warning">
            {`Factory: ${factory}`}
          </Link>
        )
      )}
      {children}
    </header>
  )
}
