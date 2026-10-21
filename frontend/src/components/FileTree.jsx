import { useId, useState } from 'react'

/** 008 Q6: {"dir/": Map, name: file} in the order given; a directory sits where its first file is. */
function nest(files) {
  const root = new Map()
  for (const file of files) {
    const parts = file.path.split('/')
    let node = root
    for (const dir of parts.slice(0, -1)) {
      if (!node.has(`${dir}/`)) node.set(`${dir}/`, new Map())
      node = node.get(`${dir}/`)
    }
    node.set(parts.at(-1), file)
  }
  return root
}

/** The directories above a path, outermost first: `src/lib/b.py` gives `src/` and `src/lib/`; an empty path none. */
function dirsOf(path) {
  const parts = path.split('/').slice(0, -1)
  return parts.map((_, i) => `${parts.slice(0, i + 1).join('/')}/`)
}

// Preline Tree View's icons, which are Lucide's, on 24×24 strokes; my-0.5 centers a 16px icon on text-sm's 20px line
function Icon({ className, children }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`my-0.5 size-4 shrink-0 ${className}`}
    >
      {children}
    </svg>
  )
}

/**
 * One level of the tree. Q4: a directory is a disclosure button (+/−, folder, name) and the list it controls, which
 * carries `hidden` while closed, so its entries leave the accessibility tree and the Tab order. Q5: Preline's rows and
 * guide line on the tokens; the glyph swaps with no height animation.
 */
function Entries({ node, prefix, tree }) {
  return [...node].map(([name, child]) => {
    if (!(child instanceof Map)) {
      return (
        <li
          key={name}
          className="flex items-start gap-x-2 rounded-md py-0.5 ps-1 pe-2 hover:bg-raised has-[[aria-current=page]]:bg-raised [&>a]:min-w-0 [&>a]:grow"
        >
          <Icon className="text-muted">
            <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
            <path d="M14 2v4a2 2 0 0 0 2 2h4" />
          </Icon>
          {tree.renderFile(child, name)}
        </li>
      )
    }
    const key = prefix + name
    const open = tree.open.has(key)
    const list = `${tree.id}${encodeURIComponent(key)}` // an id with no whitespace, whatever the name holds
    return (
      <li key={name}>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={list}
          onClick={() => tree.toggle(key)}
          className="flex w-full cursor-pointer items-start gap-x-1 rounded-md py-0.5 pe-2 text-start hover:bg-raised"
        >
          <Icon className="mx-1">
            <path d="M5 12h14" />
            {!open && <path d="M12 5v14" />}
          </Icon>
          <Icon className="me-1 text-muted">
            <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />
          </Icon>
          <span className="min-w-0">{name}</span>
        </button>
        {/* the guide line runs under the +/−, whose 24px slot centers it 12px in */}
        <ul
          id={list}
          hidden={!open}
          className="relative ps-6 before:absolute before:inset-y-0 before:start-3 before:-ms-px before:w-0.5 before:bg-line"
        >
          <Entries node={child} prefix={key} tree={tree} />
        </ul>
      </li>
    )
  })
}

/**
 * docs/ui.md §8 items 5 and 6: Preline Tree View's look, with React opening and closing the directories (Q1).
 * Q2: `files` is a flat list of objects with `path`, in display order; `renderFile(file, name)` returns the page's
 * element for one file, getting the object as given. Q3: with `allOpen` every directory starts open; else the ones
 * along `current` do, and each new `current` opens its own while every other directory keeps its state.
 * ponytail: open state is read from `files` once, so in all-open mode a directory first seen on a later load starts
 * closed; key the tree by what changes its files, as the review page's round already does.
 */
export function FileTree({ files, current = '', allOpen = false, renderFile }) {
  const id = useId()
  const [open, setOpen] = useState(() => new Set(allOpen ? files.flatMap((file) => dirsOf(file.path)) : dirsOf(current)))
  // React's "adjust state when a prop changes": in this render, so the new path's directories never paint closed
  const [seen, setSeen] = useState(current)
  if (current !== seen) {
    setSeen(current)
    setOpen((was) => new Set([...was, ...dirsOf(current)]))
  }
  const toggle = (key) =>
    setOpen((was) => {
      const next = new Set(was)
      if (!next.delete(key)) next.add(key)
      return next
    })
  return (
    <ul>
      <Entries node={nest(files)} prefix="" tree={{ id, open, toggle, renderFile }} />
    </ul>
  )
}
