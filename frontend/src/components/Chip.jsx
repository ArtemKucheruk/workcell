// 023 Q9: task.html's chip labels and §8.1's legend; the board's differ (`co`, no space)
const SHORT = { security: 'sec', ux: 'ux', ui: 'ui', code: 'code' }
const SYMBOL = { PASS: '✓', CHANGES: '✗', pending: '·' }

const blank = (md) => !md?.trim()

/**
 * 023 Q1: a verdict with a body opens it as a native popover; pending or bodiless ones are plain text.
 * 024 Q9: the review page passes no `posted`, so its chips are always the plain <span>.
 */
export function Chip({ n, who, verdict, posted }) {
  const text = `${SHORT[who] ?? who} ${SYMBOL[verdict] ?? verdict}`
  const title = `${who}: ${verdict}`
  if (blank(posted?.body_md)) return <span title={title}>{text}</span>
  return (
    <button
      type="button"
      popoverTarget={`verdict-${n}-${who}`}
      title={title}
      className="cursor-pointer underline decoration-dotted underline-offset-2 hover:text-blue-700 dark:hover:text-blue-400"
    >
      {text}
    </button>
  )
}
