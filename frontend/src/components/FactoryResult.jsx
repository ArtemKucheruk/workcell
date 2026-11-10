import { useState } from 'react'
import { ErrorMessage } from './ErrorMessage.jsx'
import { button } from './styles.js'

const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`

/**
 * Board Q8, moved twice (052): the Overwrite checkbox and the button, for Settings' Create factory and the designer's
 * Write to repo. `create(overwrite)` never rejects; the button is disabled while it runs.
 */
export function FactoryForm({ label, create }) {
  const [busy, setBusy] = useState(false)
  async function submit(event) {
    event.preventDefault()
    const overwrite = event.currentTarget.elements.overwrite.checked
    setBusy(true)
    try {
      await create(overwrite)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-3">
      <button disabled={busy} className={button}>
        {label}
      </button>
      <label className="flex items-center gap-1">
        <input type="checkbox" name="overwrite" /> Overwrite existing files
      </label>
    </form>
  )
}

/** A bulleted list of repo paths in mono; 059 Settings' legacy note lists `factory_files` with it too. */
export function FileList({ paths }) {
  return (
    <ul className="ml-6 list-disc">
      {paths.map((path) => (
        <li key={path}><code>{path}</code></li>
      ))}
    </ul>
  )
}

/**
 * MVP §3.2, 052 FE7, FE12: what a write of factory files wrote and skipped, and the commit command; or its refusal.
 * Settings' Create factory and the designer's Write to repo both show it.
 */
export function FactoryResult({ out }) {
  if (out instanceof Error) return <ErrorMessage error={out} />
  return (
    <div className="grid gap-1 rounded-md border border-line p-3">
      {out.written.length > 0 && (
        <>
          <p>{`Wrote ${plural(out.written.length, 'file')}:`}</p>
          <FileList paths={out.written} />
        </>
      )}
      {out.skipped.length > 0 && (
        <>
          <p>{`Skipped ${plural(out.skipped.length, 'existing file')} (tick Overwrite to replace them):`}</p>
          <FileList paths={out.skipped} />
        </>
      )}
      <p>Commit them so runs can see the factory:</p>
      <pre className="overflow-x-auto rounded bg-raised p-2 text-sm"><code>{out.commit_hint}</code></pre>
    </div>
  )
}
