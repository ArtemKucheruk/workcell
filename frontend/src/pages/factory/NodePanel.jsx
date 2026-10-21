import { useId, useState } from 'react'
import { field, muted } from '../../components/styles.js'
import { Icon, isAgent, KINDS, tint } from './graph.jsx'

const MODELS = ['inherit', 'opus', 'sonnet', 'haiku']
const CHOICES = { side: ['backend', 'frontend', 'both'], focus: ['security', 'ux', 'ui', 'code', 'custom'] }
const SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/

const label = 'grid gap-1 text-sm font-medium'
const input = `${field} w-full text-sm font-normal`

function Choice({ name, value, options, onChange }) {
  return (
    <label className={label}>
      {name}
      <select value={value} onChange={(event) => onChange(event.target.value)} className={input}>
        {options.map((option) => (
          <option key={option}>{option}</option>
        ))}
      </select>
    </label>
  )
}

/**
 * FE16, FE17: one node's data, written to the node at each keystroke through `set(patch)`. Tools and N keep their text
 * as typed, while the node gets the parsed value: Tools split on commas and trimmed, N a number (null when empty,
 * which Save's 422 then names). Keyed by node id, so another node starts from its own data.
 */
function Fields({ node, set }) {
  const { type, data } = node
  const id = useId()
  const [tools, setTools] = useState(() => (data.tools ?? []).join(', '))
  const [n, setN] = useState(() => String(data.n ?? ''))
  const { about, extra } = KINDS[type]

  if (!isAgent(type)) {
    return (
      <>
        <p>{about}</p>
        {type === 'rounds_below' && (
          <label className={label}>
            N
            <input
              type="number"
              min="1"
              step="1"
              value={n}
              onChange={(event) => {
                setN(event.target.value)
                set({ n: event.target.value === '' ? null : Number(event.target.value) })
              }}
              className={`${input} tabular-nums`}
            />
          </label>
        )}
      </>
    )
  }
  const slug = SLUG.test(data.name)
  return (
    <>
      <div className="grid gap-1">
        <label htmlFor={`${id}-name`} className={label}>
          Name
        </label>
        <input
          id={`${id}-name`}
          type="text"
          value={data.name}
          aria-describedby={`${id}-hint`}
          aria-invalid={!slug || undefined}
          onChange={(event) => set({ name: event.target.value })}
          className={`${input} font-mono`}
        />
        <p id={`${id}-hint`} className={`text-xs ${slug ? muted : 'text-danger'}`}>
          a-z, 0-9, and -
        </p>
      </div>
      <label className={label}>
        Description
        <input type="text" value={data.description} onChange={(event) => set({ description: event.target.value })} className={input} />
      </label>
      <Choice name="Model" value={data.model} options={MODELS} onChange={(model) => set({ model })} />
      {extra && (
        <Choice
          name={extra === 'side' ? 'Side' : 'Focus'}
          value={data[extra]}
          options={CHOICES[extra]}
          onChange={(value) => set({ [extra]: value })}
        />
      )}
      <div className="grid gap-1">
        <label htmlFor={`${id}-tools`} className={label}>
          Tools
        </label>
        <input
          id={`${id}-tools`}
          type="text"
          value={tools}
          placeholder="Read, Edit, Bash"
          aria-describedby={`${id}-tools-hint`}
          onChange={(event) => {
            setTools(event.target.value)
            set({ tools: event.target.value.split(',').map((t) => t.trim()).filter(Boolean) })
          }}
          className={input}
        />
        <p id={`${id}-tools-hint`} className={`text-xs ${muted}`}>
          comma-separated
        </p>
      </div>
      <label className={`${label} min-h-0`}>
        Prompt
        <textarea
          value={data.prompt}
          rows={14}
          onChange={(event) => set({ prompt: event.target.value })}
          className={`${field} w-full resize-y font-mono text-xs/5 font-normal`}
        />
      </label>
    </>
  )
}

/** FE16: the side panel: the one selected node's fields, else a hint. `onChange(id, patch)` merges into its data. */
export function NodePanel({ nodes, onChange }) {
  const picked = nodes.filter((n) => n.selected)
  const node = picked.length === 1 ? picked[0] : null
  return (
    <section
      aria-labelledby="node-panel"
      className="grid shrink-0 content-start gap-3 border-t border-line p-4 md:w-80 md:overflow-y-auto md:border-t-0 md:border-l"
    >
      <h2 id="node-panel" className="m-0 text-base/6">
        Node
      </h2>
      {node ? (
        <>
          <p className={`flex items-center gap-2 text-sm ${muted}`}>
            <Icon type={node.type} className={tint(node.type)} />
            {node.type === 'start' ? 'Start' : `${isAgent(node.type) ? 'Agent' : 'Condition'} · ${KINDS[node.type].label}`}
          </p>
          <Fields key={node.id} node={node} set={(patch) => onChange(node.id, patch)} />
        </>
      ) : (
        <p className={muted}>Select a node to edit it.</p>
      )}
    </section>
  )
}
