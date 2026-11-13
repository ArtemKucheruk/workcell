import { muted } from './styles.js'

/** 095 AC20, Q5: the backend's state (AC5) as words, so the bar's color is never the only signal. */
export const STATE = { allowed: 'allowed', near_limit: 'near limit', limited: 'limited' }

/** AC21: the fill per state, on a `bg-line` track. */
const FILL = { allowed: 'bg-accent', near_limit: 'bg-warning', limited: 'bg-danger' }

export const NO_DATA = 'no usage data yet, run a task'

export const WINDOWS = [
  ['five_hour', '5h'],
  ['seven_day', '7d'],
]

export const percent = (window) => `${Math.round(window.utilization * 100)}%`

const pad = (n) => String(n).padStart(2, '0')

/** AC20: `resets in 2h 10m` (days for the 7-day window, minutes under an hour), or `reset at HH:MM` once passed. */
export function resetText(window, now = Date.now()) {
  const at = new Date(window.resets_at * 1000)
  if (window.reset) return `reset at ${pad(at.getHours())}:${pad(at.getMinutes())}`
  const minutes = Math.max(0, Math.ceil((at - now) / 60000))
  const [d, h, m] = [Math.floor(minutes / 1440), Math.floor(minutes / 60) % 24, minutes % 60]
  if (d) return `resets in ${d}d ${h}h`
  return h ? `resets in ${h}h ${m}m` : `resets in ${m}m`
}

/** AC22: an account's window with the higher utilization, as [label, window]; null with no snapshot. */
export function worst(account) {
  const found = WINDOWS.map(([key, label]) => [label, account[key]]).filter(([, w]) => w)
  if (!found.length) return null
  return found.reduce((a, b) => (b[1].utilization > a[1].utilization ? b : a))
}

/**
 * 095 AC20, AC21, AC26: one window: its name, a bar filled to its % (hidden from assistive tech, which reads the text),
 * then the %, the reset text, and the state. `large` is the Usage page's size.
 */
export function UsageWindow({ name, window, large = false }) {
  const width = window.reset ? 0 : Math.min(100, Math.max(0, window.utilization * 100))
  return (
    <div className={`grid gap-0.5 ${large ? 'text-base' : 'text-xs'}`}>
      <div className="flex items-center gap-2">
        <span className="w-5 shrink-0 font-medium">{name}</span>
        <div aria-hidden="true" className={`flex-1 overflow-hidden rounded-full bg-line ${large ? 'h-2.5' : 'h-1.5'}`}>
          <div data-fill className={`h-full rounded-full ${FILL[window.state]}`} style={{ width: `${width}%` }} />
        </div>
        <span className="w-9 shrink-0 text-right tabular-nums">{percent(window)}</span>
      </div>
      <p className={`pl-7 ${muted}`}>
        {`${resetText(window)} · `}
        <span className={window.state === 'allowed' ? '' : 'font-medium text-fg'}>{STATE[window.state]}</span>
      </p>
    </div>
  )
}
