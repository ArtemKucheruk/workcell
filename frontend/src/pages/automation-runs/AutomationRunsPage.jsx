import { useCallback, useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import { runAutomation } from '../../api/factories.js'
import { automationRunsPage } from '../../api/pages.js'
import { stopRun } from '../../api/runs.js'
import { ActionButton } from '../../components/ActionButton.jsx'
import { AgentStats, agentLabel, duration } from '../../components/AgentStats.jsx'
import { RunStatusPill } from '../../components/Badge.jsx'
import { Breadcrumbs, projectTrail } from '../../components/Breadcrumbs.jsx'
import { ErrorMessage, OfflineBanner } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { RunLog } from '../../components/RunLog.jsx'
import { RunMenu, runsOff } from '../../components/RunMenu.jsx'
import { Block, ButtonBlock, Skeleton, TitleSkeleton } from '../../components/Skeleton.jsx'
import { muted, smallButton } from '../../components/styles.js'
import { Time } from '../../components/Time.jsx'
import { usePoll } from '../../hooks/usePoll.js'

/**
 * Q7: an ended run's length; a running one's elapsed time to now, worked out at render so the 3 s poll ticks it; `—` for
 * a run that isn't running and has no end.
 */
function runLength(run) {
  if (run.ended_at) return duration(run.started_at, run.ended_at)
  return run.status === 'running' ? duration(run.started_at, new Date().toISOString()) : '—'
}

/**
 * AC13, AC15, AC18: one run: `run #id` picks it (`?run=`), then its pill, trigger, start, length, account, and a failed
 * run's error as text. Q11: Stop sits only on a running run's row, with its spinner and no confirm.
 */
function RunRow({ run, picked, onStop }) {
  return (
    <li
      aria-current={picked ? 'true' : undefined}
      className={`flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md px-2 py-1 ${picked ? 'bg-raised' : ''}`}
    >
      <Link to={{ search: `?run=${run.id}` }} className="font-medium tabular-nums">{`run #${run.id}`}</Link>
      <RunStatusPill status={run.status} />
      <span className={muted}>{run.trigger}</span>
      <Time iso={run.started_at} relative />
      <span className="tabular-nums">{runLength(run)}</span>
      <span className={`wrap-anywhere ${muted}`}>{run.account ?? '—'}</span>
      {run.status === 'failed' && run.error && <span className="wrap-anywhere text-danger">{run.error}</span>}
      {run.status === 'running' && (
        <ActionButton action={() => onStop(run.id)} className={`${smallButton} ml-auto`} aria-label={`Stop run #${run.id}`}>
          Stop
        </ActionButton>
      )}
    </li>
  )
}

/** AC17: the open run's transcripts, each its agent's label linking to the transcript page, then its stats. */
function Transcripts({ run }) {
  return (
    <section aria-labelledby="run-transcripts" className="mt-4">
      <h2 id="run-transcripts">{`Transcripts · run #${run.id}`}</h2>
      {run.transcripts.length ? (
        <ul aria-label={`Transcripts of run #${run.id}`} className="grid gap-1 text-sm">
          {run.transcripts.map((t) => (
            <li key={t.id}>
              <Link to={`/transcripts/${t.id}`}>{agentLabel(t)}</Link>
              <span className={muted}>
                {' · '}
                <AgentStats t={t} />
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className={muted}>No transcripts yet.</p>
      )}
    </section>
  )
}

/** 046 Q5: the breadcrumb, the title row with Run now, then a few run rows. */
function RunsSkeleton() {
  return (
    <Skeleton>
      <TitleSkeleton title={<ButtonBlock className="w-24" />} />
      <div className="grid gap-2">
        {[0, 1, 2].map((i) => (
          <Block key={i} className="h-7 w-full" />
        ))}
      </div>
    </Skeleton>
  )
}

/**
 * docs/ui.md §8 item 17: an automation's runs, newest first, polled every 3 s (Q8). Q5: no log shows until a run is
 * picked by `?run=`, or Run now starts one; a `?run=` that isn't listed shows none. Q4: one Run now with its ▾ in the
 * title row. Run now's and Stop's refusals show in the page alert, emptied as the next one starts (AC18, AC19).
 */
function AutomationRuns({ id, fid }) {
  const [params, setParams] = useSearchParams()
  // 022 Q3: `tick` is in the deps only to hand usePoll a new load, which fetches at once
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((n) => n + 1), [])
  const load = useCallback(() => automationRunsPage(fid), [fid, tick])
  const { data: page, error } = usePoll(load, 3000)
  const [actionError, setActionError] = useState(null)
  const [started, setStarted] = useState(null)
  const owned = page && String(page.automation.project_id) === id
  const title = owned && `${page.automation.name} runs · ${page.automation.project}`
  useEffect(() => {
    if (title) document.title = `${title} · Workcell`
  }, [title])

  if (error?.status === 404) return <NotFound detail={error.message} />
  if (!page) return error ? <ErrorMessage error={error} /> : <RunsSkeleton />
  if (!owned) return <NotFound detail={`Factory #${fid} not found`} /> // AC12: another project's, as the designer does
  const { automation, runs } = page
  const off = runsOff(page)
  const picked = runs.find((r) => String(r.id) === params.get('run'))

  /** The alert empties as a request starts; a refusal fills it and the page stays, a success reloads at once. */
  async function send(call) {
    setActionError(null)
    try {
      const reply = await call()
      reload()
      return reply
    } catch (err) {
      setActionError(err)
      return null
    }
  }
  async function start(accountId) {
    setStarted(null)
    const made = await send(() => runAutomation(automation.id, accountId))
    if (made) {
      setStarted(made)
      setParams({ run: String(made.run_id) })
    }
  }

  return (
    <>
      <header className="mb-6 grid gap-2">
        <Breadcrumbs
          items={[
            ...projectTrail(automation),
            { label: 'Workflows', to: `/projects/${automation.project_id}/factories` },
            { label: automation.name },
          ]}
        />
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <h1 className="mr-auto wrap-anywhere">{automation.name}</h1>
          <div className="flex items-center gap-2">
            <ActionButton action={() => start(null)} disabled={!!off} title={off ?? undefined}>
              Run now
            </ActionButton>
            {page.accounts.length > 0 && (
              <RunMenu
                id="run-menu"
                accounts={page.accounts}
                auto={page.auto}
                disabled={!!off}
                title={off ?? undefined}
                onRun={start}
              />
            )}
          </div>
        </div>
        {actionError && <ErrorMessage error={actionError} />}
        <p role="status" className="empty:hidden">
          {started && `Started run #${started.run_id}${started.account ? ` as ${started.account}` : ''}.`}
        </p>
      </header>
      {error && <OfflineBanner />}
      {runs.length ? (
        <ul aria-label="Runs" className="grid gap-1">
          {runs.map((run) => (
            <RunRow
              key={run.id}
              run={run}
              picked={run === picked}
              onStop={(runId) => send(() => stopRun(runId))}
            />
          ))}
        </ul>
      ) : (
        <p className={muted}>No runs yet.</p>
      )}
      {picked && (
        <>
          <RunLog key={picked.id} run={picked} open />
          <Transcripts run={picked} />
        </>
      )}
    </>
  )
}

/** Keyed by automation, so another one starts with no alert or status. */
export function AutomationRunsPage() {
  const { id, fid } = useParams()
  return <AutomationRuns key={fid} id={id} fid={fid} />
}
