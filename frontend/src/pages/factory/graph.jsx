import { BaseEdge, EdgeLabelRenderer, getBezierPath, getSmoothStepPath, Handle, Position, useNodesData, useReactFlow } from '@xyflow/react'

// docs/data-model-and-api.md §6.1: the node types, in the contract's table order
export const AGENTS = ['spec_writer', 'builder', 'reviewer', 'approver', 'custom_agent']
export const CONDITIONS = ['all_pass', 'any_changes', 'rounds_below', 'approved']
export const isAgent = (type) => AGENTS.includes(type)

/**
 * The contract's table: each type's palette label, Q9's base name for a new agent and the data key its summary adds,
 * a condition's question (its card title), and what start and the conditions do (the side panel's sentence).
 */
export const KINDS = {
  start: { about: 'Where a run begins. Nothing leads into it, and its one output goes to the first agent.' },
  spec_writer: { label: 'Spec writer', base: 'spec-writer' },
  builder: { label: 'Builder', base: 'builder', extra: 'side' },
  reviewer: { label: 'Reviewer', base: 'reviewer', extra: 'focus' },
  approver: { label: 'Approver', base: 'approver' },
  custom_agent: { label: 'Custom agent', base: 'agent' },
  all_pass: {
    label: 'All reviews PASS',
    question: () => 'All reviews PASS?',
    about: 'Yes when every verdict on the latest round is PASS, else no.',
  },
  any_changes: {
    label: 'Any review CHANGES',
    question: () => 'Any review CHANGES?',
    about: 'Yes when any verdict on the latest round is CHANGES, else no.',
  },
  rounds_below: {
    label: 'Rounds used < N',
    question: (data) => `Rounds used < ${data.n}?`,
    about: 'Yes while this run has used fewer than N rounds, else no.',
  },
  approved: {
    label: 'Decision APPROVE',
    question: () => 'Decision APPROVE?',
    about: "Yes when the approver's decision is APPROVE, else no.",
  },
}

/** FE10, Q10: an agent's name, a condition's question with `n` filled in, or Start. */
export const title = (type, data) => (type === 'start' ? 'Start' : isAgent(type) ? data.name : KINDS[type].question(data))

/** Q10: an agent's kind, then its side or focus, then its model; `Condition` for a condition; nothing for start. */
function summary(type, data) {
  if (type === 'start') return ''
  if (!isAgent(type)) return 'Condition'
  const { label, extra } = KINDS[type]
  return [label, extra && data[extra], data.model].filter(Boolean).join(' · ')
}

// Q9: crypto.randomUUID needs a secure context; a plain-http LAN address isn't one
export const newId = () => crypto.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`

/** Q9: a palette node: a fresh id, and for an agent the first free `<base>`, `<base>-2`, … among the agents' names. */
export function newNode(type, nodes, position) {
  let data = type === 'rounds_below' ? { n: 2 } : {}
  if (isAgent(type)) {
    const taken = new Set(nodes.filter((n) => isAgent(n.type)).map((n) => n.data.name))
    const { base } = KINDS[type]
    let name = base
    for (let i = 2; taken.has(name); i++) name = `${base}-${i}`
    data = { name, description: '', model: 'inherit', tools: [], prompt: '' }
    if (type === 'builder') data.side = 'both'
    if (type === 'reviewer') data.focus = 'custom'
  }
  return { id: newId(), type, position, data, selected: true }
}

// Q10: one 20 px stroke drawing per type, in currentColor; no icon package
const PATHS = {
  start: 'M7 5.5v9l7-4.5z',
  spec_writer: 'M6 2.5h5.5L15 6v11.5H6zM11.5 2.5V6H15M8.5 10h4M8.5 13h4',
  builder: 'M7.5 6 3.5 10l4 4M12.5 6l4 4-4 4',
  reviewer: 'M8.5 3.5a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12.2 12.2l4.3 4.3',
  approver: 'M10 2.5a7.5 7.5 0 1 0 0 15 7.5 7.5 0 0 0 0-15zM7 10l2 2 4-4',
  custom_agent: 'M10 3l1.6 4.4L16 9l-4.4 1.6L10 15l-1.6-4.4L4 9l4.4-1.6z',
  all_pass: 'M3 6l1.5 1.5L7 5M3 13l1.5 1.5L7 12M10 6.5h7M10 13.5h7',
  any_changes: 'M12.5 4.5l3 3L8 15H5v-3zM11 6l3 3',
  rounds_below: 'M15.5 10a5.5 5.5 0 1 1-1.6-3.9M15.5 3.5v3h-3',
  approved: 'M5 17.5v-14M5 4h9.5l-2 3 2 3H5',
}

export function Icon({ type, className = '' }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`size-4 shrink-0 ${className}`}
    >
      <path d={PATHS[type]} />
    </svg>
  )
}

/** Each group's icon color, the same on the cards, the palette, and the side panel. */
export const tint = (type) => (type === 'start' ? 'text-success' : isAgent(type) ? 'text-accent' : 'text-warning')

// handles: 10 px dots, ringed in the flow's surface (index.css), so a line ending on one stays readable
const dot = 'size-2.5'

/**
 * FE10: a card: its kind's icon in a tile, the title, and the one-line summary, each cut with an ellipsis and whole in
 * `title`. A condition's is dashed and keeps room on its right for the yes and no words.
 */
function Card({ type, data, selected, className = '', children }) {
  const name = title(type, data)
  const sub = summary(type, data)
  return (
    <div
      className={`relative flex items-center gap-2.5 rounded-lg border bg-raised py-2 pl-2 text-sm text-fg shadow-sm ${
        selected ? 'border-accent ring-1 ring-accent' : 'border-line'
      } ${className}`}
    >
      <span className={`grid size-7 shrink-0 place-items-center rounded-md border border-line bg-surface ${tint(type)}`}>
        <Icon type={type} />
      </span>
      <span className="grid min-w-0">
        <span title={name} className="truncate font-medium">
          {name}
        </span>
        {sub && (
          <span title={sub} className="truncate text-xs text-muted">
            {sub}
          </span>
        )}
      </span>
      {children}
    </div>
  )
}

function StartNode({ type, data, selected }) {
  return (
    <Card type={type} data={data} selected={selected} className="pr-4">
      <Handle type="source" position={Position.Right} className={dot} />
    </Card>
  )
}

function AgentNode({ type, data, selected }) {
  return (
    <Card type={type} data={data} selected={selected} className="w-56 pr-3">
      <Handle type="target" position={Position.Left} className={dot} />
      <Handle type="source" position={Position.Right} className={dot} />
    </Card>
  )
}

/** FE11: `yes` in success and `no` in danger, each a dot with its word beside it, inside the card. */
function Branch({ id, className }) {
  return (
    <Handle type="source" id={id} position={Position.Right} className={`${dot} ${className}`}>
      <span className="absolute top-1/2 right-3 -translate-y-1/2 text-xs font-medium">{id}</span>
    </Handle>
  )
}

function ConditionNode({ type, data, selected }) {
  return (
    <Card type={type} data={data} selected={selected} className="w-60 border-dashed pr-11">
      <Handle type="target" position={Position.Left} className={dot} />
      <Branch id="yes" className="top-1/3 border-success bg-success text-success" />
      <Branch id="no" className="top-2/3 border-danger bg-danger text-danger" />
    </Card>
  )
}

// docs: memoized by React Flow; module level, so they're one object for the page's life
export const nodeTypes = {
  start: StartNode,
  ...Object.fromEntries(AGENTS.map((type) => [type, AgentNode])),
  ...Object.fromEntries(CONDITIONS.map((type) => [type, ConditionNode])),
}

/**
 * FE15: every edge (React Flow's `default` type, overridden) has a `×` at its midpoint. The button deletes through React
 * Flow, so the removal reaches the page's onEdgesChange like a Backspace would. A forward edge is a curve; one that runs
 * back (the loop's `rounds yes → builder`) steps around in right angles, since a curve would cut across the cards.
 */
function DeletableEdge({ id, source, target, markerEnd, ...ends }) {
  const { deleteElements } = useReactFlow()
  const [from, to] = useNodesData([source, target])
  const [path, x, y] = ends.targetX < ends.sourceX ? getSmoothStepPath({ ...ends, borderRadius: 8 }) : getBezierPath(ends)
  const label = `Delete edge ${from ? title(from.type, from.data) : source} → ${to ? title(to.type, to.data) : target}`
  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} />
      <EdgeLabelRenderer>
        <button
          type="button"
          aria-label={label}
          title={label}
          onClick={() => deleteElements({ edges: [{ id }] })}
          style={{ transform: `translate(-50%, -50%) translate(${x}px, ${y}px)` }}
          className="nodrag nopan pointer-events-auto absolute grid size-5 cursor-pointer place-items-center rounded-full border border-line bg-surface text-xs/none text-muted hover:border-danger hover:text-danger"
        >
          ×
        </button>
      </EdgeLabelRenderer>
    </>
  )
}

export const edgeTypes = { default: DeletableEdge }
