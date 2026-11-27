import { Fragment, useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { listModules } from '../../api/modules.js'
import { taskPage } from '../../api/pages.js'
import { runTask, stopRun } from '../../api/runs.js'
import { blockTask, exportUrl, setTaskModule, unblockTask } from '../../api/tasks.js'
import { ActionButton } from '../../components/ActionButton.jsx'
import { AgentStats, agentLabel } from '../../components/AgentStats.jsx'
import { ModulePill, StatusPill, TaskState } from '../../components/Badge.jsx'
import { Breadcrumbs, projectTrail } from '../../components/Breadcrumbs.jsx'
import { Chip } from '../../components/Chip.jsx'
import { ErrorMessage, OfflineBanner } from '../../components/ErrorMessage.jsx'
import { Markdown } from '../../components/Markdown.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { PullRequest } from '../../components/PullRequest.jsx'
import { RunLog } from '../../components/RunLog.jsx'
import { RunMenu } from '../../components/RunMenu.jsx'
import { Select } from '../../components/Select.jsx'
import { Block, ButtonBlock, Crumbs, Lines, Skeleton, TitleSkeleton } from '../../components/Skeleton.jsx'
import { button, muted, popover, smallButton } from '../../components/styles.js'
import { Time } from '../../components/Time.jsx'
import { usePoll } from '../../hooks/usePoll.js'
import { TaskFlow } from './TaskFlow.jsx'

const blank = (md) => !md?.trim()

/**
 * Q3: Stop while the latest run runs, whatever the status; else Run for backlog, Retry for in_progress with a run.
 * `can_run` disables Run and Retry, never Stop, and the hint shows only beside them. 047 Q8: on the title row, which wraps.
 * 097: Run and Retry are Auto; the Run menu beside them (with any accounts) picks one. The run line names its account.
 */
function RunControls({ page, onAction }) {
  const { task, run, hint } = page
  const running = run?.status === 'running'
  const start = running ? null : task.status === 'backlog' ? 'Run' : task.status === 'in_progress' && run ? 'Retry' : null
  if (!run && !start) return null
  return (
    <div className="flex flex-wrap items-center gap-3">
      {running && <ActionButton action={() => onAction(() => stopRun(run.id))}>Stop</ActionButton>}
      {start && (
        <ActionButton action={() => onAction(() => runTask(task.id))} disabled={!page.can_run}>
          {start}
        </ActionButton>
      )}
      {start && page.accounts?.length > 0 && (
        <RunMenu
          id="run-menu"
          accounts={page.accounts}
          auto={page.auto}
          disabled={!page.can_run}
          onRun={(id) => onAction(() => runTask(task.id, id))}
        />
      )}
      {run && (
        <span>
          {`run #${run.id} ${run.status}`}
          {run.account && ` · ${run.account}`}
          {running && (
            <>
              {' · started '}
              <Time iso={run.started_at} relative />
            </>
          )}
          {run.status === 'failed' && run.error && `: ${run.error}`}
        </span>
      )}
      {start && hint && <span className={`text-sm ${muted}`}>{hint}</span>}
    </div>
  )
}

/**
 * 047 Q9: the Export button's popover, holding the Include transcripts box (032 Q10: off unless ticked) and one Download
 * link. Esc or a click outside closes it; a download leaves it open. It sits after the status line, not in it (FE7): the
 * browser draws it in the top layer under its button, and puts it after the button in tab order.
 */
function ExportPopover({ id }) {
  const [withTranscripts, setWithTranscripts] = useState(false)
  return (
    <div
      id="export"
      popover="auto"
      className={`${popover} w-80 max-w-[90vw] gap-3 p-3 open:grid [position-anchor:--export] [position-area:bottom_span-right]`}
    >
      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={withTranscripts}
          onChange={(event) => setWithTranscripts(event.target.checked)}
          className="mt-1"
        />
        <span>
          Include transcripts <span className={muted}>(can hold paths, env, and secrets)</span>
        </span>
      </label>
      <a href={exportUrl(id, withTranscripts)} download className={`${button} justify-self-start hover:no-underline`}>
        Download
      </a>
    </div>
  )
}

/**
 * 094 AC25–AC27: Blocked by lists every link, done ones too, each with Remove; Add picks from the shared Select (107) of
 * the project's other tasks (Q8), minus the current blockers. Both reload the page; a refusal shows inside the section,
 * and the pick, kept in state while this stays mounted, survives it and polls. Blocks is read-only (Q9).
 * 107 Q5: a pick that became a blocker falls back to the first choice, as a native select's did.
 */
function Dependencies({ page, onChange }) {
  const { task, blocked_by: blockers, blocks } = page
  const [error, setError] = useState(null)
  const [picked, setPicked] = useState(null)
  const taken = new Set(blockers.map((b) => b.id))
  const choices = page.project_tasks.filter((t) => !taken.has(t.id))
  const shown = choices.find((t) => t.id === picked) ?? choices[0]
  async function change(call) {
    setError(null)
    try {
      await call()
    } catch (err) {
      setError(err)
      return
    }
    onChange()
  }
  return (
    <>
      <section aria-labelledby="task-blocked-by">
        <h2 id="task-blocked-by">Blocked by</h2>
        {blockers.length ? (
          <ul className="grid gap-1">
            {blockers.map((b) => (
              <li key={b.id} className="flex flex-wrap items-center gap-2">
                <Link to={`/tasks/${b.id}`}>{`#${b.id}`}</Link>
                <span className="wrap-anywhere">{b.title}</span>
                <StatusPill status={b.status} />
                <ActionButton
                  action={() => change(() => unblockTask(task.id, b.id))}
                  className={smallButton}
                  aria-label={`Remove #${b.id}`}
                >
                  Remove
                </ActionButton>
              </li>
            ))}
          </ul>
        ) : (
          <p className={muted}>No blockers.</p>
        )}
        {choices.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {/* htmlFor, not a wrapping label, so the picked option isn't part of the select's name */}
            <label htmlFor="blocker-pick">Wait on</label>
            <Select
              id="blocker-pick"
              value={shown.id}
              onChange={(value) => setPicked(Number(value))}
              options={choices.map((t) => ({ value: t.id, label: `#${t.id} ${t.title}` }))}
              className="max-w-full"
            />
            <ActionButton action={() => change(() => blockTask(task.id, String(shown.id)))} className={smallButton}>
              Add
            </ActionButton>
          </div>
        )}
        {error && <ErrorMessage error={error} />}
      </section>
      <section aria-labelledby="task-blocks">
        <h2 id="task-blocks">Blocks</h2>
        {blocks.length ? (
          <ul className="grid gap-1">
            {blocks.map((d) => (
              <li key={d.id}>
                <Link to={`/tasks/${d.id}`}>{`#${d.id}`}</Link> <span className="wrap-anywhere">{d.title}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className={muted}>Blocks nothing.</p>
        )}
      </section>
    </>
  )
}

/**
 * 112 AC22, Q6: the task's module, picked from No module and the project's modules, loaded once. A change PATCHes
 * `module_id` and reloads the page; a refusal shows beside it. The value follows the page, so a poll shows the stored one.
 */
function ModuleField({ task, onChange }) {
  const { data } = usePoll(useCallback(() => listModules(task.project_id), [task.project_id]))
  const [error, setError] = useState(null)
  const listed = data?.modules ?? (task.module ? [task.module] : [])
  async function pick(value) {
    setError(null)
    try {
      await setTaskModule(task.id, value ? Number(value) : null)
    } catch (err) {
      setError(err)
      return
    }
    onChange()
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label htmlFor="task-module">Module</label>
      <Select
        id="task-module"
        value={task.module ? String(task.module.id) : ''}
        onChange={pick}
        options={[{ value: '', label: 'No module' }, ...listed.map((m) => ({ value: String(m.id), label: m.name }))]}
      />
      {error && <ErrorMessage error={error} />}
    </div>
  )
}

/** Q6: the backend's quoted command as is; while a run runs it's null, so say how to get it. */
function Takeover({ page }) {
  if (page.takeover) {
    return (
      <p>
        {'Take over in terminal: '}
        <code className="text-sm wrap-anywhere">{page.takeover}</code>
      </p>
    )
  }
  if (page.run?.status === 'running' && page.task.worktree_path) return <p className={muted}>Stop the run to take over.</p>
  return null
}

/**
 * 030: one row per transcript: its label linking to the transcript page, then its stats. `other` rows (Other agents)
 * also name their run, and their round when it has no Round row yet.
 */
function Agents({ transcripts, label, other = false }) {
  return (
    <ul aria-label={label} className="grid gap-1 text-sm">
      {transcripts.map((t) => (
        <li key={t.id}>
          <Link to={`/transcripts/${t.id}`}>{agentLabel(t)}</Link>
          {other && ` · run #${t.run_id}${t.round != null ? ` · round ${t.round}` : ''}`}
          <span className={muted}>
            {' · '}
            <AgentStats t={t} />
          </span>
        </li>
      ))}
    </ul>
  )
}

/**
 * `Round n trigger chips +A −D`, the verdict popovers, the build notes, and the round's agents (030). Q2: keyed by `n` with chips keyed
 * by reviewer and an uncontrolled <details>, so open notes and popovers survive the polls.
 * claude-code.md §7.4: a standalone task (no worktree) with nothing posted says "no agent review".
 */
function Round({ round, standalone, agents }) {
  const { n, posted } = round
  const bodies = Object.entries(posted).filter(([, p]) => !blank(p.body_md))
  return (
    <li>
      <p>
        <strong>{`Round ${n}`}</strong> <span className={muted}>{round.trigger}</span>
        {standalone && Object.keys(posted).length === 0 ? (
          <>
            {' '}
            <span className={muted}>no agent review</span>
          </>
        ) : (
          Object.entries(round.verdicts).map(([who, verdict]) => (
            <Fragment key={who}>
              {' '}
              <Chip n={n} who={who} verdict={verdict} posted={posted[who]} />
            </Fragment>
          ))
        )}{' '}
        <span className={`tabular-nums ${muted}`}>{`+${round.additions} −${round.deletions}`}</span>
      </p>
      {bodies.map(([who, p]) => (
        <div
          key={who}
          id={`verdict-${n}-${who}`}
          popover="auto"
          className="m-auto w-[min(42rem,90vw)] rounded-lg border border-line bg-surface p-4 text-fg shadow-lg"
        >
          <p className="font-semibold">{`${who} · ${p.verdict}`}</p>
          <Markdown html={p.body_html} className="mt-2" />
        </div>
      ))}
      {blank(round.build_md) ? (
        <p className={`text-sm ${muted}`}>No build notes.</p>
      ) : (
        <details className="mt-1">
          <summary className="cursor-pointer text-sm">Build notes</summary>
          <Markdown html={round.build_html} className="mt-2 border-l-2 border-line pl-3" />
        </details>
      )}
      {agents.length > 0 && (
        <div className="mt-1">
          <p className={`text-sm ${muted}`}>Agents</p>
          <Agents transcripts={agents} label={`Round ${n} agents`} />
        </div>
      )}
    </li>
  )
}

/** 046 Q5: the header (breadcrumb, title with a run button, status line), then the Description heading and text. */
function TaskSkeleton() {
  return (
    <Skeleton>
      <TitleSkeleton title={<ButtonBlock className="w-16" />}>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <Block className="h-6 w-24" />
          <Crumbs className="w-48" />
          <Block className="h-6 w-14" />
          <Block className="h-6.5 w-20" />
        </div>
      </TitleSkeleton>
      <Block className="mt-8 mb-2 h-7 w-32" />
      <Lines n={3} />
    </Skeleton>
  )
}

/** docs/ui.md §8 item 4: one task, its rounds, its history, and its latest run. */
export function TaskPage() {
  const { id } = useParams()
  // 022 Q3: bumping `tick` gives usePoll a new load function, which restarts its loop with a fetch at once;
  // `tick` is in the deps for that alone
  const [tick, setTick] = useState(0)
  const refresh = useCallback(() => setTick((n) => n + 1), [])
  const load = useCallback(() => taskPage(id), [id, tick])
  const { data: page, error } = usePoll(load, 3000)
  const [actionError, setActionError] = useState(null)
  const heading = page && `#${page.task.id} ${page.task.title}`
  useEffect(() => {
    if (heading) document.title = `${heading} · Workcell`
  }, [heading])

  // Q10: a 404 is always not-found; other errors replace the page only until the first good load
  if (error?.status === 404) return <NotFound detail={error.message} />
  if (!page) return error ? <ErrorMessage error={error} /> : <TaskSkeleton />
  const { task } = page
  // Q4: no round, or a round with no Round row yet (a build that hasn't submitted), goes under Other agents
  const rounds = new Set(page.rounds.map((r) => r.n))
  const other = page.transcripts.filter((t) => !rounds.has(t.round))

  /** Q4: a success clears the alert and refetches at once; a refusal shows in it, and the 3 s poll catches up. */
  async function runAction(call) {
    try {
      await call()
    } catch (err) {
      setActionError(err)
      return
    }
    setActionError(null)
    refresh()
  }

  return (
    <>
      <header className="mb-6 grid gap-2">
        <Breadcrumbs items={[...projectTrail(task), { label: `#${task.id}` }]} />
        {/* 047: the title row; the run controls sit at its end, and wrap under the title when it's long. 093 Q1: the
            PR's buttons beside them */}
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <h1 className="mr-auto wrap-anywhere">{heading}</h1>
          <RunControls page={page} onAction={runAction} />
          {page.pr && <PullRequest key={task.id} taskId={task.id} pr={page.pr} onChange={refresh} />}
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <TaskState task={task} />
          {task.module && <ModulePill name={task.module.name} />}
          {task.branch && <code className="text-sm wrap-anywhere">{task.branch}</code>}
          {/* 108 AC23: the GitHub issue the task was synced from */}
          {task.issue_url && (
            <a href={task.issue_url} target="_blank" rel="noopener noreferrer">
              {`Issue #${task.issue_url.split('/').at(-1)}`}
            </a>
          )}
          <Link to={`/tasks/${task.id}/review`}>Review</Link>
          <button type="button" popoverTarget="export" className={`${smallButton} [anchor-name:--export]`}>
            Export <span aria-hidden="true">▾</span>
          </button>
        </div>
        <ExportPopover id={task.id} />
        <ModuleField key={task.id} task={task} onChange={refresh} />
        {actionError && <ErrorMessage error={actionError} />}
        <Takeover page={page} />
      </header>
      {error && <OfflineBanner />}
      {/* 089: the factory graph; it renders nothing for a standalone task or until its first load */}
      <TaskFlow key={task.id} taskId={task.id} running={page.run?.status === 'running'} />
      <section aria-labelledby="task-description">
        <h2 id="task-description">Description</h2>
        {blank(task.description_md) ? <p className={muted}>No description.</p> : <Markdown html={task.description_html} />}
      </section>
      <Dependencies page={page} onChange={refresh} />
      <section aria-labelledby="task-spec">
        <h2 id="task-spec">Spec</h2>
        {blank(task.spec_md) ? <p className={muted}>No spec yet.</p> : <Markdown html={task.spec_html} />}
      </section>
      <section aria-labelledby="task-rounds">
        <h2 id="task-rounds">Rounds</h2>
        {page.rounds.length ? (
          <ol className="grid gap-3">
            {page.rounds.map((round) => (
              <Round
                key={round.n}
                round={round}
                standalone={task.worktree_path == null}
                agents={page.transcripts.filter((t) => t.round === round.n)}
              />
            ))}
          </ol>
        ) : (
          <p className={muted}>No rounds yet.</p>
        )}
      </section>
      {other.length > 0 && (
        <section aria-labelledby="task-other-agents">
          <h2 id="task-other-agents">Other agents</h2>
          <Agents transcripts={other} label="Other agents" other />
        </section>
      )}
      {page.approver && (
        <section aria-label="Approver" className="mt-8 rounded-md border border-line p-3">
          <p>
            <strong>{`Approver · ${page.approver.decision}`}</strong>{' '}
            <span className={muted}>{`round ${page.approver.n}`}</span>
          </p>
          <Markdown html={page.approver.body_html} className="mt-2" />
        </section>
      )}
      <section aria-labelledby="task-history">
        <h2 id="task-history">Status history</h2>
        <ol className="grid gap-1">
          {page.history.map((entry, i) => (
            <li key={i}>
              <Time iso={entry.created_at} relative /> {entry.label}
            </li>
          ))}
        </ol>
      </section>
      {page.run && <RunLog key={page.run.id} run={page.run} />}
    </>
  )
}
