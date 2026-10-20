import hljs from 'highlight.js/lib/common'
import { useCallback, useEffect, useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { boardPage, codePage } from '../../api/pages.js'
import { Breadcrumbs, projectTrail } from '../../components/Breadcrumbs.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { Markdown } from '../../components/Markdown.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { ProjectHeader } from '../../components/ProjectHeader.jsx'
import { muted } from '../../components/styles.js'
import { usePoll } from '../../hooks/usePoll.js'

// Q6: both <pre> share font, size, and line height, so the gutter's numbers line up with the code's lines
const mono = 'm-0 p-2 font-mono text-[0.85rem]/[1.4]'

/**
 * Q4: the nested tree as sent, in `Object.entries` order; directory keys end in "/". A directory is open
 * only if the URL's `path` is under it, and the URL's file is the current page.
 */
function Tree({ node, id, path, prefix = '' }) {
  return (
    <ul className={prefix ? 'pl-4' : ''}>
      {Object.entries(node).map(([name, child]) => (
        <li key={name}>
          {name.endsWith('/') ? (
            <details open={path.startsWith(prefix + name)}>
              <summary className="cursor-pointer">{name}</summary>
              <Tree node={child} id={id} path={path} prefix={prefix + name} />
            </details>
          ) : (
            <Link
              to={`/projects/${id}/code?${new URLSearchParams({ path: child.path })}`}
              aria-current={child.path === path ? 'page' : undefined}
              className="aria-[current=page]:font-semibold"
            >
              {name}
            </Link>
          )}
        </li>
      ))}
    </ul>
  )
}

/**
 * Q5: the whole file at once, so multi-line strings and comments color right, and only for an extension
 * highlight.js knows (no auto-detection). Its HTML escapes the text. ponytail: a 1 MB file is highlighted on
 * the main thread in one go; add a size cap or a worker if that's slow.
 */
function highlight(text, lang) {
  return lang && hljs.getLanguage(lang) ? hljs.highlight(text, { language: lang, ignoreIllegals: true }).value : null
}

/** Q6: code.html's markup; the box scrolls sideways and the sticky gutter stays put. */
function Code({ view, lang }) {
  const html = useMemo(() => highlight(view.text, lang), [view.text, lang])
  return (
    <div className="flex overflow-x-auto rounded-md border border-line">
      <pre
        aria-hidden="true"
        className={`${mono} sticky left-0 border-r border-line bg-surface text-right select-none ${muted}`}
      >
        {Array.from({ length: view.lines }, (_, i) => i + 1).join('\n')}
      </pre>
      <pre className={`${mono} grow`}>
        {html == null ? <code>{view.text}</code> : <code dangerouslySetInnerHTML={{ __html: html }} />}
      </pre>
    </div>
  )
}

/** Q3: decided from the view-model alone, so a stale one never renders as the wrong kind. */
function Viewer({ page }) {
  const { view, lang, readme_html } = page
  if (view?.note != null) return <p className={muted}>{view.note}</p>
  if (readme_html != null) return <Markdown html={readme_html} />
  return view ? <Code view={view} lang={lang} /> : null
}

/** docs/ui.md §8 item 6: the main checkout's tracked files, the README landing, and one file at a time. */
export function CodePage() {
  const { id } = useParams()
  const [params] = useSearchParams()
  const path = params.get('path') ?? '' // Q2: an empty path is the landing
  // Q1: no polling; fetches on first load and on each path change
  const load = useCallback(() => codePage(id, path), [id, path])
  const { data: page, error } = usePoll(load)
  // 042 Q2, 047 Q1: the header's factory state comes from the board view-model, once per project; until it arrives,
  // or if it fails, the header is the code view-model's `name · workspace` alone
  const { data: board } = usePoll(useCallback(() => boardPage(id), [id]))
  const name = page?.project.name
  useEffect(() => {
    if (name) document.title = `${path ? `${path} · ` : ''}${name} · Code · Claude Factories`
  }, [name, path])

  // Q8: a 404 (unknown project, or a path the backend refuses) is not-found; other errors replace the page
  // only until the first good load
  if (error?.status === 404) return <NotFound detail={error.message} />
  if (!page) return error ? <ErrorMessage error={error} /> : <p className={muted}>Loading…</p>
  const { project, branch, tree, shown } = page
  // usePoll keeps the last data across a project change: only this project's board view-model counts
  const head = board?.project.id === project.id ? board : { project }

  return (
    <>
      {/* 047 Q1: from the code view-model alone, so it shows whatever the board view-model does; `Code` is always current */}
      <div className="mb-2">
        <Breadcrumbs items={[...projectTrail({ ...project, project_id: project.id, project: project.name }), { label: 'Code' }]} />
      </div>
      <ProjectHeader project={head.project} factory={head.factory}>
        {branch && (
          <p className="basis-full">
            Branch <code className="wrap-anywhere">{branch}</code>
          </p>
        )}
      </ProjectHeader>
      {error && <ErrorMessage error={error} />}
      {page.error ? (
        <ErrorMessage error={{ message: `Can't list files in ${project.path}: ${page.error}` }} />
      ) : Object.keys(tree).length === 0 ? (
        <p className={muted}>No tracked files.</p>
      ) : (
        // Q9: the review page's Files grid; minmax(0, 1fr) keeps a long line from widening the page
        <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-[minmax(10rem,16rem)_minmax(0,1fr)]">
          <nav aria-label="Files" className="text-sm wrap-anywhere">
            <Tree node={tree} id={project.id} path={path} />
          </nav>
          <div className="min-w-0">
            {shown && (
              <h2 className="mt-0 mb-1 text-base">
                <code className="wrap-anywhere">{shown}</code>
              </h2>
            )}
            <Viewer page={page} />
          </div>
        </div>
      )}
    </>
  )
}
