import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { addFactory, deleteFactory, listFactories, listTemplates, runAutomation, saveFactory } from '../../api/factories.js'
import { boardPage } from '../../api/pages.js'
import { ActionButton } from '../../components/ActionButton.jsx'
import { DeleteDialog } from '../../components/DeleteDialog.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { ProjectHeader } from '../../components/ProjectHeader.jsx'
import { Rename } from '../../components/Rename.jsx'
import { RunMenu, runsOff } from '../../components/RunMenu.jsx'
import { Block, ButtonBlock, ProjectHeaderSkeleton, Skeleton } from '../../components/Skeleton.jsx'
import { Time } from '../../components/Time.jsx'
import { button, field, muted, popover, smallButton } from '../../components/styles.js'
import { usePoll } from '../../hooks/usePoll.js'

/** Q16: what Delete removes, and what stays. */
const DELETE_TEXT =
  "This removes the factory's design from the app. Files in the repo, such as the ones Create factory wrote, stay."

/**
 * 101, docs/ui.md §8 item 14: the page's two sections, by a design's fixed kind (Q4's labels). `id` is the section's
 * + New popover; Delete's focus goes back to its opener (AC16). AC15: each has its own anchor, written out in full so
 * Tailwind sees the classes.
 */
const SECTIONS = [
  {
    kind: 'workflow', title: 'Workflows', noun: 'workflow', empty: 'No workflows yet.', id: 'new-workflow',
    anchor: '[anchor-name:--new-workflow]', anchored: '[position-anchor:--new-workflow]',
  },
  {
    kind: 'automation', title: 'Automations', noun: 'automation', empty: 'No automations yet.', id: 'new-automation',
    anchor: '[anchor-name:--new-automation]', anchored: '[position-anchor:--new-automation]',
  },
]

/**
 * FE3, Q15: + New's native popover, like + New task. The server judges the name (blank, taken), and its refusal shows
 * inside, which stays open with what was typed; a 201 opens the designer. 088 Q6: `templates` ({data, error}) are
 * radios with their descriptions. 101 Q1: only the section's kind's templates, Standard checked, else the first; with
 * none (Q8), the POST's template is null, which is Standard.
 */
function NewFactory({ projectId, templates, section }) {
  const { kind, noun, id, anchor, anchored } = section
  const navigate = useNavigate()
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const offered = templates.data?.filter((t) => t.kind === kind) ?? []
  const checked = offered.find((t) => t.key === 'standard')?.key ?? offered[0]?.key
  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    const form = new FormData(event.currentTarget)
    try {
      const made = await addFactory(projectId, form.get('name'), form.get('template'), kind)
      navigate(`/projects/${projectId}/factories/${made.id}`)
    } catch (err) {
      setError(err)
      setBusy(false)
    }
  }
  return (
    <>
      <button type="button" popoverTarget={id} className={`${button} ${anchor}`}>
        {`+ New ${noun}`}
      </button>
      <div
        id={id}
        popover="auto"
        className={`${popover} w-96 max-w-[90vw] p-3 ${anchored} [position-area:bottom_span-left]`}
      >
        <form onSubmit={submit} className="grid gap-2">
          <label className="grid gap-1">
            Name
            {/* board Q10: the autofocus attribute, which the popover focuses as it opens */}
            <input ref={(el) => el?.setAttribute('autofocus', '')} type="text" name="name" className={field} />
          </label>
          <fieldset className="grid gap-2">
            <legend className="mb-1">Template</legend>
            {templates.error ? (
              <ErrorMessage error={templates.error} />
            ) : (
              offered.map(({ key, name, description }) => (
                <div key={key} className="grid grid-cols-[auto_minmax(0,1fr)] items-baseline gap-x-2">
                  <input
                    id={`${id}-template-${key}`}
                    type="radio"
                    name="template"
                    value={key}
                    defaultChecked={key === checked}
                    aria-describedby={`${id}-template-${key}-note`}
                  />
                  <label htmlFor={`${id}-template-${key}`} className="font-medium">
                    {name}
                  </label>
                  <p id={`${id}-template-${key}-note`} className={`col-start-2 text-sm ${muted}`}>
                    {description}
                  </p>
                </div>
              ))
            )}
          </fieldset>
          <button disabled={busy} className={`${button} justify-self-start`}>
            Create
          </button>
          {error && <ErrorMessage error={error} />}
        </form>
      </div>
    </>
  )
}

/**
 * 102 AC23–AC25: an automation row's **Run now** (Auto) and its own Run menu, built like the task page's. `run` holds
 * the page's accounts, Auto's pick, `off` (why runs can't start, Q11, or null), and `start(factoryId, accountId)`.
 */
function RunNow({ factory, run }) {
  return (
    <>
      <ActionButton
        action={() => run.start(factory.id, null)}
        disabled={!!run.off}
        title={run.off ?? undefined}
        aria-label={`Run ${factory.name} now`}
        className={smallButton}
      >
        Run now
      </ActionButton>
      {run.accounts.length > 0 && (
        <RunMenu
          id={`run-menu-${factory.id}`}
          label={`Choose account for ${factory.name}`}
          accounts={run.accounts}
          auto={run.auto}
          disabled={!!run.off}
          title={run.off ?? undefined}
          onRun={(accountId) => run.start(factory.id, accountId)}
        />
      )}
    </>
  )
}

/**
 * FE2, FE4: a factory's row. Rename swaps the name for the 049 field; after a save or Esc, focus is back on Rename.
 * 102: an automation's row starts with Run now; a workflow's runs on board tasks, so it has none.
 */
function FactoryRow({ projectId, factory, run, onReload, onDelete }) {
  const [renaming, setRenaming] = useState(false)
  const rename = useRef(null)
  const n = factory.nodes
  return (
    <tr>
      <td className="wrap-anywhere">
        {renaming ? (
          <Rename
            label={`Rename ${factory.name}`}
            name={factory.name}
            save={async (name) => {
              await saveFactory(factory.id, { name })
              onReload()
            }}
            onClose={(focus) => {
              setRenaming(false)
              if (focus) rename.current.focus()
            }}
          />
        ) : (
          <Link to={`/projects/${projectId}/factories/${factory.id}`}>{factory.name}</Link>
        )}
      </td>
      <td className={`tabular-nums ${muted}`}>{`${n} ${n === 1 ? 'node' : 'nodes'}`}</td>
      <td className={muted}>
        <Time iso={factory.updated_at} relative />
      </td>
      <td>
        <div className="flex justify-end gap-2">
          {factory.kind === 'automation' && <RunNow factory={factory} run={run} />}
          {/* 103 AC23: an automation's runs page; a workflow's runs are on its tasks */}
          {factory.kind === 'automation' && (
            <Link
              to={`/projects/${projectId}/factories/${factory.id}/runs`}
              aria-label={`Runs of ${factory.name}`}
              className={`${smallButton} hover:no-underline`}
            >
              Runs
            </Link>
          )}
          <button
            ref={rename}
            type="button"
            aria-label={`Rename ${factory.name}`}
            onClick={() => setRenaming(true)}
            className={smallButton}
          >
            Rename
          </button>
          <button
            type="button"
            aria-label={`Delete ${factory.name}`}
            onClick={(event) => onDelete(factory, event.currentTarget)}
            className={`${smallButton} text-danger`}
          >
            Delete
          </button>
        </div>
      </td>
    </tr>
  )
}

/**
 * 101 AC11, AC12: one kind's section: its h2 and + New, then its table or its own empty text. 102 AC25, Q11: with rows
 * to run, the Automations section says once why Run now is off.
 */
function Section({ section, projectId, factories, templates, run, onReload, onDelete }) {
  const heading = `${section.id}-heading`
  return (
    <section aria-labelledby={heading} className="mb-8">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 id={heading}>{section.title}</h2>
        <NewFactory projectId={projectId} templates={templates} section={section} />
      </div>
      {section.kind === 'automation' && run.off && factories.length > 0 && (
        <p className={`mb-2 text-sm ${muted}`}>{run.off}</p>
      )}
      {factories.length ? (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th>Name</th>
                <th>Nodes</th>
                <th>Updated</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {factories.map((factory) => (
                <FactoryRow
                  key={factory.id}
                  projectId={projectId}
                  factory={factory}
                  run={run}
                  onReload={onReload}
                  onDelete={onDelete}
                />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className={muted}>{section.empty}</p>
      )}
    </section>
  )
}

/** 046 Q5: the header, then per section its heading and + New, the table's head, and a row. */
function FactoriesSkeleton() {
  return (
    <Skeleton>
      <ProjectHeaderSkeleton />
      {SECTIONS.map(({ kind }) => (
        <div key={kind} className="mb-8 grid gap-3">
          <div className="flex items-center justify-between gap-2">
            <Block className="h-7 w-40" />
            <ButtonBlock className="w-36" />
          </div>
          <Block className="h-7 w-full" />
          <Block className="h-7 w-full" />
        </div>
      ))}
    </Skeleton>
  )
}

/**
 * docs/ui.md §8 item 14. Q18: the header's board view-model, the list, and (088) the templates load once each; the list
 * reloads after an action. 101: the list splits into the Workflows and Automations sections by kind. 102: Run now's
 * refusal shows in the page alert, emptied as the next one starts (AC26); a start says so politely, with a link to
 * Agents, and reloads the board view-model and the list (AC27, Q13).
 */
function Factories({ id }) {
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((n) => n + 1), [])
  // board Q3: `tick` is in the deps only to hand usePoll a new load, which fetches at once
  const { data: page, error: pageError } = usePoll(useCallback(() => boardPage(id), [id, tick]))
  const [runError, setRunError] = useState(null)
  const [started, setStarted] = useState(null)
  // board Q3: `tick` is in the deps only to hand usePoll a new load, which fetches at once
  const { data: factories, error } = usePoll(useCallback(() => listFactories(id), [id, tick]))
  const templates = usePoll(listTemplates) // 088 AC14: once, beside the two; its failure stays in the popover (AC17)
  const [deleting, setDeleting] = useState(null) // {factory, opener}
  const name = page?.project.name
  useEffect(() => {
    if (name) document.title = `${name} · Workflows · Claude Factories`
  }, [name])

  const missing = [pageError, error].find((e) => e?.status === 404)
  if (missing) return <NotFound detail={missing.message} />
  if (!page || !factories) {
    const failed = pageError ?? error
    return failed ? <ErrorMessage error={failed} /> : <FactoriesSkeleton />
  }
  const sectionOf = (factory) => SECTIONS.find((s) => s.kind === factory.kind) ?? SECTIONS[0]
  const run = {
    accounts: page.accounts ?? [],
    auto: page.auto,
    off: runsOff(page),
    async start(factoryId, accountId) {
      setRunError(null)
      setStarted(null)
      try {
        setStarted(await runAutomation(factoryId, accountId))
      } catch (err) {
        setRunError(err)
        return
      }
      reload()
    },
  }
  return (
    <>
      <ProjectHeader project={page.project} factory={page.factory} />
      {error && <ErrorMessage error={error} />}
      {runError && <ErrorMessage error={runError} />}
      <div role="status" className="mb-4 empty:hidden">
        {started && (
          <>
            {`Started run #${started.run_id}${started.account ? ` as ${started.account}` : ''}. `}
            <Link to="/agents">Open Agents</Link>
          </>
        )}
      </div>
      {SECTIONS.map((section) => (
        <Section
          key={section.kind}
          section={section}
          projectId={page.project.id}
          factories={factories.filter((f) => sectionOf(f) === section)}
          templates={templates}
          run={run}
          onReload={reload}
          onDelete={(f, opener) => setDeleting({ factory: f, opener })}
        />
      ))}
      {deleting && (
        <DeleteDialog
          title={`Delete ${sectionOf(deleting.factory).noun} ${deleting.factory.name}?`}
          text={DELETE_TEXT}
          remove={() => deleteFactory(deleting.factory.id)}
          onDeleted={reload}
          onClose={(deleted) => {
            setDeleting(null)
            // the row is gone, so focus goes to its section's + New (101 AC16), as the board's delete does
            const next = deleted
              ? document.querySelector(`[popovertarget="${sectionOf(deleting.factory).id}"]`)
              : deleting.opener
            next?.focus()
          }}
        />
      )}
    </>
  )
}

/** Keyed by id, so another project's list starts with no dialog or rename open. */
export function FactoriesPage() {
  const { id } = useParams()
  return <Factories key={id} id={id} />
}
