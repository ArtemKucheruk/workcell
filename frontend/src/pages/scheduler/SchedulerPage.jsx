import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router'
import { listFactories } from '../../api/factories.js'
import { boardPage } from '../../api/pages.js'
import { createSchedule, deleteSchedule, listSchedules, patchSchedule } from '../../api/schedules.js'
import { ActionButton } from '../../components/ActionButton.jsx'
import { DeleteDialog } from '../../components/DeleteDialog.jsx'
import { ErrorMessage, OfflineBanner } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { ProjectHeader } from '../../components/ProjectHeader.jsx'
import { Block, ButtonBlock, ProjectHeaderSkeleton, Skeleton } from '../../components/Skeleton.jsx'
import { Time } from '../../components/Time.jsx'
import { button, field, muted, popover, smallButton } from '../../components/styles.js'
import { usePoll } from '../../hooks/usePoll.js'

/** AC28: what Delete removes, and what stays. */
const DELETE_TEXT = 'This removes the schedule. The automation and its runs stay.'
const FORM = 'schedule-form' // Q11: one popover for + Schedule automation and every Edit
const WEEKDAYS = [
  [1, 'Monday'], [2, 'Tuesday'], [3, 'Wednesday'], [4, 'Thursday'], [5, 'Friday'], [6, 'Saturday'], [0, 'Sunday'],
]
const REPEATS = [
  ['hourly', 'Hourly'],
  ['daily', 'Daily at'],
  ['weekly', 'Weekly on … at'],
  ['custom', 'Custom cron'],
]
const NEW = { repeat: 'daily', time: '09:00', weekday: 1, custom: '' }

const pad = (n) => String(n).padStart(2, '0')
const number = (s, max) => (/^\d+$/.test(s) && Number(s) <= max ? Number(s) : null)

/**
 * AC27: the form's preset for a stored cron: Hourly is `0 * * * *`, Daily `M H * * *`, Weekly `M H * * D` (7 reads as
 * Sunday). Anything else opens as Custom with its text.
 */
function presetOf(cron) {
  const f = cron.trim().split(/\s+/)
  const [minute, hour, weekday] = [number(f[0], 59), number(f[1], 23), number(f[4], 7)]
  const custom = { ...NEW, repeat: 'custom', custom: cron }
  if (f.length !== 5 || f[2] !== '*' || f[3] !== '*' || minute === null) return custom
  if (f[1] === '*' && f[4] === '*') return minute === 0 ? { ...NEW, repeat: 'hourly' } : custom
  if (hour === null) return custom
  const time = `${pad(hour)}:${pad(minute)}`
  if (f[4] === '*') return { ...NEW, repeat: 'daily', time }
  return weekday === null ? custom : { ...NEW, repeat: 'weekly', time, weekday: weekday % 7 }
}

/** AC26: the cron a preset's fields make; Custom's text goes as typed, for the server to judge. */
function cronOf({ repeat, time, weekday, custom }) {
  if (repeat === 'custom') return custom
  if (repeat === 'hourly') return '0 * * * *'
  const [hour, minute] = String(time).split(':').map(Number)
  return `${minute} ${hour} * * ${repeat === 'weekly' ? weekday : '*'}`
}

/**
 * AC26, AC27, Q11: the popover's form. New: the automations with no schedule; Edit: the schedule's automation, fixed.
 * Repeat shows the fields its preset needs. A refusal shows inside, and the fields keep their values.
 */
function ScheduleForm({ schedule, automations, accounts, onSave }) {
  const start = schedule ? presetOf(schedule.cron) : NEW
  const [repeat, setRepeat] = useState(start.repeat)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  async function submit(event) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const account = form.get('account')
    setBusy(true)
    setError(null)
    try {
      await onSave({
        factoryId: schedule ? schedule.factory_id : Number(form.get('automation')),
        cron: cronOf({ repeat, time: form.get('time'), weekday: form.get('weekday'), custom: form.get('custom') }),
        accountId: account ? Number(account) : null,
      })
    } catch (err) {
      setError(err)
    }
    setBusy(false)
  }
  const time = (
    <label className="grid gap-1">
      Time
      <input type="time" name="time" required defaultValue={start.time} className={field} />
    </label>
  )
  return (
    <form onSubmit={submit} className="grid gap-2">
      <h2 className="m-0 text-base">{schedule ? `Edit schedule of ${schedule.automation}` : 'Schedule automation'}</h2>
      <label className="grid gap-1">
        Automation
        {schedule ? (
          <select disabled className={field}>
            <option>{schedule.automation}</option>
          </select>
        ) : (
          <select name="automation" className={field}>
            {automations.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        )}
      </label>
      <label className="grid gap-1">
        Repeat
        <select name="repeat" value={repeat} onChange={(event) => setRepeat(event.target.value)} className={field}>
          {REPEATS.map(([value, text]) => (
            <option key={value} value={value}>
              {text}
            </option>
          ))}
        </select>
      </label>
      {repeat === 'daily' && time}
      {repeat === 'weekly' && (
        <>
          <label className="grid gap-1">
            Weekday
            <select name="weekday" defaultValue={start.weekday} className={field}>
              {WEEKDAYS.map(([value, name]) => (
                <option key={value} value={value}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          {time}
        </>
      )}
      {repeat === 'custom' && (
        <label className="grid gap-1">
          Cron
          <input
            type="text"
            name="custom"
            defaultValue={start.custom}
            placeholder="*/15 9-17 * * 1-5"
            aria-describedby={`${FORM}-cron-note`}
            className={`${field} font-mono`}
          />
          <span id={`${FORM}-cron-note`} className={`text-sm ${muted}`}>
            minute hour day month weekday, in the server&apos;s local time
          </span>
        </label>
      )}
      <label className="grid gap-1">
        Account
        <select name="account" defaultValue={schedule?.account_id ?? ''} className={field}>
          <option value="">Auto</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.label}
            </option>
          ))}
        </select>
      </label>
      <button disabled={busy} className={`${button} justify-self-start`}>
        {schedule ? 'Save' : 'Create'}
      </button>
      {error && <ErrorMessage error={error} />}
    </form>
  )
}

/** AC24: the last run as a link to its runs page (Q1), its status as text, and its start; or `No runs yet`. */
function LastRun({ projectId, schedule }) {
  const run = schedule.last_run
  return (
    <div className="grid gap-0.5">
      {run ? (
        <span className="flex flex-wrap items-baseline gap-x-2">
          <Link to={`/projects/${projectId}/factories/${schedule.factory_id}/runs?run=${run.id}`}>{`run #${run.id}`}</Link>
          <span>{run.status}</span>
          <span className={muted}>
            <Time iso={run.started_at} relative />
          </span>
        </span>
      ) : (
        <span className={muted}>No runs yet</span>
      )}
      {schedule.last_skip && (
        <span className="text-sm text-warning wrap-anywhere">
          {'Skipped '}
          <Time iso={schedule.last_skip_at} relative />
          {`: ${schedule.last_skip}`}
        </span>
      )}
    </div>
  )
}

/** AC24, AC25, AC27, AC28: one schedule's row. */
function ScheduleRow({ projectId, schedule, onToggle, onEdit, onDelete }) {
  const name = schedule.automation
  return (
    <tr>
      <td className="wrap-anywhere">
        <Link to={`/projects/${projectId}/factories/${schedule.factory_id}/runs`}>{name}</Link>
      </td>
      <td>{schedule.summary}</td>
      <td>
        {schedule.enabled && schedule.next_run_at ? (
          <Time iso={schedule.next_run_at} relative />
        ) : (
          <span className={muted}>Paused</span>
        )}
      </td>
      <td>
        <LastRun projectId={projectId} schedule={schedule} />
      </td>
      <td className="wrap-anywhere">{schedule.account ?? 'Auto'}</td>
      <td>
        <div className="flex justify-end gap-2">
          <ActionButton
            action={() => onToggle(schedule)}
            aria-label={`${schedule.enabled ? 'Pause' : 'Resume'} ${name}`}
            className={smallButton}
          >
            {schedule.enabled ? 'Pause' : 'Resume'}
          </ActionButton>
          <button
            type="button"
            popoverTarget={FORM}
            popoverTargetAction="show"
            aria-label={`Edit schedule of ${name}`}
            onClick={() => onEdit(schedule)}
            className={smallButton}
          >
            Edit
          </button>
          <button
            type="button"
            aria-label={`Delete schedule of ${name}`}
            onClick={(event) => onDelete(schedule, event.currentTarget)}
            className={`${smallButton} text-danger`}
          >
            Delete
          </button>
        </div>
      </td>
    </tr>
  )
}

/** 046 Q5: the header, the h1 and its button, the table's head, and two rows. */
function SchedulerSkeleton() {
  return (
    <Skeleton>
      <ProjectHeaderSkeleton />
      <div className="mb-4 flex items-center justify-between gap-2">
        <Block className="h-8 w-40" />
        <ButtonBlock className="w-48" />
      </div>
      <div className="grid gap-3">
        {[0, 1, 2].map((i) => (
          <Block key={i} className="h-7 w-full" />
        ))}
      </div>
    </Skeleton>
  )
}

/**
 * docs/ui.md §8 item 17. Q12: the schedules poll every 3 s; the header's board view-model and the factories load once,
 * and again after each action (`tick`). An action's refusal shows in the page's red alert, emptied as the next starts.
 */
function Scheduler({ id }) {
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((n) => n + 1), [])
  // board Q3: `tick` is in the deps only to hand usePoll a new load, which fetches at once
  const { data: page, error: pageError } = usePoll(useCallback(() => boardPage(id), [id, tick]))
  const { data: factories, error: factoriesError } = usePoll(useCallback(() => listFactories(id), [id, tick]))
  const { data: schedules, error } = usePoll(useCallback(() => listSchedules(id), [id, tick]), 3000)
  const [actionError, setActionError] = useState(null)
  const [form, setForm] = useState({ schedule: null, key: 0 })
  const [deleting, setDeleting] = useState(null) // {schedule, opener}
  const pop = useRef(null)
  const name = page?.project.name
  useEffect(() => {
    if (name) document.title = `${name} · Scheduler · Claude Factories`
  }, [name])

  const missing = [pageError, factoriesError, error].find((e) => e?.status === 404)
  if (missing) return <NotFound detail={missing.message} />
  if (!page || !factories || !schedules) {
    const failed = pageError ?? factoriesError ?? error
    return failed ? <ErrorMessage error={failed} /> : <SchedulerSkeleton />
  }
  const projectId = page.project.id
  const automations = factories.filter((f) => f.kind === 'automation')
  const scheduled = new Set(schedules.map((s) => s.factory_id))
  const open = automations.filter((f) => !scheduled.has(f.id))
  const full = automations.length === 0 ? 'Create an automation on Workflows first' : 'Every automation has a schedule'

  async function toggle(schedule) {
    setActionError(null)
    try {
      await patchSchedule(schedule.id, { enabled: !schedule.enabled })
    } catch (err) {
      setActionError(err)
      return
    }
    reload()
  }

  async function save({ factoryId, cron, accountId }) {
    if (form.schedule) await patchSchedule(form.schedule.id, { cron, account_id: accountId })
    else await createSchedule(projectId, factoryId, cron, accountId)
    pop.current?.hidePopover?.()
    reload()
  }

  return (
    <>
      <ProjectHeader project={page.project} factory={page.factory} />
      {error && <OfflineBanner />}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h1>Scheduler</h1>
        <button
          type="button"
          popoverTarget={FORM}
          popoverTargetAction="show"
          disabled={open.length === 0}
          title={open.length === 0 ? full : undefined}
          onClick={() => setForm((f) => ({ schedule: null, key: f.key + 1 }))}
          className={`${button} [anchor-name:--schedule-form]`}
        >
          + Schedule automation
        </button>
      </div>
      <div
        ref={pop}
        id={FORM}
        popover="auto"
        className={`${popover} w-96 max-w-[90vw] p-3 [position-anchor:--schedule-form] [position-area:bottom_span-left]`}
      >
        <ScheduleForm
          key={form.key}
          schedule={form.schedule}
          automations={open}
          accounts={page.accounts ?? []}
          onSave={save}
        />
      </div>
      {actionError && <ErrorMessage error={actionError} />}
      {schedules.length ? (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr>
                <th>Automation</th>
                <th>Schedule</th>
                <th>Next run</th>
                <th>Last run</th>
                <th>Account</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {schedules.map((s) => (
                <ScheduleRow
                  key={s.id}
                  projectId={projectId}
                  schedule={s}
                  onToggle={toggle}
                  onEdit={(schedule) => setForm((f) => ({ schedule, key: f.key + 1 }))}
                  onDelete={(schedule, opener) => setDeleting({ schedule, opener })}
                />
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className={`grid gap-1 rounded-md border border-line px-4 py-8 text-center ${muted}`}>
          <p>No scheduled automations.</p>
          {automations.length === 0 && (
            <p>
              {'Create an automation on '}
              <Link to={`/projects/${projectId}/factories`}>Workflows</Link>
              {' first.'}
            </p>
          )}
        </div>
      )}
      {deleting && (
        <DeleteDialog
          title={`Delete schedule of ${deleting.schedule.automation}?`}
          text={DELETE_TEXT}
          remove={() => deleteSchedule(deleting.schedule.id)}
          onDeleted={reload}
          onClose={(deleted) => {
            setDeleting(null)
            // the row is gone, so focus goes to + Schedule automation, as the Workflows page's delete does
            const next = deleted ? document.querySelector(`[popovertarget="${FORM}"]`) : deleting.opener
            next?.focus()
          }}
        />
      )}
    </>
  )
}

/** Keyed by id, so another project's page starts with no form or dialog open. */
export function SchedulerPage() {
  const { id } = useParams()
  return <Scheduler key={id} id={id} />
}
