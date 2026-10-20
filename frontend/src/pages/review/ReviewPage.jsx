import hljs from 'highlight.js/lib/common'
import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useParams, useSearchParams } from 'react-router'
import { reviewPage } from '../../api/pages.js'
import { addComment, approveTask, requestChanges } from '../../api/reviews.js'
import { ActionButton } from '../../components/ActionButton.jsx'
import { Chip } from '../../components/Chip.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { Markdown } from '../../components/Markdown.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { StatusLine } from '../../components/StatusLine.jsx'
import { button, field, muted } from '../../components/styles.js'
import { Time } from '../../components/Time.jsx'
import { usePoll } from '../../hooks/usePoll.js'

const blank = (md) => !md?.trim()
const plusMinus = ({ additions, deletions }) => `+${additions} −${deletions}`
const CHANGE = { added: '(new)', deleted: '(deleted)' }
const SIGN = { add: '+', del: '-' }

/** Q5, Q7: a comment box whose Comment stays disabled while blank. A refusal shows inside it and keeps the text. */
function CommentForm({ label, placeholder, autoFocus, send, onSent, children }) {
  const [text, setText] = useState('')
  const [error, setError] = useState(null)
  async function submit() {
    try {
      await send(text)
    } catch (err) {
      setError(err)
      return
    }
    setText('')
    setError(null)
    onSent()
  }
  return (
    <form className="grid max-w-3xl gap-2">
      <textarea
        aria-label={label}
        placeholder={placeholder}
        autoFocus={autoFocus}
        rows={4}
        value={text}
        onChange={(e) => setText(e.target.value)}
        className={field}
      />
      <div className="flex gap-2">
        <ActionButton action={submit} disabled={blank(text)}>
          Comment
        </ActionButton>
        {children}
      </div>
      {error && <ErrorMessage error={error} />}
    </form>
  )
}

// --- Conversation (docs/ui.md §8.2) ------------------------------------------------------

/**
 * `Round n trigger chips +A −D`, then each posted verdict with a body as a closed <details>, in reviewer order
 * (Q9). claude-code.md §7.4: a standalone task (no worktree) with nothing posted says "no agent review".
 */
function Round({ round, standalone }) {
  const { n, posted, verdicts } = round
  const bodies = Object.keys(verdicts).filter((who) => !blank(posted[who]?.body_md))
  return (
    <li>
      <p>
        <strong>{`Round ${n}`}</strong> <span className={muted}>{round.trigger}</span>
        {standalone && Object.keys(posted).length === 0 ? (
          <>
            {' '}
            <span className={muted}>no agent review</span>
          </>
        ) : (
          Object.entries(verdicts).map(([who, verdict]) => (
            <Fragment key={who}>
              {' '}
              <Chip n={n} who={who} verdict={verdict} />
            </Fragment>
          ))
        )}{' '}
        <span className={`tabular-nums ${muted}`}>{plusMinus(round)}</span>
      </p>
      {bodies.map((who) => (
        <details key={who} className="ml-4">
          <summary className="cursor-pointer truncate">
            {`${who} · ${posted[who].verdict} `}
            <span className={muted}>{posted[who].body_md.trim().split(/\r?\n/)[0]}</span>
          </summary>
          <Markdown html={posted[who].body_html} className="my-2 border-l-2 border-line pl-3" />
        </details>
      ))}
    </li>
  )
}

function Conversation({ page, onSent }) {
  const { task, rounds, approver, timeline } = page
  return (
    <>
      <section aria-labelledby="review-description">
        <h2 id="review-description" className="mt-0">
          Description
        </h2>
        {blank(task.description_md) ? <p className={muted}>No description.</p> : <Markdown html={task.description_html} />}
        {!blank(task.spec_md) && (
          <details className="mt-3">
            <summary className="cursor-pointer">Spec</summary>
            <Markdown html={task.spec_html} className="mt-2 border-l-2 border-line pl-3" />
          </details>
        )}
      </section>
      <section aria-labelledby="review-rounds">
        <h2 id="review-rounds">Rounds</h2>
        {rounds.length ? (
          <ol className="grid gap-3">
            {rounds.map((round) => (
              <Round key={round.n} round={round} standalone={task.worktree_path == null} />
            ))}
          </ol>
        ) : (
          <p className={muted}>No rounds yet.</p>
        )}
      </section>
      {approver && (
        <section aria-label="Approver" className="mt-8 rounded-md border border-line p-3">
          <p>
            <strong>{`Approver · ${approver.decision}`}</strong> <span className={muted}>{`round ${approver.n}`}</span>
          </p>
          <Markdown html={approver.body_html} className="mt-2" />
        </section>
      )}
      <section aria-labelledby="review-timeline">
        <h2 id="review-timeline">Timeline</h2>
        <ol className="grid gap-2">
          {timeline.map((entry) => (
            <li key={`${entry.kind}-${entry.id}`}>
              <Time iso={entry.created_at} /> {entry.label}
              {!blank(entry.body_md) && <Markdown html={entry.body_html} className="mt-1 ml-4" />}
            </li>
          ))}
        </ol>
      </section>
      <div className="mt-8">
        {rounds.length ? (
          // Q6: no `round`, so the backend files it on the latest one
          <CommentForm
            label="Comment"
            placeholder="Leave a comment…"
            send={(body_md) => addComment(task.id, { author: 'me', body_md })}
            onSent={onSent}
          />
        ) : (
          <p className={muted}>Comments open once a round is submitted.</p>
        )}
      </div>
    </>
  )
}

// --- Files changed (docs/ui.md §8.3) -----------------------------------------------------

/** 008 Q6: {"dir/": Map, name: file} in patch order; a directory sits where its first file is. */
function fileTree(files) {
  const root = new Map()
  for (const file of files) {
    const parts = file.path.split('/')
    let node = root
    for (const dir of parts.slice(0, -1)) {
      if (!node.has(`${dir}/`)) node.set(`${dir}/`, new Map())
      node = node.get(`${dir}/`)
    }
    node.set(parts.at(-1), file)
  }
  return root
}

/** Q2: plain fragment links, so the browser does the scrolling. */
function Tree({ node, nested = false }) {
  return (
    <ul className={nested ? 'pl-4' : ''}>
      {[...node].map(([name, child]) => (
        <li key={name}>
          {child instanceof Map ? (
            <>
              {name}
              <Tree node={child} nested />
            </>
          ) : (
            <a href={`#${encodeURI(`file:${child.path}`)}`}>
              {name} <span className="tabular-nums">{plusMinus(child)}</span>
            </a>
          )}
        </li>
      ))}
    </ul>
  )
}

/**
 * Q10: each code cell's highlight.js HTML, which escapes the text, or null when highlight.js doesn't know the
 * extension (no auto-detection). ponytail: line by line, so a construct spanning lines (a multi-line string or
 * comment) may be colored wrong, and every row of every file renders; highlight whole hunks, or collapse big
 * files, if that matters.
 */
function highlight(file) {
  if (!file.lang || !hljs.getLanguage(file.lang)) return null
  return file.rows.map((row) => row.side && hljs.highlight(row.text, { language: file.lang, ignoreIllegals: true }).value)
}

function CommentBody({ comment, where = false }) {
  return (
    <div className="comment">
      <strong>{comment.author}</strong>
      {where && comment.line != null && ` on line ${comment.line} (${comment.side})`}
      <Markdown html={comment.body_html} className="mt-1" />
    </div>
  )
}

/**
 * One file's header and diff table. Q3: a line row's id is the backend's `anchor`, and only the number on its
 * `side` links there. Q4: a plain <a>, so the browser sets the hash; its click also opens the inline form.
 */
function DiffFile({ file, form, onLine, inline }) {
  const html = useMemo(() => highlight(file), [file]) // once per loaded file, not when a form opens
  const number = (row, side) =>
    row[side] == null ? null : side === row.side ? (
      <a href={`#${encodeURI(row.anchor)}`} onClick={() => onLine(row.anchor)}>
        {row[side]}
      </a>
    ) : (
      row[side]
    )
  return (
    <section id={`file:${file.path}`}>
      <h2 className="mt-0 mb-1 flex flex-wrap items-baseline gap-2 text-base">
        <code className="wrap-anywhere">{file.path}</code>
        {file.change === 'renamed' ? (
          <>
            {' '}
            <span className={`font-normal ${muted}`}>
              {'(renamed from '}
              <code className="wrap-anywhere">{file.old_path}</code>
              {')'}
            </span>
          </>
        ) : (
          CHANGE[file.change] && (
            <>
              {' '}
              <span className={`font-normal ${muted}`}>{CHANGE[file.change]}</span>
            </>
          )
        )}{' '}
        <span className="ml-auto font-normal tabular-nums">{plusMinus(file)}</span>
      </h2>
      <div className="overflow-x-auto rounded-md border border-line">
        <table className="diff-table">
          <tbody>
            {file.rows.map((row, i) => (
              <Fragment key={i}>
                {row.side ? (
                  <tr id={row.anchor} className={row.kind}>
                    <td className="num">{number(row, 'old')}</td>
                    <td className="num">{number(row, 'new')}</td>
                    <td className="sign">{SIGN[row.kind]}</td>
                    <td>{html ? <code dangerouslySetInnerHTML={{ __html: html[i] }} /> : <code>{row.text}</code>}</td>
                  </tr>
                ) : (
                  <tr className={row.kind}>
                    <td colSpan={4}>{row.text}</td>
                  </tr>
                )}
                {row.comments.length > 0 && (
                  <tr className="comments">
                    <td colSpan={4}>
                      {row.comments.map((c) => (
                        <CommentBody key={c.id} comment={c} />
                      ))}
                    </td>
                  </tr>
                )}
                {row.anchor && row.anchor === form && (
                  <tr className="comments">
                    <td colSpan={4}>{inline(file.path, row)}</td>
                  </tr>
                )}
              </Fragment>
            ))}
            {file.orphans.length > 0 && (
              <tr className="comments">
                <td colSpan={4}>
                  {file.orphans.map((c) => (
                    <CommentBody key={c.id} comment={c} where />
                  ))}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function Files({ page, onSent }) {
  const [form, setForm] = useState(null) // Q5: the anchor whose inline form is open; page state, one at a time
  const { task, selected, files } = page
  if (!selected) return <p className={muted}>No rounds yet.</p>

  /** Q3, Q5: posts on the selected round, at the row's own side and number. */
  const inline = (path, row) => {
    const { side } = row
    const line = row[side]
    return (
      <CommentForm
        label={`Comment on ${path} line ${line} (${side})`}
        autoFocus
        send={(body_md) => addComment(task.id, { round: selected.n, author: 'me', path, line, side, body_md })}
        onSent={() => {
          setForm(null)
          onSent()
        }}
      >
        <button type="button" className={button} onClick={() => setForm(null)}>
          Cancel
        </button>
      </CommentForm>
    )
  }

  return (
    <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-[minmax(10rem,16rem)_minmax(0,1fr)]">
      <nav aria-label="Files" className="text-sm wrap-anywhere md:sticky md:top-4">
        <Tree node={fileTree(files)} />
      </nav>
      {/* grid-cols-1 is minmax(0, 1fr): an auto track would grow to the widest diff line and widen the page */}
      <div className="grid min-w-0 grid-cols-1 gap-6">
        {files.map((file) => (
          <DiffFile key={file.path} file={file} form={form} onLine={setForm} inline={inline} />
        ))}
      </div>
    </div>
  )
}

// --- The page ----------------------------------------------------------------------------

/** docs/ui.md §8 item 5: one round's review, with Conversation and Files changed tabs and my decision. */
export function ReviewPage() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const { hash } = useLocation()
  const round = params.get('round')
  const onFiles = params.get('tab') === 'files' // Q2: any other tab is Conversation
  // Q1: no polling. 022 Q3's `tick` gives usePoll a new load after each action; `tab` isn't a dep, so
  // switching tabs fetches nothing
  const [tick, setTick] = useState(0)
  const refresh = useCallback(() => setTick((n) => n + 1), [])
  const load = useCallback(() => reviewPage(id, round), [id, round, tick])
  const { data: page, error } = usePoll(load)
  const [summary, setSummary] = useState('')
  const [actionError, setActionError] = useState(null)
  const heading = page && `#${page.task.id} ${page.task.title}`
  useEffect(() => {
    if (heading) document.title = `${heading} · Review · Claude Factories`
  }, [heading])

  // Q4: a deep link scrolls to its line (or file) once the view-model has rendered; it opens no form
  const loaded = page != null
  useEffect(() => {
    if (!loaded || !hash) return
    let target
    try {
      target = decodeURIComponent(hash.slice(1))
    } catch {
      return // a malformed hash is ignored
    }
    document.getElementById(target)?.scrollIntoView()
  }, [loaded, hash])

  // Q12: a 404 is always not-found; other errors replace the page only until the first good load
  if (error?.status === 404) return <NotFound detail={error.message} />
  if (!page) return error ? <ErrorMessage error={error} /> : <p className={muted}>Loading…</p>
  const { task, rounds, selected } = page
  const off = !(task.status === 'review' && rounds.length > 0) // 009 Q2, Q3: only in review, with a round

  /** Q8: success or refusal, refetch; a success clears the summary and the alert, a refusal shows in it. */
  async function decide(call) {
    try {
      await call()
      setActionError(null)
      setSummary('')
    } catch (err) {
      setActionError(err)
    }
    refresh()
  }

  /** Q2: tab links keep the URL's `round`; Conversation drops `tab`. */
  const tabHref = (tab) => {
    const q = new URLSearchParams(round ? { round } : {})
    if (tab) q.set('tab', tab)
    const query = q.toString()
    return `/tasks/${task.id}/review${query ? `?${query}` : ''}`
  }
  const tabClass =
    '-mb-px border-b-2 border-transparent px-2 py-1 text-inherit hover:no-underline aria-[current=page]:border-current aria-[current=page]:font-semibold'

  return (
    <>
      {/* Q11: review.html's grid; the buttons sit on the title row, after Summary in tab order */}
      <header className="mb-6 grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-2">
        <nav aria-label="Breadcrumb" className="col-span-full text-sm">
          <Link to={`/projects/${task.project_id}`}>{task.project}</Link>
          {' › '}
          <Link to={`/tasks/${task.id}`}>{`#${task.id}`}</Link>
        </nav>
        <h1 className="col-start-1 row-start-2 wrap-anywhere">{heading}</h1>
        <p className="col-span-full flex flex-wrap items-center gap-x-3 gap-y-1">
          <StatusLine task={task} />
          {task.branch && <code className="text-sm wrap-anywhere">{task.branch}</code>}
          {rounds.length > 0 && (
            <label>
              {'round '}
              <select
                value={selected?.n}
                onChange={(e) => setParams(onFiles ? { round: e.target.value, tab: 'files' } : { round: e.target.value })}
                className={field}
              >
                {rounds.map((r) => (
                  <option key={r.n} value={r.n}>
                    {r.n}
                  </option>
                ))}
              </select>
            </label>
          )}
          {selected && (
            <span className="tabular-nums">
              {`${selected.files} file${selected.files === 1 ? '' : 's'} changed ${plusMinus(selected)}`}
            </span>
          )}
        </p>
        <div className="col-span-full mt-2 grid max-w-3xl gap-1">
          <label htmlFor="summary">Summary</label>
          <textarea
            id="summary"
            rows={2}
            placeholder="What should change? Required for Request changes."
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            disabled={off}
            className={field}
          />
        </div>
        <ActionButton
          className={`${button} col-start-2 row-start-2`}
          action={() => decide(() => requestChanges(task.id, summary))}
          disabled={off || blank(summary)}
        >
          Request changes
        </ActionButton>
        <ActionButton className={`${button} col-start-3 row-start-2`} action={() => decide(() => approveTask(task.id))} disabled={off}>
          Approve
        </ActionButton>
        {actionError && (
          <div className="col-span-full">
            <ErrorMessage error={actionError} />
          </div>
        )}
      </header>
      {error && <ErrorMessage error={error} />}
      {task.commit_hint && (
        <section aria-labelledby="review-commit" className="mb-6">
          <h2 id="review-commit" className="mt-0">
            Commit it yourself
          </h2>
          <p className={muted}>Done. The app never runs git; run these in a terminal.</p>
          <pre className="mt-2 overflow-x-auto rounded-md border border-line p-3 text-sm">
            {task.commit_hint}
          </pre>
        </section>
      )}
      <nav aria-label="Review tabs" className="mb-6 flex gap-4 border-b border-line">
        <Link to={tabHref()} aria-current={onFiles ? undefined : 'page'} className={tabClass}>
          Conversation
        </Link>
        <Link to={tabHref('files')} aria-current={onFiles ? 'page' : undefined} className={tabClass}>
          {`Files changed ${selected?.files ?? 0}`}
        </Link>
      </nav>
      {onFiles ? <Files key={selected?.n} page={page} onSent={refresh} /> : <Conversation page={page} onSent={refresh} />}
    </>
  )
}
