import { Link } from 'react-router'
import { muted } from './styles.js'

/**
 * 047, docs/ui.md §8: `workspace › project › #id › page` on the task, review, code, and transcript pages. `items` is
 * `[{label, to}…, {label}]`: every item but the last links to its `to`, and the last is the current page. Inline items, so
 * a long trail wraps like text; the separators are hidden from screen readers, which hear the list instead.
 */
export function Breadcrumbs({ items }) {
  return (
    <nav aria-label="Breadcrumb" className="text-sm">
      <ol className="wrap-anywhere">
        {items.map((item, i) => (
          <li key={i} className="inline">
            {i > 0 && <span aria-hidden="true" className={muted}>{' › '}</span>}
            {i < items.length - 1 ? (
              <Link to={item.to}>{item.label}</Link>
            ) : (
              <span aria-current="page" className={muted}>
                {item.label}
              </span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  )
}

/** The trail's first two items, from any view-model object with `workspace_id`, `workspace`, `project_id`, and `project`. */
export const projectTrail = ({ workspace_id, workspace, project_id, project }) => [
  { label: workspace, to: `/workspaces/${workspace_id}` },
  { label: project, to: `/projects/${project_id}` },
]
