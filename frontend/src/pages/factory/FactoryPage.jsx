import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  Controls,
  MarkerType,
  ReactFlow,
  ReactFlowProvider,
  useNodesInitialized,
  useReactFlow,
} from '@xyflow/react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router'
import { getFactory, saveFactory } from '../../api/factories.js'
import { ActionButton } from '../../components/ActionButton.jsx'
import { Breadcrumbs, projectTrail } from '../../components/Breadcrumbs.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { Block, ButtonBlock, Crumbs, Skeleton } from '../../components/Skeleton.jsx'
import { button, muted } from '../../components/styles.js'
import { usePoll } from '../../hooks/usePoll.js'
import { FilesDialog } from './FilesDialog.jsx'
import { AGENTS, CONDITIONS, edgeTypes, newId, newNode, nodeTypes } from './graph.jsx'
import { NodePanel } from './NodePanel.jsx'
import { DRAG, Palette } from './Palette.jsx'

// FE18: React Flow's own bookkeeping, which leaves the page saved; every other change is an edit
const QUIET = new Set(['select', 'dimensions'])
const edits = (changes) => changes.some((change) => !QUIET.has(change.type))

const PALETTE = new Set([...AGENTS, ...CONDITIONS])
// an arrowhead on every edge, drawn in the edge's stroke: defaultMarkerColor={null} leaves it to index.css's variable
const EDGE_OPTIONS = { markerEnd: { type: MarkerType.ArrowClosed } }
const DELETE_KEYS = ['Backspace', 'Delete']
const KIND_LABELS = { workflow: 'Workflow', automation: 'Automation' } // 101 AC18

/**
 * Round-1 review-ui: the first view is readable. The whole loop shows when it fits at 0.8× or more (up to 1×), centred;
 * a wider one opens at 0.8× from its left edge, so it reads from Start, and Fit View still shows all of it. Along each
 * axis, `place` centres the bounds when they fit inside PAD on both sides, else puts their start PAD in.
 */
const FIRST_ZOOM = 0.8
const PAD = 40
const place = (size, start, extent, zoom) =>
  extent * zoom > size - 2 * PAD ? PAD - start * zoom : (size - extent * zoom) / 2 - start * zoom

// the designer's frame: from md up it fills the window under the title row; below md the flow is 60vh, with the
// palette above it and the Node panel under it
const FRAME = 'md:h-[calc(100dvh-8rem)] md:min-h-120'
const FLOW = 'h-[60vh] min-h-80 md:h-auto'

/** FE19: the graph as stored: only the contract's keys, and a null sourceHandle for an agent's or start's edge. */
const stored = (nodes, edges) => ({
  nodes: nodes.map(({ id, type, position: { x, y }, data }) => ({ id, type, position: { x, y }, data })),
  edges: edges.map(({ id, source, sourceHandle, target }) => ({ id, source, sourceHandle: sourceHandle ?? null, target })),
})

/**
 * FE9–FE23: the designer. `version` counts edits and `saved` is the version the last good PUT carried, so an edit made
 * while a save is pending stays unsaved.
 */
function Designer({ factory }) {
  const { screenToFlowPosition, getNodesBounds, setViewport } = useReactFlow()
  // Q11: start is the one node the delete key skips
  const [nodes, setNodes] = useState(() => factory.graph.nodes.map((n) => (n.type === 'start' ? { ...n, deletable: false } : n)))
  const [edges, setEdges] = useState(factory.graph.edges)
  const [version, setVersion] = useState(0)
  const [saved, setSaved] = useState(0)
  const [error, setError] = useState(null)
  const [showFiles, setShowFiles] = useState(false)
  const flow = useRef(null)
  const saveButton = useRef(null)
  const dirty = version !== saved
  const touch = useCallback(() => setVersion((v) => v + 1), [])

  // once, as soon as React Flow has measured every node; before paint, so the unplaced view never shows
  const measured = useNodesInitialized()
  const placed = useRef(false)
  useLayoutEffect(() => {
    if (!measured || placed.current) return
    placed.current = true
    const { width, height } = flow.current.getBoundingClientRect()
    const box = getNodesBounds(nodes)
    const fit = Math.min((width - 2 * PAD) / box.width, (height - 2 * PAD) / box.height)
    const zoom = Math.min(1, Math.max(FIRST_ZOOM, fit))
    setViewport({ x: place(width, box.x, box.width, zoom), y: place(height, box.y, box.height, zoom), zoom })
  }, [measured]) // the first view only: later edits never move it

  const onNodesChange = useCallback(
    (changes) => {
      setNodes((ns) => applyNodeChanges(changes, ns))
      if (edits(changes)) touch()
    },
    [touch],
  )
  const onEdgesChange = useCallback(
    (changes) => {
      setEdges((es) => applyEdgeChanges(changes, es))
      if (edits(changes)) touch()
    },
    [touch],
  )
  const onConnect = useCallback(
    ({ source, sourceHandle, target }) => {
      setEdges((es) => addEdge({ id: newId(), source, sourceHandle: sourceHandle ?? null, target }, es))
      touch()
    },
    [touch],
  )

  /** FE13: the new node alone is selected, so the side panel shows it. */
  function add(type, position) {
    setNodes((ns) => [...ns.map((n) => (n.selected ? { ...n, selected: false } : n)), newNode(type, ns, position)])
    touch()
  }

  function addAtCenter(type) {
    const box = flow.current.getBoundingClientRect()
    add(type, screenToFlowPosition({ x: box.left + box.width / 2, y: box.top + box.height / 2 }))
  }

  function dragOver(event) {
    if (!event.dataTransfer.types.includes(DRAG)) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }

  /** FE14: a palette item dropped on the flow lands where it was dropped. */
  function drop(event) {
    const type = event.dataTransfer.getData(DRAG)
    if (!PALETTE.has(type)) return
    event.preventDefault()
    add(type, screenToFlowPosition({ x: event.clientX, y: event.clientY }))
  }

  function edit(id, patch) {
    setNodes((ns) => ns.map((n) => (n.id === id ? { ...n, data: { ...n.data, ...patch } } : n)))
    touch()
  }

  /** FE19, FE21: never rejects (ActionButton); a refusal keeps the graph and the unsaved state. */
  async function save() {
    setError(null)
    const sent = version
    try {
      await saveFactory(factory.id, { graph: stored(nodes, edges) })
      setSaved(sent)
    } catch (err) {
      setError(err)
    }
  }

  // FE20: Ctrl+S and ⌘+S press Save, which is disabled while saved or pending, so then they send nothing
  useEffect(() => {
    function key(event) {
      if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 's') return
      event.preventDefault()
      saveButton.current?.click()
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [])

  // FE22, Q12: leaving the page warns while unsaved; in-app links don't
  useEffect(() => {
    if (!dirty) return
    const warn = (event) => event.preventDefault()
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  return (
    <>
      <header className="mb-4 grid gap-2">
        <Breadcrumbs
          items={[
            ...projectTrail(factory),
            // 101: the list page's sidebar label
            { label: 'Workflows', to: `/projects/${factory.project_id}/factories` },
            { label: factory.name },
          ]}
        />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <h1 className="wrap-anywhere">{factory.name}</h1>
          {/* 101 AC18, Q7: the fixed kind as muted text beside the name, not color alone */}
          <p className={`mr-auto text-sm ${muted}`}>{KIND_LABELS[factory.kind]}</p>
          <p role="status" className={`text-sm ${muted}`}>
            {dirty ? 'Unsaved changes' : ''}
          </p>
          {error && <ErrorMessage error={error} />}
          {/* 103 AC24, Q14: an automation's runs page; leaving with unsaved changes doesn't ask, like the breadcrumb */}
          {factory.kind === 'automation' && (
            <Link to={`/projects/${factory.project_id}/factories/${factory.id}/runs`} className={`${button} hover:no-underline`}>
              Runs
            </Link>
          )}
          {/* 052 FE1: the stored graph's compiled files, before Save */}
          <button type="button" onClick={() => setShowFiles(true)} className={button}>
            Files
          </button>
          <ActionButton ref={saveButton} action={save} disabled={!dirty}>
            Save
          </ActionButton>
        </div>
      </header>
      <div className={`flex flex-col overflow-hidden rounded-lg border border-line md:flex-row ${FRAME}`}>
        <Palette onAdd={addAtCenter} />
        <div ref={flow} className={`min-w-0 md:flex-1 ${FLOW}`}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            defaultEdgeOptions={EDGE_OPTIONS}
            defaultMarkerColor={null}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onDragOver={dragOver}
            onDrop={drop}
            deleteKeyCode={DELETE_KEYS}
            minZoom={0.2}
          >
            <Background />
            <Controls orientation="horizontal" />
          </ReactFlow>
        </div>
        <NodePanel nodes={nodes} onChange={edit} />
      </div>
      {showFiles && <FilesDialog id={factory.id} unsaved={dirty} onClose={() => setShowFiles(false)} />}
    </>
  )
}

/** 046 Q5: the breadcrumb, the title row with Save, and the designer's frame. */
function DesignerSkeleton() {
  return (
    <Skeleton>
      <div className="mb-4 grid gap-2">
        <Crumbs />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <Block className="mr-auto h-8 w-48" />
          <ButtonBlock className="w-16" />
        </div>
      </div>
      <Block className={`rounded-lg ${FLOW} ${FRAME}`} />
    </Skeleton>
  )
}

/** docs/ui.md §8 item 14, Q18: loaded once, never polled, since a poll would overwrite what's being edited. */
function FactoryDesign({ id, fid }) {
  const { data: factory, error } = usePoll(useCallback(() => getFactory(fid), [fid]))
  // Q13: a factory of another project at this URL is not found here
  const ours = factory && String(factory.project_id) === id
  useEffect(() => {
    if (ours) document.title = `${factory.name} · ${factory.project} · Workcell`
  }, [ours, factory])

  if (error?.status === 404) return <NotFound detail={error.message} />
  if (!factory) return error ? <ErrorMessage error={error} /> : <DesignerSkeleton />
  if (!ours) return <NotFound detail={`Factory #${fid} not found`} />
  return (
    <ReactFlowProvider>
      <Designer factory={factory} />
    </ReactFlowProvider>
  )
}

/** Keyed by the URL, so another factory starts from its own graph. */
export function FactoryPage() {
  const { id, fid } = useParams()
  return <FactoryDesign key={`${id}/${fid}`} id={id} fid={fid} />
}
