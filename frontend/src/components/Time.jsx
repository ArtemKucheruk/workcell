const pad = (n) => String(n).padStart(2, '0')

/**
 * Q13: an ISO time in the browser's local time as YYYY-MM-DD HH:MM, like Jinja's local_time.
 * 022 Q6: `timeOnly` prints just HH:MM, like local_time("%H:%M").
 */
export function Time({ iso, timeOnly = false }) {
  const d = new Date(iso)
  const hm = `${pad(d.getHours())}:${pad(d.getMinutes())}`
  const text = timeOnly ? hm : `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hm}`
  return (
    <time dateTime={iso} className="tabular-nums">
      {text}
    </time>
  )
}
