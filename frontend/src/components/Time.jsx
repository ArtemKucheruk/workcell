const pad = (n) => String(n).padStart(2, '0')

/** Q13: an ISO time in the browser's local time as YYYY-MM-DD HH:MM, like Jinja's local_time. */
export function Time({ iso }) {
  const d = new Date(iso)
  const text = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  return (
    <time dateTime={iso} className="tabular-nums">
      {text}
    </time>
  )
}
