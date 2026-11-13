import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { usagePage } from '../../api/usage.js'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { Block, Skeleton } from '../../components/Skeleton.jsx'
import { muted } from '../../components/styles.js'
import { Time } from '../../components/Time.jsx'
import { NO_DATA, UsageWindow, WINDOWS } from '../../components/UsageWindow.jsx'

const EMPTY = 'No usage in this period.'
const empty = `rounded-md border border-line px-4 py-3 ${muted}`

/** AC28: thousands separators, the same in every locale the tests run in. */
const n = (value) => value.toLocaleString('en-US')

/**
 * AC28: the three token kinds, in the order the bars stack them, each with its fill and the text that names it.
 * Cache read is `muted`, which stands out from the `raised` track and the page in both themes.
 */
const KINDS = [
  ['input_tokens', 'input', 'bg-accent'],
  ['cache_read_tokens', 'cache read', 'bg-muted'],
  ['output_tokens', 'output', 'bg-warning'],
]
const total = (row) => KINDS.reduce((sum, [key]) => sum + row[key], 0)

/** AC26: one account's card: label and `active` pill, its two windows, when the snapshot was taken, and overage. */
function AccountCard({ account }) {
  return (
    <li className="grid gap-3 rounded-md border border-line px-4 py-3">
      <p className="flex flex-wrap items-baseline gap-2">
        <span className="font-medium wrap-anywhere">{account.label}</span>
        {account.active && (
          <span className="rounded-full border border-accent px-2 text-xs font-medium text-accent">active</span>
        )}
      </p>
      {account.five_hour ? (
        <>
          {WINDOWS.map(([key, name]) => account[key] && <UsageWindow key={key} name={name} window={account[key]} large />)}
          <p className={`text-sm ${muted}`}>
            {'as of '}
            <Time iso={account.recorded_at} relative />
            {` · run #${account.run_id} · Overage: ${account.overage ? 'in use' : 'not in use'}`}
          </p>
        </>
      ) : (
        <p className={muted}>{NO_DATA}</p>
      )}
    </li>
  )
}

/** AC28: one stacked bar per day, scaled to the busiest day, with its totals and runs as text under it. */
function ByDay({ days }) {
  const most = Math.max(...days.map(total))
  if (!most && !days.some((d) => d.runs)) return <p className={empty}>{EMPTY}</p>
  return (
    <>
      <p className={`mb-2 flex flex-wrap gap-x-4 text-sm ${muted}`}>
        {KINDS.map(([key, label, fill]) => (
          <span key={key} className="inline-flex items-center gap-1.5">
            <span aria-hidden="true" className={`inline-block size-2.5 rounded-sm ${fill}`} />
            {label}
          </span>
        ))}
      </p>
      <ol className="grid gap-2">
        {days.map((day) => (
          <li key={day.day} className="grid gap-0.5 text-sm">
            <div className="flex items-center gap-3">
              <span className="w-24 shrink-0 tabular-nums">{day.day}</span>
              <div aria-hidden="true" className="flex h-3 flex-1 overflow-hidden rounded-sm bg-raised">
                {most > 0 &&
                  KINDS.map(([key, , fill]) => (
                    <div key={key} className={fill} style={{ width: `${(day[key] / most) * 100}%` }} />
                  ))}
              </div>
            </div>
            <p className={`pl-27 tabular-nums ${muted}`}>
              {`${KINDS.map(([key, label]) => `${label} ${n(day[key])}`).join(' · ')} · ${day.runs} ${
                day.runs === 1 ? 'run' : 'runs'
              }`}
            </p>
          </li>
        ))}
      </ol>
    </>
  )
}

/** AC28: a by-account, by-model, or by-agent table: the key, the three token columns, and runs. */
function Groups({ rows, label }) {
  if (!rows.length) return <p className={empty}>{EMPTY}</p>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr>
            <th scope="col">{label}</th>
            {['Input', 'Cache read', 'Output', 'Runs'].map((h) => (
              <th key={h} scope="col" className="text-right">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key}>
              <th scope="row" className="font-normal wrap-anywhere">
                {row.key}
              </th>
              {[...KINDS.map(([key]) => row[key]), row.runs].map((value, i) => (
                <td key={i} className="text-right tabular-nums">
                  {n(value)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** AC28: the most expensive tasks, each linking to its page, with its three token counts. */
function TopTasks({ tasks }) {
  if (!tasks.length) return <p className={empty}>{EMPTY}</p>
  return (
    <ol className="grid gap-1 text-sm">
      {tasks.map((t) => (
        <li key={t.task_id} className="flex flex-wrap items-baseline gap-x-3">
          <Link to={`/tasks/${t.task_id}`} className="wrap-anywhere">{`#${t.task_id} ${t.title}`}</Link>
          <span className={`tabular-nums ${muted}`}>
            {KINDS.map(([key, label]) => `${label} ${n(t[key])}`).join(' · ')}
          </span>
        </li>
      ))}
    </ol>
  )
}

/** AC29: runs whose snapshot was limited, latest first. */
function LimitedRuns({ runs }) {
  if (!runs.length) return <p className={empty}>No limited runs.</p>
  return (
    <ul className="grid gap-1 text-sm">
      {runs.map((r) => (
        <li key={r.run_id} className="flex flex-wrap items-baseline gap-x-2">
          <span className={`tabular-nums ${muted}`}>{`run #${r.run_id}`}</span>
          <span aria-hidden="true">·</span>
          <Link to={`/tasks/${r.task_id}`} className="wrap-anywhere">{`#${r.task_id} ${r.title}`}</Link>
          <span aria-hidden="true">·</span>
          <span>{r.label}</span>
          {r.ended_at && (
            <>
              <span aria-hidden="true">·</span>
              <Time iso={r.ended_at} />
            </>
          )}
        </li>
      ))}
    </ul>
  )
}

/** AC27: the period, a native radio group. */
function Period({ days, onChange }) {
  return (
    <fieldset className="mb-6 flex flex-wrap gap-4">
      <legend className="sr-only">Period</legend>
      {[7, 30].map((d) => (
        <label key={d} className="inline-flex items-center gap-1.5">
          <input type="radio" name="usage-days" value={d} checked={days === d} onChange={() => onChange(d)} />
          {`Last ${d} days`}
        </label>
      ))}
    </fieldset>
  )
}

function UsageSkeleton() {
  return (
    <Skeleton>
      <Block className="mb-4 h-8 w-24" />
      <Block className="mb-6 h-6 w-64" />
      <Block className="mb-2 h-7 w-28" />
      <div className="grid gap-3 rounded-md border border-line px-4 py-3">
        <Block className="h-6 w-56" />
        <Block className="h-5 w-full" />
        <Block className="h-5 w-full" />
      </div>
    </Skeleton>
  )
}

const Section = ({ id, title, children }) => (
  <section aria-labelledby={id}>
    <h2 id={id}>{title}</h2>
    {children}
  </section>
)

/**
 * 095, docs/ui.md §8 item 16: each Claude account's latest limits, then the token and run stats over 7 or 30 days.
 * AC25: fetched once per period, never polled; the limits are as fresh as each account's last run (Q2).
 */
export function UsagePage() {
  const [days, setDays] = useState(7)
  const [page, setPage] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    document.title = 'Usage · Claude Factories'
  }, [])
  useEffect(() => {
    let live = true
    setError(null)
    usagePage(days).then(
      (body) => live && setPage(body),
      (err) => live && setError(err),
    )
    return () => {
      live = false
    }
  }, [days])

  if (!page) return error ? <ErrorMessage error={error} /> : <UsageSkeleton />
  const { stats } = page
  return (
    <>
      <h1 className="mb-4">Usage</h1>
      <Section id="usage-accounts" title="Accounts">
        {page.accounts.length ? (
          <ul className="grid gap-4 md:grid-cols-2">
            {page.accounts.map((a) => (
              <AccountCard key={a.id} account={a} />
            ))}
          </ul>
        ) : (
          // round 2 (ui): no blank section with no accounts; Settings is where one is added
          <p className={empty}>
            No Claude accounts yet. <Link to="/settings">Sign in from Settings</Link>.
          </p>
        )}
      </Section>
      <div className="mt-8">
        <Period days={days} onChange={setDays} />
        {error && (
          <div className="mb-3">
            <ErrorMessage error={error} />
          </div>
        )}
      </div>
      <Section id="usage-by-day" title="By day">
        <ByDay days={stats.by_day} />
      </Section>
      <Section id="usage-by-account" title="By account">
        <Groups rows={stats.by_account} label="Account" />
      </Section>
      <Section id="usage-by-model" title="By model">
        <Groups rows={stats.by_model} label="Model" />
      </Section>
      <Section id="usage-by-agent" title="By agent">
        <Groups rows={stats.by_agent} label="Agent" />
      </Section>
      <Section id="usage-top-tasks" title="Most expensive tasks">
        <TopTasks tasks={stats.top_tasks} />
      </Section>
      <Section id="usage-limited" title="Limited runs">
        <LimitedRuns runs={page.limited_runs} />
      </Section>
    </>
  )
}
