import { useEffect, useId, useRef, useState } from 'react'
import { saveProjectContext } from '../../api/projects.js'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { Markdown } from '../../components/Markdown.jsx'
import { button, field, muted } from '../../components/styles.js'

/** Q3: the pinned card, built from GET /api/projects/{id}/context rather than stored as a row. */
export const PINNED = 'Stack and conventions'
export const PINNED_TEXT = 'Agents read it at the top of fctl show.'

const utf8 = (text) => new TextEncoder().encode(text).length

// board Q10: the autofocus attribute, which showModal focuses; React's autoFocus focuses on mount, before the dialog shows
const autofocus = (el) => el?.setAttribute('autofocus', '')

/**
 * FE3, FE11: a modal `<dialog>` like the Files dialog: its heading, Close at the right, then `children`. Shown with
 * showModal as it mounts; `onClose` follows every close, Close, Esc, and a save's included, so the opener unmounts it.
 * `ref` is the `<dialog>`, for a save to close it. `size` is a width class written out in full, for Tailwind's scanner.
 */
export function Modal({ heading, size, onClose, ref, children }) {
  const id = useId()
  const own = useRef(null)
  const dialog = ref ?? own

  // StrictMode runs this twice; showModal on an open dialog throws
  useEffect(() => {
    if (!dialog.current.open) dialog.current.showModal()
  }, [dialog])

  return (
    <dialog
      ref={dialog}
      aria-labelledby={id}
      onClose={(event) => {
        // React passes a dialog's close up the tree, to a group modal holding this one
        event.stopPropagation()
        onClose()
      }}
      className={`m-auto max-h-[calc(100dvh-2rem)] ${size} max-w-[calc(100vw-2rem)] overflow-y-auto rounded-lg border border-line bg-surface p-5 text-left text-base font-normal text-fg shadow-xl backdrop:bg-surface/80`}
    >
      <div className="grid gap-4">
        <div className="flex items-start justify-between gap-3">
          <h2 id={id} className="m-0 wrap-anywhere">
            {heading}
          </h2>
          <button type="button" onClick={() => dialog.current.close()} className={button}>
            Close
          </button>
        </div>
        {children}
      </div>
    </dialog>
  )
}

/** 033 FE19, FE20: the live UTF-8 count against the cap; over it, `over the limit` in danger. */
function Size({ bytes, max }) {
  const over = bytes > max
  return (
    <span className={`text-sm tabular-nums ${over ? 'font-semibold text-danger' : muted}`}>
      {`${bytes} / ${max} bytes${over ? ' · over the limit' : ''}`}
    </span>
  )
}

/** 033 Q10: the saved version as the backend rendered it, since the SPA renders no markdown. */
function Preview({ md, html }) {
  const id = useId()
  return (
    <section aria-labelledby={id} className="grid min-w-0 content-start gap-2">
      <h3 id={id} className="m-0 font-semibold">
        Preview
      </h3>
      <div className="max-h-[60dvh] overflow-auto rounded-md border border-line p-4">
        {md.trim() ? <Markdown html={html} /> : <p className={muted}>Nothing saved yet.</p>}
      </div>
    </section>
  )
}

/** Content's textarea, monospace like the code it often holds. */
function ContentField({ value, onChange, ref }) {
  return (
    <label className="grid gap-1">
      Content
      <textarea
        ref={ref}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        rows={16}
        placeholder="Markdown, e.g. # API conventions"
        className={`${field} font-mono text-sm`}
      />
    </label>
  )
}

/**
 * FE4–FE7, Q10: New card and Edit (Title, Description, Content and its count, and on Edit the saved Preview), and New
 * group and a group's Edit (Title and Description). `save` sends the fields and reloads the items; a success closes the
 * dialog, and a refusal shows inside, which stays open with what was typed.
 */
export function CardDialog({ heading, item, group, maxBytes, save, onClose }) {
  const id = useId()
  const dialog = useRef(null)
  const [content, setContent] = useState(item?.content_md ?? '')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const bytes = utf8(content)
  const edit = item && !group

  async function submit(event) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const fields = { title: form.get('title'), description: form.get('description') }
    if (!group) fields.content_md = content
    setBusy(true)
    setError(null)
    try {
      await save(fields)
    } catch (err) {
      setError(err)
      setBusy(false)
      return
    }
    dialog.current?.close()
  }

  return (
    <Modal ref={dialog} heading={heading} size={group ? 'w-md' : edit ? 'w-6xl' : 'w-3xl'} onClose={onClose}>
      <div className={edit ? 'grid items-start gap-6 lg:grid-cols-2' : 'grid'}>
        <form onSubmit={submit} className="grid min-w-0 gap-3">
          {item?.source_path && <p className={`font-mono text-xs wrap-anywhere ${muted}`}>{item.source_path}</p>}
          <label className="grid gap-1">
            Title
            <input ref={autofocus} name="title" required defaultValue={item?.title} className={field} />
          </label>
          <label className="grid gap-1">
            Description
            <input
              name="description"
              maxLength={160}
              defaultValue={item?.description}
              aria-describedby={`${id}-hint`}
              className={field}
            />
          </label>
          <p id={`${id}-hint`} className={`-mt-2 text-sm ${muted}`}>
            Shown on the card. Up to 160 characters.
          </p>
          {!group && <ContentField value={content} onChange={setContent} />}
          <div className="flex flex-wrap items-center gap-3">
            <button disabled={busy || (!group && bytes > maxBytes)} className={button}>
              Save
            </button>
            {!group && <Size bytes={bytes} max={maxBytes} />}
          </div>
          {error && <ErrorMessage error={error} />}
        </form>
        {edit && <Preview md={item.content_md} html={item.content_html} />}
      </div>
    </Modal>
  )
}

/**
 * FE3: 033's editor in the pinned card's dialog. `saved` is the last GET or PUT reply, which the Preview shows; `draft`
 * and `bytes` stay null until typed. A save stays open, so the Preview's update shows, and hands the reply to the page
 * (`onSaved`), so the next open starts from it.
 */
export function PinnedDialog({ projectId, loaded, onSaved, onClose }) {
  const [saved, setSaved] = useState(loaded)
  const [draft, setDraft] = useState(null)
  const [bytes, setBytes] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const text = draft ?? saved.context_md
  const size = bytes ?? saved.bytes

  async function save(event) {
    event.preventDefault()
    setBusy(true)
    try {
      const reply = await saveProjectContext(projectId, text)
      setSaved(reply)
      onSaved(reply)
      setBytes(null) // the reply's count, until the next keystroke
      setError(null)
    } catch (err) {
      setError(err) // the draft and the old Preview stay
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal heading={PINNED} size="w-6xl" onClose={onClose}>
      <p className={`-mt-2 text-sm ${muted}`}>{PINNED_TEXT}</p>
      <div className="grid items-start gap-6 lg:grid-cols-2">
        <form onSubmit={save} className="grid min-w-0 gap-3">
          <ContentField
            ref={autofocus}
            value={text}
            onChange={(value) => {
              setDraft(value)
              setBytes(utf8(value))
            }}
          />
          <div className="flex flex-wrap items-center gap-3">
            <button disabled={busy || size > saved.max_bytes} className={button}>
              Save
            </button>
            <Size bytes={size} max={saved.max_bytes} />
          </div>
          {error && <ErrorMessage error={error} />}
        </form>
        <Preview md={saved.context_md} html={saved.context_html} />
      </div>
    </Modal>
  )
}
