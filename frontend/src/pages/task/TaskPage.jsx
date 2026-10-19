import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router'
import { taskPage } from '../../api/pages.js'
import { runLog, runTask, stopRun } from '../../api/runs.js'
import { exportUrl } from '../../api/tasks.js'
import { ActionButton } from '../../components/ActionButton.jsx'
import { AgentStats, agentLabel } from '../../components/AgentStats.jsx'
import { Chip } from '../../components/Chip.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { Markdown } from '../../components/Markdown.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { StatusLine } from '../../components/StatusLine.jsx'
import { Time } from '../../components/Time.jsx'
import { usePoll } from '../../hooks/usePoll.js'

const muted = 'text-gray-600 dark:text-gray-400'
const blank = (md) => !md?.trim()

/**
 * Q3: Stop while the latest run runs, whatever the status; else Run for backlog, Retry for in_progress with a run.
 * `can_run` disables Run and Retry, never Stop, and the hint shows only beside them.
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
      {run && (
        <span>
          {`run #${run.id} ${run.status}`}
          {running && (
            <>
              {' · started '}
              <Time iso={run.started_at} timeOnly />
            </>
          )}
          {run.status === 'failed' && run.error && `: ${run.error}`}
        </span>
      )}
      {start && hint && <span className={`text-sm ${muted}`}>{hint}</span>}
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
          className="m-auto w-[min(42rem,90vw)] rounded-lg border border-gray-300 p-4 shadow-lg dark:border-gray-700"
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
          <Markdown html={round.build_html} className="mt-2 border-l-2 border-gray-200 pl-3 dark:border-gray-700" />
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

/**
 * Q5: the run's log as text, from `after=0`. usePoll fetches every 3 s while the run is running and once
 * otherwise, so the run stopping gives one last fetch. Keyed by run id, so a new run starts a fresh cursor.
 * ponytail: the whole log stays in memory and in the DOM; window it if logs get big.
 */
function RunLog({ run }) {
  const [lines, setLines] = useState([])
  const cursor = useRef(0)
  const box = useRef(null)
  const load = useCallback(async () => {
    const after = cursor.current
    const reply = await runLog(run.id, after).catch(() => null) // a failed fetch shows nothing; the next poll retries
    if (!reply || cursor.current !== after) return // the cursor moved: an overlapping fetch already appended these
    cursor.current = reply.next
    if (reply.lines.length) setLines((old) => [...old, ...reply.lines])
  }, [run.id])
  usePoll(load, run.status === 'running' ? 3000 : undefined)
  const end = () => {
    box.current.scrollTop = box.current.scrollHeight
  }
  useEffect(end, [lines])
  return (
    <details onToggle={end} className="mt-8">
      <summary className="cursor-pointer font-semibold">{`Run log · run #${run.id}`}</summary>
      <div
        ref={box}
        className="mt-2 max-h-96 overflow-auto rounded-md bg-gray-100 p-3 font-mono text-sm whitespace-pre-wrap wrap-anywhere dark:bg-gray-900"
      >
        {lines.length ? lines.map((line, i) => <div key={i}>{line.text}</div>) : <p className={muted}>No output yet.</p>}
      </div>
    </details>
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
  const [withTranscripts, setWithTranscripts] = useState(false) // 032 Q10: Export leaves them out unless ticked
  const heading = page && `#${page.task.id} ${page.task.title}`
  useEffect(() => {
    if (heading) document.title = `${heading} · Claude Factories`
  }, [heading])

  // Q10: a 404 is always not-found; other errors replace the page only until the first good load
  if (error?.status === 404) return <NotFound detail={error.message} />
  if (!page) return error ? <ErrorMessage error={error} /> : <p className={muted}>Loading…</p>
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
        <nav aria-label="Breadcrumb" className="text-sm">
          <Link to={`/projects/${task.project_id}`}>{task.project}</Link>
        </nav>
        <h1 className="text-2xl font-semibold wrap-anywhere">{heading}</h1>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <StatusLine task={task} />
          {task.branch && <code className="text-sm wrap-anywhere">{task.branch}</code>}
          <Link to={`/tasks/${task.id}/review`}>Review</Link>
          <a href={exportUrl(task.id, withTranscripts)} download>
            Export
          </a>
          <label className="flex items-center gap-1 text-sm">
            <input type="checkbox" checked={withTranscripts} onChange={(event) => setWithTranscripts(event.target.checked)} />
            Include transcripts <span className={muted}>(can hold paths, env, and secrets)</span>
          </label>
        </p>
        <RunControls page={page} onAction={runAction} />
        {actionError && <ErrorMessage error={actionError} />}
        <Takeover page={page} />
      </header>
      {error && <ErrorMessage error={error} />}
      <section aria-labelledby="task-description">
        <h2 id="task-description">Description</h2>
        {blank(task.description_md) ? <p className={muted}>No description.</p> : <Markdown html={task.description_html} />}
      </section>
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
        <section aria-label="Approver" className="mt-8 rounded-md border border-gray-200 p-3 dark:border-gray-800">
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
              <Time iso={entry.created_at} /> {entry.label}
            </li>
          ))}
        </ol>
      </section>
      {page.run && <RunLog key={page.run.id} run={page.run} />}
    </>
  )
}
