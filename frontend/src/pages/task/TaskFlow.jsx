import { MarkerType, ReactFlow } from '@xyflow/react'
import { useCallback, useMemo, useState } from 'react'
import { Link } from 'react-router'
import { taskFlow } from '../../api/pages.js'
import { AgentStats, agentLabel } from '../../components/AgentStats.jsx'
import { Markdown } from '../../components/Markdown.jsx'
import { field, muted, smallButton } from '../../components/styles.js'
import { usePoll } from '../../hooks/usePoll.js'
import { CONDITIONS, edgeTypes, nodeTypes, STATES, stateIcon, title } from '../factory/graph.jsx'

// the designer's arrowheads (FactoryPage's EDGE_OPTIONS); Q4: and no `×`, since nothing here deletes
const EDGE = { markerEnd: { type: MarkerType.ArrowClosed }, deletable: false }

/** AC22, AC23, AC24: the graph's nodes, read-only, each carrying its state for the card and an accessible name with it. */
function flowNodes(flow) {
  return flow.graph.nodes.map(({ id, type, position, data }) => {
    const { state, label, current } = flow.nodes[id]
    return {
      id,
      type,
      position,
      data: { ...data, state, label, current },
      draggable: false,
      connectable: false,
      deletable: false,
      ariaLabel: `${title(type, data)}: ${label}`,
      domAttributes: current ? { 'aria-current': 'step' } : undefined,
    }
  })
}

function Transcripts({ list }) {
  if (!list.length) return <p className={`text-sm ${muted}`}>No transcripts for this round.</p>
  return (
    <ul aria-label="Transcripts" className="grid gap-1 text-sm">
      {list.map((t) => (
        <li key={t.id}>
          <Link to={`/transcripts/${t.id}`}>{agentLabel(t)}</Link>
          <span className={muted}>
            {' · '}
            <AgentStats t={t} />
          </span>
        </li>
      ))}
    </ul>
  )
}

/** The request's per-type results: spec, build notes and diff, verdict and comments, decisions, or a condition's answer. */
function Result({ node: { type, data }, result }) {
  if (type === 'start') return <p className={`text-sm ${muted}`}>Where the run begins.</p>
  if (CONDITIONS.includes(type)) {
    return result.answer ? (
      <p>
        <strong>{result.answer}</strong> <span className={muted}>{result.why}</span>
      </p>
    ) : (
      <p className={muted}>Not reached.</p>
    )
  }
  return (
    <>
      {type === 'spec_writer' &&
        (result.spec_md?.trim() ? <Markdown html={result.spec_html} /> : <p className={muted}>No spec yet.</p>)}
      {type === 'builder' &&
        (result.diff_url ? (
          <>
            <p className="text-sm">
              <span className="tabular-nums">{`${result.files} files +${result.additions} −${result.deletions}`}</span>
              {' · '}
              <Link to={result.diff_url}>Diff</Link>
            </p>
            {result.build_md?.trim() ? (
              <Markdown html={result.build_html} />
            ) : (
              <p className={`text-sm ${muted}`}>No build notes.</p>
            )}
          </>
        ) : (
          <p className={muted}>Not built yet.</p>
        ))}
      {type === 'reviewer' &&
        (result.verdict ? (
          <>
            <p>
              <strong>{result.verdict.verdict}</strong>
            </p>
            <Markdown html={result.verdict.body_html} />
            {result.comments.length > 0 && (
              <ul aria-label="Comments" className="grid gap-2 text-sm">
                {result.comments.map((c, i) => (
                  <li key={i} className="border-l-2 border-line pl-2">
                    <p className={muted}>{c.path ? `${c.path}${c.line != null ? `:${c.line}` : ''}` : 'Conversation'}</p>
                    <Markdown html={c.body_html} />
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : (
          data.focus !== 'custom' && <p className={muted}>No verdict yet.</p>
        ))}
      {type === 'approver' &&
        (result.decisions.length ? (
          <ul aria-label="Decisions" className="grid gap-2">
            {result.decisions.map((d, i) => (
              <li key={i}>
                <p>
                  <strong>{`${d.actor} · ${d.decision}`}</strong>
                </p>
                <Markdown html={d.body_html} />
              </li>
            ))}
          </ul>
        ) : (
          <p className={muted}>No decision yet.</p>
        ))}
      <h4 className="mt-2 text-sm font-semibold">Transcripts</h4>
      <Transcripts list={result.transcripts} />
    </>
  )
}

/**
 * Q5: the clicked node's result beside the canvas from md up, under it below md; a plain section, which Close or Esc
 * (while focus is in it) closes. It reads the node from the current flow, so a round change or poll updates it.
 */
function Panel({ node, state, onClose }) {
  const name = `${title(node.type, node.data)} result`
  return (
    <section
      aria-label={name}
      onKeyDown={(event) => event.key === 'Escape' && onClose()}
      className="grid content-start gap-2 border-t border-line p-3 md:w-96 md:overflow-auto md:border-t-0 md:border-l"
    >
      <div className="flex items-start gap-2">
        <h3 className="mr-auto text-base wrap-anywhere">{name}</h3>
        <button type="button" onClick={onClose} className={smallButton}>
          Close
        </button>
      </div>
      <p className={`text-sm ${STATES[state.state].tone}`}>
        <span aria-hidden="true">{stateIcon(node.type, state.state)}</span> {state.label}
      </p>
      <Result node={node} result={state.result} />
    </section>
  )
}

/**
 * 089, docs/ui.md §8 item 4: the task's factory as a read-only graph, each node's state for the chosen round, and the
 * clicked node's result. AC28: refetched every 3 s while the run runs, once otherwise; with no manual pick it asks for
 * the latest round, so the selector follows a new one. A failed load (or a standalone task's null graph) shows nothing.
 */
export function TaskFlow({ taskId, running }) {
  const [picked, setPicked] = useState(null)
  const [open, setOpen] = useState(null)
  const load = useCallback(() => taskFlow(taskId, picked), [taskId, picked])
  const { data: flow } = usePoll(load, running ? 3000 : undefined)
  const nodes = useMemo(() => (flow?.graph ? flowNodes(flow) : []), [flow])
  const edges = useMemo(() => (flow?.graph ? flow.graph.edges.map((e) => ({ ...e, ...EDGE })) : []), [flow])
  if (!flow?.graph) return null
  const shown = open && flow.graph.nodes.find((n) => n.id === open)

  // AC26: React Flow makes each node a tab stop; Enter on one opens its panel
  function keyDown(event) {
    const id = event.key === 'Enter' && event.target.closest?.('.react-flow__node')?.dataset.id
    if (id) setOpen(id)
  }

  return (
    <section aria-labelledby="task-factory">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h2 id="task-factory" className="mr-auto">
          Factory
        </h2>
        <span className={`text-sm ${muted}`}>{flow.source ? `design ${flow.source.name}` : 'default graph'}</span>
        <label htmlFor="flow-round" className="text-sm">
          Round
        </label>
        <select
          id="flow-round"
          value={picked ?? flow.round}
          onChange={(event) => setPicked(Number(event.target.value))}
          className={field}
        >
          {flow.rounds.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </div>
      <div className="mt-2 flex flex-col overflow-hidden rounded-lg border border-line md:flex-row">
        {/* Q8: a fixed 20rem box; panning and zooming stay on */}
        <div className="h-80 min-w-0 md:flex-1" onKeyDown={keyDown}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            defaultMarkerColor={null}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            edgesFocusable={false}
            deleteKeyCode={null}
            onNodeClick={(_, node) => setOpen(node.id)}
            fitView
            minZoom={0.2}
          />
        </div>
        {shown && <Panel node={shown} state={flow.nodes[shown.id]} onClose={() => setOpen(null)} />}
      </div>
    </section>
  )
}
