import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate, useOutletContext, useParams } from 'react-router'
import { boardPage } from '../../api/pages.js'
import {
  createFactory,
  deleteProject,
  importBundle,
  patchProject,
  syncFactory,
  syncGithubIssues,
  syncPlane,
} from '../../api/projects.js'
import { DangerZone, PROJECT_TEXT } from '../../components/DeleteDialog.jsx'
import { FactoryForm, FactoryResult, FileList } from '../../components/FactoryResult.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { ProjectHeader } from '../../components/ProjectHeader.jsx'
import { Select } from '../../components/Select.jsx'
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

/**
 * 108 AC27: the Label filter with its own Save, sent trimmed by the server (blank clears it). A save says `Saved.` and
 * `onSaved` reloads; a refusal shows as an alert and keeps what was typed.
 */
function IssueLabel({ project, onSaved }) {
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  async function submit(event) {
    event.preventDefault()
    const form = event.currentTarget
    setBusy(true)
    setSaved(false)
    try {
      const out = await patchProject(project.id, { github_label: form.elements.namedItem('github_label').value })
      setError(null)
      form.elements.namedItem('github_label').value = out.github_label ?? ''
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={submit} onInput={() => setSaved(false)} className="grid gap-2">
      <div className="flex flex-wrap items-center gap-3">
        <label htmlFor="github-label">Label</label>
        <input
          id="github-label"
          name="github_label"
          defaultValue={project.github_label ?? ''}
          placeholder="all open issues"
          className={`${field} w-full max-w-xs`}
        />
        <button disabled={busy} className={button}>
          Save
        </button>
        <span aria-live="polite" className={muted}>
          {saved ? 'Saved.' : ''}
        </span>
      </div>
      {error && <ErrorMessage error={error} />}
    </form>
  )
}

/**
 * 108 AC28–AC30: Sync now, disabled while pending and without a github.com origin (whose hint shows instead). A 200 says
 * the counts in a polite region and `onSynced` reloads; a refusal shows as an alert and doesn't. The region is cleared
 * as a sync starts, so an identical result is announced again.
 */
function GithubIssues({ project, onSynced }) {
  const [result, setResult] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const repo = project.github_repo
  async function sync() {
    setBusy(true)
    setResult('')
    setError(null)
    try {
      const out = await syncGithubIssues(project.id)
      setResult(`Synced GitHub issues: ${out.new} new, ${out.updated} updated, ${out.skipped} skipped`)
      onSynced()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <p className={muted}>
        {repo ? `Open issues of ${repo} as Backlog tasks, through your gh login.` : project.github_hint}
      </p>
      <IssueLabel project={project} onSaved={onSynced} />
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={sync} disabled={busy || !repo} className={button}>
          Sync now
        </button>
        <p aria-live="polite" className={`m-0 ${muted}`}>
          {result}
        </p>
      </div>
      {error && <ErrorMessage error={error} />}
    </>
  )
}

const PLANE_URL = 'https://api.plane.so' // 109 AC4: a null plane_api_url shows as Plane's cloud

/**
 * 109 AC17, AC18: API URL, Workspace slug, Project ID, the API key, and Mark done in Plane, with one Save (PATCH, `Saved.`,
 * reload; a refusal is an alert and keeps what was typed). The key is write-only: page data says only plane_key_set, so
 * the field is an empty password input, or `API key: set` with Replace (an empty input Save sends) and Clear. Save sends
 * the key only when one was typed.
 */
function PlaneForm({ project, onSaved }) {
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const [replacing, setReplacing] = useState(false)
  const askKey = !project.plane_key_set || replacing
  async function save(fields, form) {
    setBusy(true)
    setSaved(false)
    try {
      const out = await patchProject(project.id, fields)
      setError(null)
      if (form) {
        form.elements.namedItem('plane_api_url').value = out.plane_api_url ?? PLANE_URL
        form.elements.namedItem('plane_workspace').value = out.plane_workspace ?? ''
        form.elements.namedItem('plane_project_id').value = out.plane_project_id ?? ''
        const key = form.elements.namedItem('plane_api_key')
        if (key) key.value = ''
      }
      setReplacing(false)
      setSaved(true)
      onSaved()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }
  function submit(event) {
    event.preventDefault()
    const form = event.currentTarget
    const value = (name) => form.elements.namedItem(name).value
    const fields = {
      plane_api_url: value('plane_api_url'),
      plane_workspace: value('plane_workspace'),
      plane_project_id: value('plane_project_id'),
      plane_mark_done: form.elements.namedItem('plane_mark_done').checked,
    }
    const key = form.elements.namedItem('plane_api_key')?.value
    if (key) fields.plane_api_key = key
    save(fields, form)
  }
  const rows = [
    ['plane-url', 'plane_api_url', 'API URL', project.plane_api_url ?? PLANE_URL, 'font-mono text-sm/6'],
    ['plane-workspace', 'plane_workspace', 'Workspace slug', project.plane_workspace ?? '', ''],
    ['plane-project', 'plane_project_id', 'Project ID', project.plane_project_id ?? '', 'font-mono text-sm/6'],
  ]
  return (
    <form onSubmit={submit} onInput={() => setSaved(false)} className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-6 gap-y-2">
      {rows.map(([id, name, label, value, extra]) => (
        <div key={id} className="contents">
          <label htmlFor={id} className={muted}>
            {label}
          </label>
          <input id={id} name={name} defaultValue={value} className={`${field} w-full max-w-md ${extra}`} />
        </div>
      ))}
      {askKey ? (
        <>
          <label htmlFor="plane-key" className={muted}>
            API key
          </label>
          <input
            id="plane-key"
            name="plane_api_key"
            type="password"
            autoComplete="off"
            placeholder={replacing ? 'the new key' : 'not set'}
            className={`${field} w-full max-w-md`}
          />
        </>
      ) : (
        <>
          <span className={muted}>API key</span>
          <div className="flex flex-wrap items-center gap-3">
            <span>API key: set</span>
            <button type="button" onClick={() => setReplacing(true)} disabled={busy} className={button}>
              Replace
            </button>
            <button type="button" onClick={() => save({ plane_api_key: '' })} disabled={busy} className={button}>
              Clear
            </button>
          </div>
        </>
      )}
      <div className="col-start-2 flex items-center gap-2">
        <input id="plane-mark-done" name="plane_mark_done" type="checkbox" defaultChecked={project.plane_mark_done} />
        <label htmlFor="plane-mark-done">Mark done in Plane</label>
      </div>
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

/**
 * 109 AC19: Sync now, disabled until the URL, slug and project ID are saved and a key is set, and while pending. A 200
 * says the counts in a polite region (cleared as a sync starts) and `onSynced` reloads; a refusal is an alert.
 */
function Plane({ project, onSynced }) {
  const [result, setResult] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const ready = Boolean(project.plane_api_url && project.plane_workspace && project.plane_project_id && project.plane_key_set)
  async function sync() {
    setBusy(true)
    setResult('')
    setError(null)
    try {
      const out = await syncPlane(project.id)
      setResult(`Synced Plane: ${out.new} new, ${out.updated} updated, ${out.skipped} skipped`)
      onSynced()
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <p className={muted}>
        Backlog and unstarted work items of a Plane project as Backlog tasks; with Mark done in Plane, approving one sets
        its item to the project&apos;s first completed state.
      </p>
      <PlaneForm project={project} onSaved={onSynced} />
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={sync} disabled={busy || !ready} className={button}>
          Sync now
        </button>
        <p aria-live="polite" className={`m-0 ${muted}`}>
          {result}
        </p>
      </div>
      {error && <ErrorMessage error={error} />}
    </>
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
      {/* 107 Q2: named by its span, not a wrapping label, which would add the option's text to its name */}
      <div className="flex items-center gap-2">
        <span id={`move-${project.id}-workspace`}>Workspace</span>
        <Select
          aria-labelledby={`move-${project.id}-workspace`}
          name="workspace_id"
          defaultValue={project.workspace_id}
          options={workspaces.map((w) => ({ value: w.id, label: w.name }))}
        />
      </div>
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

/**
 * docs/ui.md §8 item 12. Q6: loaded once, and reloaded after Save, Create factory, Import, Sync factory/, Move, and
 * (108) the GitHub label's Save and Sync now, and (109) the Plane section's Save, Clear, and Sync now.
 */
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
    if (name) document.title = `${name} · Settings · Workcell`
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
        <Section id="settings-github" title="GitHub issues">
          <GithubIssues project={project} onSynced={refresh} />
        </Section>
        <Section id="settings-plane" title="Plane">
          <Plane project={project} onSynced={refresh} />
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
