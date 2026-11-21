import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router'
import { agentsPage } from '../../api/pages.js'
import { stopRun } from '../../api/runs.js'
import { ActionButton } from '../../components/ActionButton.jsx'
import { duration, durationMs } from '../../components/AgentStats.jsx'
import { RunningBadge, Stage } from '../../components/Badge.jsx'
import { ErrorMessage, OfflineBanner } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { Block, ButtonBlock, Skeleton } from '../../components/Skeleton.jsx'
import { muted, smallButton } from '../../components/styles.js'
import { Time } from '../../components/Time.jsx'
import { usePoll } from '../../hooks/usePoll.js'

const TaskLink = ({ id, title, className = '' }) => (
  <Link to={`/tasks/${id}`} className={className}>{`#${id} ${title}`}</Link>
)
const ProjectLink = ({ id, name }) => <Link to={`/projects/${id}`}>{name}</Link>

/**
 * 102 AC28, AC29, Q14: what a run works on. A task run's `#id title` links to the task; an automation run's name links
 * to its designer, and once the automation is deleted (Q9) its `deleted automation` is plain text.
 */
function RunTitle({ run, className }) {
  if (run.kind !== 'automation') return <TaskLink id={run.task_id} title={run.title} className={className} />
  if (run.factory_id == null) return <span className={className}>{run.title}</span>
  return (
    <Link to={`/projects/${run.project_id}/factories/${run.factory_id}`} className={className}>
      {run.title}
    </Link>
  )
}

/** 102 Q9: a deleted automation's run has no project; an empty cell keeps the Recent columns in place. */
const RunProject = ({ run }) => (run.project_id == null ? <span /> : <ProjectLink id={run.project_id} name={run.project} />)

// the Dashboard's group label: a run's kind, small and muted, so `factory` and later kinds read as a tag, not a pill
const kindLabel = `text-xs font-semibold tracking-wide uppercase ${muted}`

/**
 * FE4, Q12: one row per agent, the orchestrator first. From md up the rows share their list's columns (subgrid), each
 * cell at its own column, so a missing type or round leaves a gap instead of shifting the rest; below md they wrap.
 * The type shows only when it differs from the name; the latest tool line is the run log's text, one line, cut with …
 */
function AgentRow({ agent }) {
  const { name, type, round } = agent
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 md:col-span-5 md:grid md:grid-cols-subgrid">
      <span className="font-medium wrap-anywhere md:col-start-1">{name}</span>
      {type && type !== name && <span className={`${muted} md:col-start-2`}>{type}</span>}
      {round != null && <span className={`${muted} md:col-start-3`}>{`round ${round}`}</span>}
      <span className="md:col-start-4">
        {agent.running ? (
          <RunningBadge />
        ) : (
          <span className={`tabular-nums ${muted}`}>
            {agent.duration_ms == null ? 'finished' : `finished · ${durationMs(agent.duration_ms)}`}
          </span>
        )}
      </span>
      {agent.last_tool != null && (
        <code title={agent.last_tool} className={`block min-w-0 truncate text-xs ${muted} max-md:basis-full md:col-start-5`}>
          {agent.last_tool}
        </code>
      )}
    </li>
  )
}

/**
 * FE3, FE4: a running run as a card: what it works on, then when it started, the Run log link, and Stop; under that, on
 * `raised`, its agents. Stage and round are left out when null. `elapsed` is worked out at render, so the 3 s polls tick it.
 */
function RunningRun({ run, onStop }) {
  return (
    <li className="overflow-hidden rounded-md border border-line">
      <div className="grid gap-1.5 px-4 py-3">
        <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className={kindLabel}>{run.kind}</span>
          <RunTitle run={run} className="font-medium wrap-anywhere" />
          {run.project_id != null && (
            <span className="text-sm">
              <ProjectLink id={run.project_id} name={run.project} />
            </span>
          )}
          {(run.stage || run.round != null) && (
            <span className={`inline-flex flex-wrap items-baseline gap-1.5 text-sm ${muted}`}>
              <Stage stage={run.stage} />
              {run.stage && run.round != null && <span aria-hidden="true">·</span>}
              {run.round != null && <span>{`round ${run.round}`}</span>}
            </span>
          )}
        </p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <p className={`mr-auto text-sm tabular-nums ${muted}`}>
            {'started '}
            <Time iso={run.started_at} relative />
            {` · elapsed ${duration(run.started_at, new Date().toISOString())}`}
          </p>
          {/* 102 Q14: an automation run's log has no page yet */}
          {run.kind !== 'automation' && (
            <Link to={`/tasks/${run.task_id}#run-log`} className="text-sm">
              Run log
            </Link>
          )}
          <ActionButton action={() => onStop(run.id)} className={smallButton}>
            Stop
          </ActionButton>
        </div>
      </div>
      <ul
        aria-label={`Agents of run #${run.id}`}
        className="grid gap-y-1.5 border-t border-line bg-raised px-4 py-3 text-sm md:grid-cols-[auto_auto_auto_auto_minmax(0,1fr)] md:gap-x-4"
      >
        {run.agents.map((agent, i) => (
          // the log only appends, and names can repeat (`agent`), so the place is the key
          <AgentRow key={i} agent={agent} />
        ))}
      </ul>
    </li>
  )
}

/**
 * FE7, Q5, Q6: how an ended run went, as plain text; its duration (`—` with no end); its transcripts, left out at 0.
 * 102 AC29: an automation run's transcripts have no page yet, so their count is plain text.
 */
function RecentRow({ run }) {
  const n = run.transcripts
  const count = `${n} ${n === 1 ? 'transcript' : 'transcripts'}`
  return (
    <li className="flex flex-wrap items-baseline gap-x-4 gap-y-1 bg-surface px-4 py-2.5 text-sm md:col-span-6 md:grid md:grid-cols-subgrid">
      <span className={`tabular-nums ${muted}`}>{`run #${run.id}`}</span>
      <RunTitle run={run} className="font-medium wrap-anywhere" />
      <RunProject run={run} />
      <span className="wrap-anywhere">{run.status === 'failed' && run.error ? `failed: ${run.error}` : run.status}</span>
      <span className={`tabular-nums ${muted} md:text-right`}>{duration(run.started_at, run.ended_at)}</span>
      {n > 0 && (run.kind === 'automation' ? <span>{count}</span> : <Link to={`/tasks/${run.task_id}`}>{count}</Link>)}
    </li>
  )
}

// Q9, FE6: the Dashboard's `Nothing needs you.` box
const empty = `rounded-md border border-line px-4 py-3 ${muted}`

/** 046 Q5: the h1, the Running heading, and one running card with its agents box. */
function AgentsSkeleton() {
  return (
    <Skeleton>
      <Block className="mb-4 h-8 w-28" />
      <Block className="mb-2 h-7 w-24" />
      <div className="overflow-hidden rounded-md border border-line">
        <div className="grid gap-1.5 px-4 py-3">
          <Block className="h-6 w-96 max-w-full" />
          <div className="flex items-center gap-4">
            <Block className="mr-auto h-5 w-56" />
            <ButtonBlock className="h-7 w-14" />
          </div>
        </div>
        <div className="grid gap-y-1.5 border-t border-line px-4 py-3">
          {[0, 1, 2].map((i) => (
            <Block key={i} className="h-5 w-full" />
          ))}
        </div>
      </div>
    </Skeleton>
  )
}

/** docs/ui.md §8 item 15, §8.8: every running run with its agents, then the last 20 ended runs. Polled every 3 s. */
export function AgentsPage() {
  // 022 Q3, as on the task page: bumping `tick` restarts usePoll's loop with a fetch at once; `tick` is a dep for that alone
  const [tick, setTick] = useState(0)
  const load = useCallback(() => agentsPage(), [tick])
  const { data: page, error } = usePoll(load, 3000)
  const [stopError, setStopError] = useState(null)
  useEffect(() => {
    document.title = 'Agents · Claude Factories'
  }, [])

  if (error?.status === 404) return <NotFound detail={error.message} />
  if (!page) return error ? <ErrorMessage error={error} /> : <AgentsSkeleton />

  /** FE5, Q11: no confirm; a success clears the alert and refetches at once, a refusal shows in it and the page stays. */
  async function stop(id) {
    try {
      await stopRun(id)
    } catch (err) {
      setStopError(err)
      return
    }
    setStopError(null)
    setTick((n) => n + 1)
  }

  return (
    <>
      <h1 className="mb-4">Agents</h1>
      {error && <OfflineBanner />}
      <section aria-labelledby="agents-running">
        <h2 id="agents-running" className="mt-0">
          Running
        </h2>
        {stopError && (
          <div className="mb-3">
            <ErrorMessage error={stopError} />
          </div>
        )}
        {page.running.length ? (
          <ul className="grid gap-4">
            {page.running.map((run) => (
              <RunningRun key={run.id} run={run} onStop={stop} />
            ))}
          </ul>
        ) : (
          <p className={empty}>Nothing running.</p>
        )}
      </section>
      <section aria-labelledby="agents-recent">
        <h2 id="agents-recent">Recent</h2>
        {page.recent.length ? (
          // the 1px row gaps show the list's `line` background as dividers, as on the Reviews page
          <ul className="grid gap-px overflow-hidden rounded-md border border-line bg-line md:grid-cols-[auto_minmax(0,1fr)_auto_auto_auto_auto] md:gap-x-4">
            {page.recent.map((run) => (
              <RecentRow key={run.id} run={run} />
            ))}
          </ul>
        ) : (
          <p className={empty}>No runs yet.</p>
        )}
      </section>
    </>
  )
}
