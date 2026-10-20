// 043 Q2: the one chip format, `sec ✓`, on every page; the board adds its `r2` before them
const SHORT = { security: 'sec', ux: 'ux', ui: 'ui', code: 'code' }
const SYMBOL = { PASS: '✓', CHANGES: '✗', pending: '·' }
// Q8: the whole label takes the verdict's color; an unknown verdict shows as it is, muted
const TONE = { PASS: 'text-success', CHANGES: 'text-danger', pending: 'text-muted' }

const blank = (md) => !md?.trim()

/**
 * 023 Q1: a verdict with a body opens it as a native popover; pending or bodiless ones are plain text.
 * 024 Q9: the review page passes no `posted`, so its chips are always the plain <span>.
 * Q2: nowrap, so a narrow row breaks between chips, not inside one.
 */
export function Chip({ n, who, verdict, posted }) {
  const text = `${SHORT[who] ?? who} ${SYMBOL[verdict] ?? verdict}`
  const title = `${who}: ${verdict}`
  const tone = TONE[verdict] ?? 'text-muted'
  if (blank(posted?.body_md)) return <span title={title} className={`whitespace-nowrap ${tone}`}>{text}</span>
  return (
    <button
      type="button"
      popoverTarget={`verdict-${n}-${who}`}
      title={title}
      className={`cursor-pointer whitespace-nowrap underline decoration-dotted underline-offset-2 hover:text-accent ${tone}`}
    >
      {text}
    </button>
  )
}
