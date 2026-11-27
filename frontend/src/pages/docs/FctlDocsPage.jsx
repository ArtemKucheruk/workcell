import { useEffect } from 'react'
import { useLocation } from 'react-router'
import { fctlDoc } from '../../api/pages.js'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { Markdown } from '../../components/Markdown.jsx'
import { Lines, Skeleton } from '../../components/Skeleton.jsx'
import { usePoll } from '../../hooks/usePoll.js'

/**
 * docs/ui.md §8 item 7: the fctl reference, pre-rendered by the backend from fctl.md, with a Contents nav built
 * from its headings (Q2: every heading, flat, in document order). Heading texts render as React text.
 */
export function FctlDocsPage() {
  // no polling: the content is static per build; fctlDoc is module-level, so usePoll gets a stable fn
  const { data: doc, error } = usePoll(fctlDoc)
  const { hash } = useLocation()
  useEffect(() => {
    document.title = 'fctl reference · Workcell'
  }, [])

  // Q9: ReviewPage's Q4 deep link, copied: scroll to the hash's heading once the content has rendered
  const loaded = doc != null
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

  return (
    <>
      <h1 className="mb-6">fctl reference</h1>
      {!doc ? (
        error ? (
          <ErrorMessage error={error} />
        ) : (
          // 046 Q5: under the static h1, the Contents column and the text in the page's grid
          <Skeleton>
            <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-[minmax(10rem,16rem)_minmax(0,1fr)]">
              <Lines n={8} />
              <Lines n={12} />
            </div>
          </Skeleton>
        )
      ) : (
        // Q10: the code page's grid; minmax(0, 1fr) and min-w-0 keep a wide code block from widening the page
        <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-[minmax(10rem,16rem)_minmax(0,1fr)]">
          <nav aria-label="Contents" className="text-sm wrap-anywhere">
            <ul>
              {doc.headings.map((h, i) => (
                <li key={i}>
                  <a href={`#${h.id}`}>{h.text}</a>
                </li>
              ))}
            </ul>
          </nav>
          {/* round 1 ux: a wide table scrolls in its own box too, like the code blocks */}
          <Markdown html={doc.body_html} className="min-w-0 [&_table]:block [&_table]:overflow-x-auto" />
        </div>
      )}
    </>
  )
}
