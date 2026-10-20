const pad = (n) => String(n).padStart(2, '0')
const day = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
const midnight = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate())

/**
 * 046 Q1: `just now` under a minute or in the future, then floored `Nm ago` and `Nh ago` under a day, then by local
 * calendar days: `yesterday`, `Nd ago` up to 6, else the local date. A few lines of arithmetic, since
 * Intl.RelativeTimeFormat's narrow English output differs between ICU versions.
 */
function ago(d, now) {
  const m = Math.floor((now - d) / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  if (m < 1440) return `${Math.floor(m / 60)}h ago`
  const days = Math.round((midnight(now) - midnight(d)) / 86400000) // round: a DST day is 23 or 25 hours
  if (days === 1) return 'yesterday'
  return days < 7 ? `${days}d ago` : day(d)
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
