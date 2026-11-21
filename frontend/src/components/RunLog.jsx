import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router'
import { runLog } from '../api/runs.js'
import { usePoll } from '../hooks/usePoll.js'
import { muted } from './styles.js'

/**
 * Q5: the run's log as text, from `after=0`. usePoll fetches every 3 s while the run is running and once
 * otherwise, so the run stopping gives one last fetch. Keyed by run id, so a new run starts a fresh cursor.
 * ponytail: the whole log stays in memory and in the DOM; window it if logs get big.
 * 053 Q7: `#run-log` (the Agents page's Run log link) opens it as it mounts and scrolls to it; jsdom has no scrollIntoView.
 * 103: moved here from the task page; `open` opens it as it mounts too (the automation runs page's picked run).
 */
export function RunLog({ run, open = false }) {
  const [lines, setLines] = useState([])
  const cursor = useRef(0)
  const box = useRef(null)
  const panel = useRef(null)
  const { hash } = useLocation()
  const [linked] = useState(hash === '#run-log') // as it mounts only: a later toggle is mine
  useEffect(() => {
    if (linked) panel.current.scrollIntoView?.()
  }, [linked])
  const load = useCallback(async () => {
    const after = cursor.current
    const reply = await runLog(run.id, after).catch(() => null) // a failed fetch shows nothing; the next poll retries
    if (!reply || cursor.current !== after) return // the cursor moved: an overlapping fetch already appended these
    cursor.current = reply.next
    if (reply.lines.length) setLines((old) => [...old, ...reply.lines])
  }, [run.id])
  usePoll(load, run.status === 'running' ? 3000 : undefined)
  const end = () => {
    box.current.scrollTop = box.current.scrollHeight
  }
  useEffect(end, [lines])
  return (
    <details ref={panel} id="run-log" open={linked || open} onToggle={end} className="mt-8 scroll-mt-6">
      <summary className="cursor-pointer font-semibold">{`Run log · run #${run.id}`}</summary>
      <div
        ref={box}
        className="mt-2 max-h-96 overflow-auto rounded-md bg-raised p-3 font-mono text-sm whitespace-pre-wrap wrap-anywhere"
      >
        {lines.length ? lines.map((line, i) => <div key={i}>{line.text}</div>) : <p className={muted}>No output yet.</p>}
      </div>
    </details>
  )
}
