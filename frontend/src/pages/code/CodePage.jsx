import hljs from 'highlight.js/lib/common'
import { useCallback, useEffect, useId, useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { boardPage, codePage } from '../../api/pages.js'
import { Breadcrumbs, projectTrail } from '../../components/Breadcrumbs.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { FileTree } from '../../components/FileTree.jsx'
import { Markdown } from '../../components/Markdown.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { ProjectHeader } from '../../components/ProjectHeader.jsx'
import { Select } from '../../components/Select.jsx'
import { Block, Crumbs, Lines, ProjectHeaderSkeleton, Skeleton } from '../../components/Skeleton.jsx'
import { muted } from '../../components/styles.js'
import { usePoll } from '../../hooks/usePoll.js'

// Q6: both <pre> share font, size, and line height, so the gutter's numbers line up with the code's lines
const mono = 'm-0 p-2 font-mono text-[0.85rem]/[1.4]'

/** Q2, 025 Q4: the view-model's nested tree as FileTree's flat list, in `Object.entries` order; directory keys end in "/". */
const flatten = (node) => Object.entries(node).flatMap(([name, child]) => (name.endsWith('/') ? flatten(child) : [child]))

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

/**
 * 090 Q4: a link to the git host, in a new tab. `href` is the backend's lib.remote result, always http(s), never a
 * raw remote. The hidden suffix tells a screen reader it opens a new tab.
 */
function HostLink({ href, children }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-sm wrap-anywhere">
      {children}
      {/* the space outside the span: accessible-name computation trims a hidden child's own spaces */}
      {' '}
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  )
}

/** Q3: decided from the view-model alone, so a stale one never renders as the wrong kind. */
function Viewer({ page }) {
  const { view, lang, readme_html } = page
  if (view?.note != null) return <p className={muted}>{view.note}</p>
  if (readme_html != null) return <Markdown html={readme_html} />
  return view ? <Code view={view} lang={lang} /> : null
}

/** 046 Q5: the breadcrumb, the project header with its Branch picker line, then the file tree beside the viewer. */
function CodeSkeleton() {
  return (
    <Skeleton>
      <Crumbs className="mb-2 w-48" />
      <ProjectHeaderSkeleton>
        <div className="basis-full">
          <Block className="h-7.5 w-48" />
        </div>
      </ProjectHeaderSkeleton>
      <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-[minmax(10rem,16rem)_minmax(0,1fr)]">
        <Lines n={6} />
        <div className="rounded-md border border-line p-4">
          <Lines n={8} />
        </div>
      </div>
    </Skeleton>
  )
}

/** docs/ui.md §8 item 6: the main checkout's or a branch's tracked files, the README landing, and one file at a time. */
export function CodePage() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const path = params.get('path') ?? '' // Q2: an empty path is the landing
  const wanted = params.get('branch') ?? '' // 054: sent as is, so ?branch=<checked-out> gets the working tree from the backend
  // Q1: no polling; fetches on first load and on each path or branch change
  const load = useCallback(() => codePage(id, path, wanted), [id, path, wanted])
  const branchId = useId()
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
  if (!page) return error ? <ErrorMessage error={error} /> : <CodeSkeleton />
  // 054: a backend from before `branches` gives a picker with the checked-out branch alone, not a crash
  const { project, branch, branches = [], tree, shown, file_url } = page
  // 090 Q4: the repo link's text is web_url without its scheme; absent from an older backend, so no link
  const repo = project.web_url && (
    <HostLink href={project.web_url}>{project.web_url.replace(/^https?:\/\//, '')}</HostLink>
  )
  // 054 Q2: the browsed branch; none (the "" option, the working tree) for no ?branch= or the checked-out one
  const browsed = wanted && wanted !== branch ? wanted : ''
  // usePoll keeps the last data across a project change: only this project's board view-model counts
  const head = board?.project.id === project.id ? board : { project }

  return (
    <>
      {/* 047 Q1: from the code view-model alone, so it shows whatever the board view-model does; `Code` is always current */}
      <div className="mb-2">
        <Breadcrumbs items={[...projectTrail({ ...project, project_id: project.id, project: project.name }), { label: 'Code' }]} />
      </div>
      <ProjectHeader project={head.project} factory={head.factory}>
        {/* 054 Q8: only with a checked-out branch (or detached HEAD), as the old label; a sibling label, so the
            select's name is Branch and not Branch plus its option. Q3: picking one drops ?path= for its README landing.
            min-w-0 lets the line shrink to the header, so a long option can't widen the page; the select caps at 28rem */}
        {branch && (
          <p className="min-w-0 basis-full text-sm">
            <label htmlFor={branchId}>Branch</label>{' '}
            <Select
              id={branchId}
              value={browsed}
              onChange={(value) => setParams(value ? { branch: value } : {})}
              options={[
                { value: '', label: branch },
                ...branches.filter((name) => name !== branch).map((name) => ({ value: name, label: name })),
              ]}
              className="max-w-[min(100%,28rem)] font-mono"
            />
            {repo && <> {repo}</>}
          </p>
        )}
        {/* 090 Q4: with no Branch line (a git failure), the repo link gets a line of its own */}
        {!branch && repo && <p className="min-w-0 basis-full">{repo}</p>}
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
            {/* Q3: the URL's file opens its directories and is the current page; keyed so another project starts fresh */}
            <FileTree
              key={project.id}
              files={flatten(tree)}
              current={path}
              renderFile={(file, name) => (
                <Link
                  to={`/projects/${project.id}/code?${new URLSearchParams(browsed ? { path: file.path, branch: browsed } : { path: file.path })}`}
                  aria-current={file.path === path ? 'page' : undefined}
                  className="text-fg aria-[current=page]:font-semibold aria-[current=page]:text-accent"
                >
                  {name}
                </Link>
              )}
            />
          </nav>
          <div className="min-w-0">
            {/* 090 Q4, Q5: file_url only with ?path= on github.com (lib.remote.blob_url), so the README landing has no
                second link and the label can name the host */}
            {shown && (
              <div className="mb-1 flex flex-wrap items-baseline gap-x-3">
                <h2 className="m-0 text-base">
                  <code className="wrap-anywhere">{shown}</code>
                </h2>
                {file_url && <HostLink href={file_url}>View on github.com</HostLink>}
              </div>
            )}
            <Viewer page={page} />
          </div>
        </div>
      )}
    </>
  )
}
