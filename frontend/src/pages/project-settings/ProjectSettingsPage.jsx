import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useOutletContext, useParams } from 'react-router'
import { boardPage } from '../../api/pages.js'
import { createFactory, deleteProject, importBundle, patchProject, syncFactory } from '../../api/projects.js'
import { DangerZone, PROJECT_TEXT } from '../../components/DeleteDialog.jsx'
import { FactoryForm, FactoryResult, FileList } from '../../components/FactoryResult.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { ProjectHeader } from '../../components/ProjectHeader.jsx'
import { Block, ButtonBlock, ProjectHeaderSkeleton, Rows, Skeleton } from '../../components/Skeleton.jsx'
import { button, field, muted, section } from '../../components/styles.js'
import { usePoll } from '../../hooks/usePoll.js'

/**
 * 049 FE16–FE18, Q15: Name and Test command in one form, sent together as typed. On success the fields take the stored
 * values (trimmed; a blank test command is null), and `onSaved` reloads; a refusal keeps what was typed.
 * A subgrid of the Repository grid, so its labels line up with the read-only rows under it.
 */
function ProjectForm({ project, onSaved }) {
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  async function submit(event) {
    event.preventDefault()
    const form = event.currentTarget
    const { name, test_cmd } = Object.fromEntries(new FormData(form))
    setBusy(true)
    setSaved(false)
    try {
      const out = await patchProject(project.id, { name, test_cmd })
      setError(null)
      form.elements.namedItem('name').value = out.name
      form.elements.namedItem('test_cmd').value = out.test_cmd ?? ''
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={submit} onInput={() => setSaved(false)} className="col-span-2 grid grid-cols-subgrid items-center gap-y-2">
      <label htmlFor="project-name" className={muted}>
        Name
      </label>
      <input id="project-name" name="name" defaultValue={project.name} className={`${field} w-full max-w-md`} />
      <label htmlFor="project-test-cmd" className={muted}>
        Test command
      </label>
      <input
        id="project-test-cmd"
        name="test_cmd"
        defaultValue={project.test_cmd ?? ''}
        placeholder="not set"
        className={`${field} w-full max-w-md font-mono text-sm/6`}
      />
      <div className="col-start-2 flex flex-wrap items-center gap-3">
        <button disabled={busy} className={button}>
          Save
        </button>
        <span aria-live="polite" className={muted}>
          {saved ? 'Saved.' : ''}
        </span>
      </div>
      {error && (
        <div className="col-start-2">
          <ErrorMessage error={error} />
        </div>
      )}
    </form>
  )
}

/** Q9: the repo facts `fctl connect` set, read-only; a null value says so in words. */
function Repository({ project }) {
  const rows = [
    ['Path', project.path],
    ['Remote', project.remote_url, 'none'],
    ['Default branch', project.default_branch],
  ]
  return (
    <dl className="col-span-2 grid grid-cols-subgrid gap-y-1">
      {rows.map(([name, value, empty]) => (
        <div key={name} className="contents">
          <dt className={muted}>{name}</dt>
          <dd className={value == null ? muted : 'font-mono text-sm/6 wrap-anywhere'}>{value ?? empty}</dd>
        </div>
      ))}
    </dl>
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

/**
 * 058 FE1–FE4, Q14: one `POST …/import-factory {}`, disabled while it's pending (no spinner). A 200 says the counts
 * beside the button and `onSynced` reloads; a refusal shows its detail there and doesn't. Cleared as it starts, so a
 * second identical result is announced again.
 */
function SyncFactory({ projectId, onSynced }) {
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)
  async function sync() {
    setBusy(true)
    setOut(null)
    try {
      const { imported, skipped } = await syncFactory(projectId)
      const created = imported.filter((job) => job.created).length
      setOut(`Synced factory/: ${created} new, ${imported.length - created} updated, ${skipped} skipped`)
      onSynced()
    } catch (err) {
      setOut(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="grid gap-2">
      <p className={muted}>
        The repo&apos;s <code>factory/board.json</code> and <code>factory/backlog.md</code> as tasks. The board also syncs
        them when either file changes.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={sync} disabled={busy} className={button}>
          Sync factory/
        </button>
        <div aria-live="polite">{out instanceof Error ? <ErrorMessage error={out} /> : out && <p className={muted}>{out}</p>}</div>
      </div>
    </div>
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
      await patchProject(project.id, { workspace_id: workspaceId })
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

const OVERWRITE = "Overwrite replaces SKILL.md and the 7 agents with the app's templates."

/** 059 FE4, FE5, Q4: for a legacy repo only, what Overwrite would replace: the 8 paths on disk now, or none. */
function OverwriteNote({ files }) {
  if (!files.length) return <p>{`${OVERWRITE} None of them exist now.`}</p>
  return (
    <div className="grid gap-1">
      <p>{`${OVERWRITE} These exist now:`}</p>
      <FileList paths={files} />
    </div>
  )
}

/** One titled block of the page; `id` ties the heading to the region. */
function Section({ id, title, children }) {
  return (
    <section aria-labelledby={id} className={section}>
      <h2 id={id} className="m-0">
        {title}
      </h2>
      {children}
    </section>
  )
}

/** 046 Q5: the project header, then the Repository section's heading, its two fields and Save, and three rows. */
function SettingsSkeleton() {
  return (
    <Skeleton>
      <ProjectHeaderSkeleton />
      <div className={`${section} max-w-3xl`}>
        <Block className="h-7 w-32" />
        <div className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-6 gap-y-2">
          <Block className="h-6 w-28" />
          <Block className="h-8 w-full max-w-md" />
          <Block className="h-6 w-28" />
          <Block className="h-8 w-full max-w-md" />
          <ButtonBlock className="col-start-2 w-16" />
        </div>
        <Rows n={3} />
      </div>
    </Skeleton>
  )
}

/** docs/ui.md §8 item 12. Q6: loaded once, and reloaded after Save, Create factory, Import, Sync factory/, and Move. */
function ProjectSettings({ id }) {
  const { reloadSidebar } = useOutletContext()
  const navigate = useNavigate()
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
  if (!page) return error ? <ErrorMessage error={error} /> : <SettingsSkeleton />
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
          {/* 049 Q15: the editable two first, then the read-only rows, on one grid */}
          <div className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-4">
            <ProjectForm
              project={project}
              onSaved={() => {
                refresh()
                reloadSidebar() // Q13: no navigation, so the sidebar's name follows here
              }}
            />
            <Repository project={project} />
          </div>
          {/* Q5 */}
          <p className={`text-sm ${muted}`}>
            Path, remote, and default branch come from <code>fctl connect</code>. Rerunning it in the repo also resets the
            name, and the test command when it passes one.
          </p>
        </Section>
        <Section id="settings-factory" title="Factory">
          {/* Q9: the state in words; Create factory only when it isn't ready, as on the board before */}
          {factory === 'ready' ? (
            <p>{`Ready: the factory is committed on ${project.default_branch}, so runs can use it.`}</p>
          ) : (
            <>
              {page.hint && <p className={muted}>{page.hint}</p>}
              {factory === 'legacy' && <OverwriteNote files={page.factory_files} />}
              <FactoryForm label="Create factory" create={makeFactory} />
            </>
          )}
          <div aria-live="polite">{factoryOut && <FactoryResult out={factoryOut} />}</div>
        </Section>
        <Section id="settings-import" title="Import">
          <p className={muted}>A task bundle (.zip) from a task&apos;s Export, added to this project.</p>
          <ImportBundle onImport={importFile} />
          <div aria-live="polite">{importOut && <ImportResult out={importOut} />}</div>
          <SyncFactory projectId={project.id} onSynced={refresh} />
        </Section>
        <Section id="settings-move" title="Move to another workspace">
          <MoveProject
            key={project.workspace_id}
            project={project}
            workspaces={page.workspaces}
            onDone={() => {
              refresh()
              reloadSidebar()
            }}
          />
        </Section>
        <DangerZone
          label="Delete project"
          summary="Delete this project and its tasks from the app. The repo stays on disk."
          title={`Delete project ${project.name}?`}
          text={PROJECT_TEXT}
          remove={() => deleteProject(project.id)}
          onDeleted={() => navigate(`/workspaces/${project.workspace_id}`)}
        />
      </div>
    </>
  )
}

/** FE32: keyed by id, so another project starts with its own Move select and no earlier results. */
export function ProjectSettingsPage() {
  const { id } = useParams()
  return <ProjectSettings key={id} id={id} />
}
