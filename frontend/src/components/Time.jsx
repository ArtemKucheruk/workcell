const pad = (n) => String(n).padStart(2, '0')
const day = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
const midnight = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate())

/**
 * 046 Q1: `just now` under a minute, then floored `Nm ago` and `Nh ago` under a day, then by local calendar days:
 * `yesterday`, `Nd ago` up to 6, else the local date. A few lines of arithmetic, since Intl.RelativeTimeFormat's
 * narrow English output differs between ICU versions. 104 Q7: a future time reads the same way forward: `in <1m`,
 * `in Nm`, `in Nh`, then `tomorrow`, `in Nd` up to 6, else the date.
 */
function ago(d, now) {
  const future = d > now
  const m = Math.floor(Math.abs(now - d) / 60000)
  if (m < 1) return future ? 'in <1m' : 'just now'
  if (m < 60) return future ? `in ${m}m` : `${m}m ago`
  if (m < 1440) return future ? `in ${Math.floor(m / 60)}h` : `${Math.floor(m / 60)}h ago`
  const days = Math.abs(Math.round((midnight(now) - midnight(d)) / 86400000)) // round: a DST day is 23 or 25 hours
  if (days === 1) return future ? 'tomorrow' : 'yesterday'
  if (days >= 7) return day(d)
  return future ? `in ${days}d` : `${days}d ago`
}

/**
 * Q13: an ISO time in the browser's local time as YYYY-MM-DD HH:MM, like Jinja's local_time.
 * 046: `relative` reads from the clock at render (Q3: the page's own polls refresh it), with the full time in `title`.
 */
export function Time({ iso, relative = false }) {
  const d = new Date(iso)
  const full = `${day(d)} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  return (
    <time dateTime={iso} title={relative ? full : undefined} className="tabular-nums">
      {relative ? ago(d, new Date()) : full}
    </time>
  )
}
