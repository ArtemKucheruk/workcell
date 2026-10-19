import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { rawUrl, transcript } from '../../api/transcripts.js'
import { AgentStats, agentLabel } from '../../components/AgentStats.jsx'
import { button } from '../../components/ActionButton.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { Markdown } from '../../components/Markdown.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { Time } from '../../components/Time.jsx'
import { usePoll } from '../../hooks/usePoll.js'

const muted = 'text-gray-600 dark:text-gray-400'
const pre = 'overflow-auto rounded-md bg-gray-100 p-3 font-mono text-sm whitespace-pre-wrap wrap-anywhere dark:bg-gray-900'

/**
 * One content block. docs/MVP.md §4.5: only text arrives as `text_html`; a tool's input and result and thinking
 * render as React text, so markup in them shows literally.
 */
function Block({ block, onShowAll }) {
  if (block.type === 'text') return <Markdown html={block.text_html} />
  if (block.type === 'thinking') {
    return (
      <details>
        <summary className={`cursor-pointer text-sm ${muted}`}>Thinking</summary>
        <p className="mt-1 text-sm whitespace-pre-wrap wrap-anywhere">{block.text}</p>
      </details>
    )
  }
  if (block.type === 'tool_use') {
    return (
      <div>
        <p className="text-sm">
          {'Tool call: '}
          <code>{block.name}</code>
        </p>
        <pre className={pre}>{block.input}</pre>
      </div>
    )
  }
  if (block.type === 'tool_result') {
    return (
      <div>
        <p className={`text-sm ${block.is_error ? 'text-red-700 dark:text-red-400' : muted}`}>
          {block.is_error ? 'Tool error' : 'Tool result'}
        </p>
        <pre className={pre}>{block.text}</pre>
        {block.truncated && (
          <button type="button" onClick={onShowAll} className={`${button} mt-1 text-sm`}>
            Show all
          </button>
        )}
      </div>
    )
  }
  return null
}

/**
 * docs/ui.md §8 item 8: one agent's transcript. Fetched once, no poll: a copy only changes when a run ends.
 * Q9: "Show all" refetches with ?full=1, after which every tool result is whole.
 * ponytail: every message renders at once; window the list if transcripts get long enough to lag.
 */
export function TranscriptPage() {
  const { id } = useParams()
  const [full, setFull] = useState(false)
  const load = useCallback(() => transcript(id, full), [id, full])
  const { data: t, error } = usePoll(load)
  const showAll = useCallback(() => setFull(true), [])
  const label = t && agentLabel(t)
  useEffect(() => {
    if (label) document.title = `${label} · Claude Factories`
  }, [label])

  if (error?.status === 404) return <NotFound detail={error.message} />
  if (!t) return error ? <ErrorMessage error={error} /> : <p className={muted}>Loading…</p>

  return (
    <>
      <header className="mb-6 grid gap-2">
        <nav aria-label="Breadcrumb" className="text-sm">
          <Link to={`/tasks/${t.task_id}`}>{`Task #${t.task_id}`}</Link>
        </nav>
        <h1 className="text-2xl font-semibold wrap-anywhere">{label}</h1>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span>{`run #${t.run_id}`}</span>
          {t.round != null && <span>{`round ${t.round}`}</span>}
          <AgentStats t={t} />
          <a href={rawUrl(t.id)} download>
            Download raw
          </a>
        </p>
      </header>
      {error && <ErrorMessage error={error} />}
      {t.messages.length ? (
        <ol className="grid gap-4">
          {t.messages.map((m, i) => (
            <li key={i} className="grid gap-2 border-l-2 border-gray-200 pl-3 dark:border-gray-700">
              <p className="text-sm">
                <strong>{m.role}</strong>
                {m.at && (
                  <>
                    {' · '}
                    <Time iso={m.at} />
                  </>
                )}
              </p>
              {m.blocks.map((b, j) => (
                <Block key={j} block={b} onShowAll={showAll} />
              ))}
            </li>
          ))}
        </ol>
      ) : (
        <p className={muted}>No messages.</p>
      )}
    </>
  )
}
