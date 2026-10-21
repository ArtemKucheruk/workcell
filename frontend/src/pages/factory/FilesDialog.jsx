import hljs from 'highlight.js/lib/common'
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { downloadUrl, factoryFiles, writeFactory } from '../../api/factories.js'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { FactoryForm, FactoryResult } from '../../components/FactoryResult.jsx'
import { Block, Lines, Skeleton } from '../../components/Skeleton.jsx'
import { button } from '../../components/styles.js'
import { usePoll } from '../../hooks/usePoll.js'

// Q11: the file list beside the preview from md up, above it below md
const GRID = 'grid gap-4 md:grid-cols-[18rem_minmax(0,1fr)]'

/**
 * FE2, FE4, docs/MVP.md §4.5: highlight.js escapes the text, so its output is the only HTML inserted. Lines wrap: the
 * files are prose prompts, and a modal reads better without a sideways scroll. A focusable region, so it scrolls by key.
 */
function Preview({ file }) {
  const html = useMemo(
    () => hljs.highlight(file.content, { language: 'markdown', ignoreIllegals: true }).value,
    [file.content],
  )
  return (
    <div
      role="region"
      aria-label={file.path}
      tabIndex={0}
      className="max-h-[55dvh] min-h-48 overflow-auto rounded-md border border-line bg-raised"
    >
      <pre className="m-0 p-3 font-mono text-[0.85rem]/[1.5] whitespace-pre-wrap wrap-anywhere">
        <code dangerouslySetInnerHTML={{ __html: html }} />
      </pre>
    </div>
  )
}

/** FE2, FE3: one button per path, in the reply's order; the selected one is aria-current, as the code tree marks its file. */
function Files({ files, current, onSelect }) {
  return (
    <ul className="grid content-start gap-0.5">
      {files.map((file, i) => (
        <li key={file.path}>
          <button
            type="button"
            aria-current={i === current ? 'true' : undefined}
            onClick={() => onSelect(i)}
            className="w-full cursor-pointer rounded-md px-2 py-1 text-start font-mono text-sm wrap-anywhere hover:bg-raised aria-[current=true]:bg-raised aria-[current=true]:font-semibold aria-[current=true]:text-accent"
          >
            {file.path}
          </button>
        </li>
      ))}
    </ul>
  )
}

/** 046 Q5: the list beside the preview, in the loaded grid. */
function FilesSkeleton() {
  return (
    <Skeleton>
      <div className={GRID}>
        <Lines n={8} />
        <Block className="h-64" />
      </div>
    </Skeleton>
  )
}

/**
 * FE1–FE11, Q11: the compiled files of the stored graph. Mounted on open, shown with showModal (Close, first, takes
 * focus), and fetched as it mounts, the way DeleteDialog works; `onClose` follows every close, Esc included, so the
 * designer unmounts it and the next open fetches again. `unsaved` is the designer's state, which this never compiles.
 */
export function FilesDialog({ id, unsaved, onClose }) {
  const titleId = useId()
  const dialog = useRef(null)
  const { data: files, error } = usePoll(useCallback(() => factoryFiles(id), [id]))
  const [current, setCurrent] = useState(0)
  const [out, setOut] = useState(null)

  // StrictMode runs this twice; showModal on an open dialog throws
  useEffect(() => {
    if (!dialog.current.open) dialog.current.showModal()
  }, [])

  /** FE6–FE8: a refusal is the result too, a red alert under the form; the file list stays. */
  async function write(overwrite) {
    try {
      setOut(await writeFactory(id, overwrite))
    } catch (err) {
      setOut(err)
    }
  }

  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      onClose={onClose}
      className="m-auto max-h-[calc(100dvh-2rem)] w-5xl max-w-[calc(100vw-2rem)] overflow-y-auto rounded-lg border border-line bg-surface p-5 text-left text-base font-normal text-fg shadow-xl backdrop:bg-surface/80"
    >
      <div className="grid gap-4">
        <div className="flex items-center justify-between gap-3">
          <h2 id={titleId} className="m-0">
            Files
          </h2>
          <button type="button" onClick={() => dialog.current.close()} className={button}>
            Close
          </button>
        </div>
        {/* FE10: a warning edge, fg text, so it reads at 4.5:1 in both schemes */}
        {unsaved && (
          <p className="rounded-md border border-line border-l-4 border-l-warning px-3 py-2 text-sm">
            Showing the last saved design. Save to include your changes.
          </p>
        )}
        {files ? (
          <>
            <div className={GRID}>
              <Files files={files} current={current} onSelect={setCurrent} />
              {files[current] && <Preview file={files[current]} />}
            </div>
            <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
              <a href={downloadUrl(id)} download className={`${button} hover:no-underline`}>
                Download .zip
              </a>
              <FactoryForm label="Write to repo" create={write} />
            </div>
            <div aria-live="polite">{out && <FactoryResult out={out} />}</div>
          </>
        ) : error ? (
          <ErrorMessage error={error} />
        ) : (
          <FilesSkeleton />
        )}
      </div>
    </dialog>
  )
}
