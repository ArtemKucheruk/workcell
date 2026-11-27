import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router'
import { rawUrl, transcript } from '../../api/transcripts.js'
import { AgentStats, agentLabel } from '../../components/AgentStats.jsx'
import { Breadcrumbs, projectTrail } from '../../components/Breadcrumbs.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { Markdown } from '../../components/Markdown.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { Block as Placeholder, Lines, Skeleton, TitleSkeleton } from '../../components/Skeleton.jsx'
import { button, muted } from '../../components/styles.js'
import { Time } from '../../components/Time.jsx'
import { usePoll } from '../../hooks/usePoll.js'

const pre = 'overflow-auto rounded-md bg-raised p-3 font-mono text-sm whitespace-pre-wrap wrap-anywhere'

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
        <p className={`text-sm ${block.is_error ? 'text-danger' : muted}`}>
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

/** 046 Q5: the breadcrumb, the label, the stats line, then a few messages. */
function TranscriptSkeleton() {
  return (
    <Skeleton>
      <TitleSkeleton>
        <Placeholder className="h-6 w-96 max-w-full" />
      </TitleSkeleton>
      <div className="grid gap-4">
        {[0, 1, 2].map((i) => (
          <div key={i} className="grid gap-2 border-l-2 border-line pl-3">
            <Placeholder className="h-5 w-40" />
            <Lines n={3} />
          </div>
        ))}
      </div>
    </Skeleton>
  )
}

/**
 * 047 Q2: a task transcript's `#id` links to its task. 103 AC25, Q9: an automation's (no task_id) is `Workflows ›
 * <automation>`, the name linking to its runs page with this run open.
 */
const owner = (t) =>
  t.task_id == null
    ? [
        { label: 'Workflows', to: `/projects/${t.project_id}/factories` },
        { label: t.factory, to: `/projects/${t.project_id}/factories/${t.factory_id}/runs?run=${t.run_id}` },
      ]
    : [{ label: `#${t.task_id}`, to: `/tasks/${t.task_id}` }]

/**
 * docs/ui.md §8 item 8: one agent's transcript. Fetched once, no poll: a copy only changes when a run ends.
 * Q9: "Show all" refetches with ?full=1, after which every tool result is whole. 047 Q2: the breadcrumb's `#id` is the link
 * to its task, and its last item is the agent's label.
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
    if (label) document.title = `${label} · Workcell`
  }, [label])

  if (error?.status === 404) return <NotFound detail={error.message} />
  if (!t) return error ? <ErrorMessage error={error} /> : <TranscriptSkeleton />

  return (
    <>
      <header className="mb-6 grid gap-2">
        <Breadcrumbs items={[...projectTrail(t), ...owner(t), { label }]} />
        <h1 className="wrap-anywhere">{label}</h1>
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
            <li key={i} className="grid gap-2 border-l-2 border-line pl-3">
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
