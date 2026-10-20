import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router'
import { boardPage } from '../../api/pages.js'
import { projectContext, saveProjectContext } from '../../api/projects.js'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { Markdown } from '../../components/Markdown.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { ProjectHeader } from '../../components/ProjectHeader.jsx'
import { button, field, muted } from '../../components/styles.js'
import { usePoll } from '../../hooks/usePoll.js'

const utf8 = (text) => new TextEncoder().encode(text).length

/**
 * 033's editor, moved from the board and open on load. `saved` is the last GET or PUT reply, which the Preview
 * shows (Q10: the saved version, since the SPA renders no markdown); `draft` and `bytes` stay null until typed.
 */
function Editor({ projectId, loaded }) {
  const [saved, setSaved] = useState(loaded)
  const [draft, setDraft] = useState(null)
  const [bytes, setBytes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const text = draft ?? saved.context_md
  const size = bytes ?? saved.bytes
  const over = size > saved.max_bytes

  async function save(event) {
    event.preventDefault()
    setBusy(true)
    try {
      setSaved(await saveProjectContext(projectId, text))
      setBytes(null) // the reply's count, until the next keystroke
      setError(null)
    } catch (err) {
      setError(err) // the draft and the old Preview stay
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid items-start gap-8 lg:grid-cols-2">
      <form onSubmit={save} className="grid gap-2">
        <h2 id="context-editor" className="m-0">
          Project context
        </h2>
        <p className={`text-sm ${muted}`}>
          Stack and conventions. Agents read it at the top of <code>fctl show</code>.
        </p>
        <textarea
          aria-labelledby="context-editor"
          value={text}
          onChange={(event) => {
            setDraft(event.target.value)
            setBytes(utf8(event.target.value))
          }}
          rows={20}
          placeholder="Markdown, e.g. # Stack"
          className={`${field} font-mono text-sm`}
        />
        <div className="flex flex-wrap items-center gap-3">
          <button disabled={busy || over} className={button}>
            Save
          </button>
          <span className={`text-sm tabular-nums ${over ? 'font-semibold text-danger' : muted}`}>
            {`${size} / ${saved.max_bytes} bytes${over ? ' · over the limit' : ''}`}
          </span>
        </div>
        {error && <ErrorMessage error={error} />}
      </form>
      <section aria-labelledby="context-preview" className="grid gap-2">
        <h2 id="context-preview" className="m-0">
          Preview
        </h2>
        <div className="rounded-md border border-line p-4">
          {saved.context_md.trim() ? (
            <Markdown html={saved.context_html} />
          ) : (
            <p className={muted}>Nothing saved yet.</p>
          )}
        </div>
      </section>
    </div>
  )
}

/** docs/ui.md §8 item 11. Q6: the context and the header's board view-model load once each, never polled. */
function ProjectContext({ id }) {
  const { data: page, error: pageError } = usePoll(useCallback(() => boardPage(id), [id]))
  const { data: context, error } = usePoll(useCallback(() => projectContext(id), [id]))
  const name = page?.project.name
  useEffect(() => {
    if (name) document.title = `${name} · Context · Claude Factories`
  }, [name])

  const missing = [pageError, error].find((e) => e?.status === 404)
  if (missing) return <NotFound detail={missing.message} />
  if (!page) return pageError ? <ErrorMessage error={pageError} /> : <p className={muted}>Loading…</p>
  return (
    <>
      <ProjectHeader project={page.project} factory={page.factory} />
      {error ? (
        <ErrorMessage error={error} />
      ) : context ? (
        <Editor projectId={page.project.id} loaded={context} />
      ) : (
        <p className={muted}>Loading…</p>
      )}
    </>
  )
}

/** FE24: keyed by id, so another project's page never shows this one's draft. */
export function ContextPage() {
  const { id } = useParams()
  return <ProjectContext key={id} id={id} />
}
