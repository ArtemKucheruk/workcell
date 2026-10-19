/** 030: a transcript's label: its teammate name, else its agent type, else `agent`. */
export const agentLabel = (t) => t.name ?? t.agent_type ?? 'agent'

const count = (n) => n.toLocaleString('en-US')

/** 030 Q12: `1h 2m` from an hour, `4m 12s` under one, `12s` under a minute; `—` without both times. */
export function duration(start, end) {
  const ms = Date.parse(end) - Date.parse(start)
  if (!(ms >= 0)) return '—'
  const s = Math.round(ms / 1000)
  if (s >= 3600) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
  if (s >= 60) return `${Math.floor(s / 60)}m ${s % 60}s`
  return `${s}s`
}

/** docs/ui.md §8 items 4 and 8: model · turns · tokens · duration, shared by the task and transcript pages. */
export function AgentStats({ t }) {
  const tokens = `in ${count(t.input_tokens)} · cache ${count(t.cache_read_tokens)} · out ${count(t.output_tokens)}`
  return (
    <span className="tabular-nums">
      {[t.model ?? 'unknown model', `${count(t.turns)} turns`, tokens, duration(t.started_at, t.ended_at)].join(' · ')}
    </span>
  )
}
