import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { boardPage } from '../../api/pages.js'
import { createFactory, importBundle, moveProject } from '../../api/projects.js'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { ProjectHeader } from '../../components/ProjectHeader.jsx'
import { button, field, muted } from '../../components/styles.js'
import { usePoll } from '../../hooks/usePoll.js'

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`

/** Q9: the repo facts `fctl connect` set, read-only; a null value says so in words. */
function Repository({ project }) {
  const rows = [
    ['Path', project.path],
    ['Remote', project.remote_url, 'none'],
    ['Default branch', project.default_branch],
    ['Test command', project.test_cmd, 'not set'],
  ]
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-1">
      {rows.map(([name, value, empty]) => (
        <div key={name} className="contents">
          <dt className={muted}>{name}</dt>
          <dd className={value == null ? muted : 'font-mono text-sm/6 wrap-anywhere'}>{value ?? empty}</dd>
        </div>
      ))}
    </dl>
  )
}

/** Board Q8, moved: the Overwrite checkbox and the button. */
function FactoryForm({ create }) {
  const [busy, setBusy] = useState(false)
  async function submit(event) {
    event.preventDefault()
    const overwrite = event.currentTarget.elements.overwrite.checked
    setBusy(true)
    try {
      await create(overwrite)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-3">
      <button disabled={busy} className={button}>
        Create factory
      </button>
      <label className="flex items-center gap-1">
        <input type="checkbox" name="overwrite" /> Overwrite existing files
      </label>
    </form>
  )
}

/** MVP §3.2: what Create factory wrote and skipped, and the commit command; or its refusal. */
function FactoryResult({ out }) {
  if (out instanceof Error) return <ErrorMessage error={out} />
  const files = (paths) => (
    <ul className="ml-6 list-disc">
      {paths.map((path) => (
        <li key={path}><code>{path}</code></li>
      ))}
    </ul>
  )
  return (
    <div className="grid gap-1 rounded-md border border-line p-3">
      {out.written.length > 0 && (
        <>
          <p>{`Wrote ${plural(out.written.length, 'file')}:`}</p>
          {files(out.written)}
        </>
      )}
      {out.skipped.length > 0 && (
        <>
          <p>{`Skipped ${plural(out.skipped.length, 'existing file')} (tick Overwrite to replace them):`}</p>
          {files(out.skipped)}
        </>
      )}
      <p>Commit them so runs can see the factory:</p>
      <pre className="overflow-x-auto rounded bg-raised p-2 text-sm"><code>{out.commit_hint}</code></pre>
    </div>
  )
}

/** 032 Q10, moved: a task bundle from Export, posted as is; Import stays disabled until a file is chosen. */
function ImportBundle({ onImport }) {
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    try {
      await onImport(file)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-3">
      <input
        type="file"
        accept=".zip,application/zip"
        aria-label="Task bundle (.zip)"
        onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        className="max-w-72 text-sm"
      />
      <button disabled={!file || busy} className={button}>
        Import
      </button>
    </form>
  )
}

/** 032 Q10: the imported task, linked; or the refusal's detail. */
function ImportResult({ out }) {
  if (out instanceof Error) return <ErrorMessage error={out} />
  return (
    <p>
      Imported <Link to={`/tasks/${out.task_id}`}>{`#${out.task_id} ${out.title}`}</Link>
    </p>
  )
}

/** §8 item 2, moved: this project to another workspace; a refusal shows in the form. */
function MoveProject({ project, workspaces, onDone }) {
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  async function submit(event) {
    event.preventDefault()
    const workspaceId = Number(new FormData(event.currentTarget).get('workspace_id'))
    setBusy(true)
    try {
      await moveProject(project.id, workspaceId)
      setError(null)
      onDone()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-3">
      <label className="flex items-center gap-2">
        Workspace
        <select name="workspace_id" defaultValue={project.workspace_id} className={field}>
          {workspaces.map((w) => (
            <option key={w.id} value={w.id}>{w.name}</option>
          ))}
        </select>
      </label>
      <button disabled={busy} className={button}>
        Move
      </button>
      {error && <ErrorMessage error={error} />}
    </form>
  )
}

/** One titled block of the page; `id` ties the heading to the region. */
function Section({ id, title, children }) {
  return (
    <section aria-labelledby={id} className="grid gap-3 border-t border-line pt-6">
      <h2 id={id} className="m-0">
        {title}
      </h2>
      {children}
    </section>
  )
}

/** docs/ui.md §8 item 12. Q6: loaded once, and reloaded after Create factory, Import, and Move. */
function ProjectSettings({ id }) {
  // board Q3: bumping `tick` hands usePoll a new load, which fetches at once
  const [tick, setTick] = useState(0)
  const refresh = useCallback(() => setTick((n) => n + 1), [])
  const load = useCallback(() => boardPage(id), [id, tick])
  const { data: page, error } = usePoll(load)
  const [factoryOut, setFactoryOut] = useState(null)
  const [importOut, setImportOut] = useState(null)
  const name = page?.project.name
  useEffect(() => {
    if (name) document.title = `${name} · Settings · Claude Factories`
  }, [name])

  if (error?.status === 404) return <NotFound detail={error.message} />
  if (!page) return error ? <ErrorMessage error={error} /> : <p className={muted}>Loading…</p>
  const { project, factory } = page

  async function makeFactory(overwrite) {
    try {
      setFactoryOut(await createFactory(project.id, overwrite))
      refresh()
    } catch (err) {
      setFactoryOut(err) // no reload: the form and its refusal stay as they are
    }
  }

  async function importFile(file) {
    try {
      setImportOut(await importBundle(project.id, file))
      refresh()
    } catch (err) {
      setImportOut(err)
    }
  }

  return (
    <>
      <ProjectHeader project={project} factory={factory} />
      {error && <ErrorMessage error={error} />}
      <div className="grid max-w-3xl gap-8">
        <Section id="settings-repo" title="Repository">
          <Repository project={project} />
          <p className={`text-sm ${muted}`}>
            <code>fctl connect</code> sets these; run it again in the repo to change them.
          </p>
        </Section>
        <Section id="settings-factory" title="Factory">
          {/* Q9: the state in words; Create factory only when it isn't ready, as on the board before */}
          {factory === 'ready' ? (
            <p>{`Ready: the factory is committed on ${project.default_branch}, so runs can use it.`}</p>
          ) : (
            <>
              {page.hint && <p className={muted}>{page.hint}</p>}
              <FactoryForm create={makeFactory} />
            </>
          )}
          <div aria-live="polite">{factoryOut && <FactoryResult out={factoryOut} />}</div>
        </Section>
        <Section id="settings-import" title="Import">
          <p className={muted}>A task bundle (.zip) from a task&apos;s Export, added to this project.</p>
          <ImportBundle onImport={importFile} />
          <div aria-live="polite">{importOut && <ImportResult out={importOut} />}</div>
        </Section>
        <Section id="settings-move" title="Move to another workspace">
          <MoveProject key={project.workspace_id} project={project} workspaces={page.workspaces} onDone={refresh} />
        </Section>
      </div>
    </>
  )
}

/** FE32: keyed by id, so another project starts with its own Move select and no earlier results. */
export function ProjectSettingsPage() {
  const { id } = useParams()
  return <ProjectSettings key={id} id={id} />
}
