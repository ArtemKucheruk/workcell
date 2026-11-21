import { Item } from './Menu.jsx'
import { popover, smallButton } from './styles.js'

/**
 * 102 AC25, Q11: why runs can't start, from a page's `runs_enabled`, `runs_active`, and `max_concurrent_runs`; null when
 * they can. 103 AC20: moved here from the Workflows page, so the automation runs page says the same.
 */
export function runsOff(page) {
  if (!page.runs_enabled) return 'Not signed in — runs disabled'
  if (page.runs_active >= page.max_concurrent_runs) return `${page.runs_active} of ${page.max_concurrent_runs} runs active`
  return null
}

/** 097 AC27: a usage window as a whole percentage, `—` while it's unknown. */
const percent = (w) => (w ? `${Math.round(w.utilization * 100)}%` : '—')

/**
 * 097 AC27, AC28: the ▾ beside Run, Retry, or Run now, a native popover menu: Auto with the account it would pick (`auto`,
 * from the DB, Q9), or `all near limits` with none, then every account with its 5h and 7d usage, the preferred one marked
 * in text. Choosing one calls `onRun` with its id (Auto with null). 102 AC23: moved here from the task page; `id` names
 * the popover and its anchor, so each automation row on the Workflows page has its own. `title` explains `disabled`.
 */
export function RunMenu({ id, accounts, auto, disabled, title, onRun, label = 'Choose account' }) {
  return (
    <>
      <button
        type="button"
        popoverTarget={id}
        aria-label={label}
        disabled={disabled}
        title={title}
        style={{ anchorName: `--${id}` }}
        className={`${smallButton} -ml-2`}
      >
        <span aria-hidden="true">▾</span>
      </button>
      <div
        id={id}
        popover="auto"
        aria-label="Run as"
        style={{ positionAnchor: `--${id}` }}
        className={`${popover} w-80 max-w-[90vw] p-1 open:grid [position-area:bottom_span-left]`}
      >
        <Item menu={id} onClick={() => onRun(null)}>
          {auto ? `Auto (→ ${auto.label})` : 'Auto (all near limits)'}
        </Item>
        {accounts.map((a) => (
          <Item key={a.id} menu={id} onClick={() => onRun(a.id)} className="wrap-anywhere">
            {`${a.label} · 5h ${percent(a.five_hour)} · 7d ${percent(a.seven_day)}${a.active ? ' · preferred' : ''}`}
          </Item>
        ))}
      </div>
    </>
  )
}
