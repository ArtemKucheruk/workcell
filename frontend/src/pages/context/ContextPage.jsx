import { useCallback, useEffect, useId, useState } from 'react'
import { useParams } from 'react-router'
import {
  contextFromPath,
  contextItems,
  createContextItem,
  deleteContextItem,
  patchContextItem,
  reloadContextItem,
  uploadContextItem,
} from '../../api/context.js'
import { boardPage } from '../../api/pages.js'
import { projectContext } from '../../api/projects.js'
import { PinnedPill } from '../../components/Badge.jsx'
import { DeleteDialog } from '../../components/DeleteDialog.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { Actions, Item } from '../../components/Menu.jsx'
import { NotFound } from '../../components/NotFound.jsx'
import { ProjectHeader } from '../../components/ProjectHeader.jsx'
import { Block, ButtonBlock, ProjectHeaderSkeleton, Skeleton } from '../../components/Skeleton.jsx'
import { button, field, muted } from '../../components/styles.js'
import { usePoll } from '../../hooks/usePoll.js'
import { CardDialog, PINNED, PINNED_TEXT, PinnedDialog } from './CardDialog.jsx'
import { GroupDialog } from './GroupDialog.jsx'

const cards = (n) => `${n} ${n === 1 ? 'card' : 'cards'}`

/** FE9: what Delete removes, and what stays. */
const ITEM_TEXT = 'This removes the card from the app. A file it was read from stays on disk.'
const groupText = (n) => `This removes the group and its ${cards(n)} from the app. Files they were read from stay on disk.`

const PATH_HINT =
  "An absolute path to a .md, .markdown, or .txt file, or a folder of them, on the backend's machine. In Docker, only mounted folders exist."

// the page's grid and the group modal's; `group/row` shows the card's ⋯ as the sidebar's rows do
const GRID = 'grid gap-4 sm:grid-cols-2 xl:grid-cols-3'
const cardLook = 'group/row flex min-w-0 flex-col gap-2 rounded-lg border border-line bg-raised p-4'
// a group is a second sheet offset behind the card, in raised with a line edge: it holds cards
const sheets = 'shadow-[4px_4px_0_-1px_var(--color-raised),4px_4px_0_0_var(--color-line)]'
const titleButton = 'min-w-0 flex-1 cursor-pointer text-left font-medium text-accent wrap-anywhere hover:underline'
const toolbar = 'flex flex-wrap items-start gap-x-6 gap-y-3'

/** The ⋯ a menu item was chosen in, else the clicked element: where focus goes back when its dialog closes. */
function opener(el) {
  const menu = el.closest('[popover]')
  return menu ? document.querySelector(`[popovertarget="${menu.id}"]:not([popovertargetaction])`) : el
}

/** FE2, FE3, Q3: the first card, from the project's context_md; no ⋯, since it can't be moved or deleted. */
function PinnedCard({ onOpen }) {
  return (
    <li className={cardLook}>
      <div className="flex items-start gap-2">
        <button type="button" aria-haspopup="dialog" onClick={onOpen} className={titleButton}>
          {PINNED}
        </button>
        <PinnedPill />
      </div>
      <p className={`text-sm ${muted}`}>{PINNED_TEXT}</p>
    </li>
  )
}

/**
 * FE2, FE7: a card or a group: its title opens it, then its description, and at the foot a group's count and a path's
 * source_path. The ⋯ menu: Edit; Reload from path (path cards); Move to group (Q9: left out with nowhere to go) and Move
 * out of group; and under a divider, Delete. A group's holds Edit and Delete.
 */
function Card({ item, count, groups, on }) {
  const menu = `context-menu-${item.id}`
  const caption = `${menu}-move`
  const group = item.kind === 'group'
  const others = groups.filter((g) => g.id !== item.parent_id)
  return (
    <li className={`${cardLook} ${group ? sheets : ''}`}>
      <div className="flex items-start gap-2">
        <button type="button" aria-haspopup="dialog" onClick={(event) => on.open(item, event)} className={titleButton}>
          {item.title}
        </button>
        <Actions id={menu} label={`Actions for ${item.title}`}>
          <Item menu={menu} onClick={(event) => on.edit(item, event)}>
            Edit
          </Item>
          {!group && (
            <>
              {item.source_path && (
                <Item menu={menu} onClick={() => on.reload(item)}>
                  Reload from path
                </Item>
              )}
              {others.length > 0 && (
                <>
                  <p id={caption} className={`px-2 pt-1 text-xs ${muted}`}>
                    Move to group
                  </p>
                  <div className="grid pl-2">
                    {others.map((g) => (
                      <Item key={g.id} menu={menu} onClick={() => on.move(item, g.id)} aria-describedby={caption} className="truncate">
                        {g.title}
                      </Item>
                    ))}
                  </div>
                </>
              )}
              {item.parent_id != null && (
                <Item menu={menu} onClick={() => on.move(item, null)}>
                  Move out of group
                </Item>
              )}
            </>
          )}
          <hr className="my-1 border-line" />
          <Item menu={menu} onClick={(event) => on.remove(item, event)} className="text-danger">
            Delete
          </Item>
        </Actions>
      </div>
      {item.description && <p className={`line-clamp-3 text-sm ${muted}`}>{item.description}</p>}
      {(group || item.source_path) && (
        <div className="mt-auto grid gap-0.5 text-xs">
          {group && <p className={muted}>{cards(count)}</p>}
          {item.source_path && <p className={`font-mono wrap-anywhere ${muted}`}>{item.source_path}</p>}
        </div>
      )}
    </li>
  )
}

/** FE2, FE11: `shown` in the order received, each group with its count of `all`'s cards; `children` go first. */
function Cards({ shown, all, groups, on, children }) {
  return (
    <ul aria-label="Cards" className={GRID}>
      {children}
      {shown.map((item) => (
        <Card
          key={item.id}
          item={item}
          count={item.kind === 'group' ? all.filter((c) => c.parent_id === item.id).length : 0}
          groups={groups}
          on={on}
        />
      ))}
    </ul>
  )
}

/**
 * FE4, FE5, FE12–FE15: + New card, + New group (the page's only), Upload files, and the Path form, each sending
 * `parentId` inside a group. Uploads go one at a time in the chosen order (Q17), then the items reload once; each
 * refused file is `<name>: <detail>` in `onError`'s alert. A path's refusal shows beside its form, which keeps it.
 */
function AddControls({ projectId, parentId, onNew, onNewGroup, onAdded, onError }) {
  const id = useId()
  const [uploading, setUploading] = useState(false)
  const [path, setPath] = useState('')
  const [adding, setAdding] = useState(false)
  const [refusal, setRefusal] = useState(null)

  async function upload(event) {
    const files = [...event.currentTarget.files]
    event.currentTarget.value = '' // FE14: so the same file can be chosen again
    if (!files.length) return
    onError(null)
    setUploading(true)
    const refused = []
    for (const file of files) {
      try {
        await uploadContextItem(projectId, file, parentId)
      } catch (err) {
        refused.push(`${file.name}: ${err.message}`)
      }
    }
    setUploading(false)
    if (refused.length < files.length) onAdded()
    if (refused.length) onError(new Error(refused.join('; ')))
  }

  async function addPath(event) {
    event.preventDefault()
    setAdding(true)
    setRefusal(null)
    try {
      await contextFromPath(projectId, path.trim(), parentId)
      setPath('')
      onAdded()
    } catch (err) {
      setRefusal(err)
    } finally {
      setAdding(false)
    }
  }

  return (
    <div className={toolbar}>
      <div className="flex flex-wrap gap-2">
        <button type="button" data-new-card aria-haspopup="dialog" onClick={onNew} className={button}>
          + New card
        </button>
        {onNewGroup && (
          <button type="button" aria-haspopup="dialog" onClick={onNewGroup} className={button}>
            + New group
          </button>
        )}
        {/* a native file input, its picker opened by the label, which looks like the buttons beside it */}
        <label
          aria-busy={uploading || undefined}
          className={`${button} has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent ${uploading ? 'pointer-events-none opacity-50' : ''}`}
        >
          Upload files
          <input type="file" multiple accept=".md,.markdown,.txt" disabled={uploading} onChange={upload} className="sr-only" />
        </label>
      </div>
      <form onSubmit={addPath} className="grid min-w-0 flex-1 basis-80 gap-1">
        <div className="flex items-center gap-2">
          <label htmlFor={`${id}-path`}>Path</label>
          <input
            id={`${id}-path`}
            value={path}
            onChange={(event) => setPath(event.target.value)}
            aria-describedby={`${id}-hint`}
            placeholder="/path/to/notes"
            spellCheck={false}
            className={`${field} min-w-0 flex-1 font-mono text-sm`}
          />
          <button disabled={adding || !path.trim()} className={button}>
            Add from path
          </button>
        </div>
        <p id={`${id}-hint`} className={`text-sm ${muted}`}>
          {PATH_HINT}
        </p>
        {refusal && <ErrorMessage error={refusal} />}
      </form>
    </div>
  )
}

/** 046 Q5: the toolbar's buttons and Path form, then a row of cards, in the loaded page's grids. */
function LibrarySkeleton() {
  return (
    <div className="grid gap-6">
      <div className={toolbar}>
        <div className="flex flex-wrap gap-2">
          <ButtonBlock className="w-28" />
          <ButtonBlock className="w-32" />
          <ButtonBlock className="w-30" />
        </div>
        <div className="grid min-w-0 flex-1 basis-80 gap-1">
          <ButtonBlock className="w-full" />
          <Block className="h-5 w-full" />
          <Block className="h-5 w-2/3" />
        </div>
      </div>
      <div className={GRID}>
        {[0, 1, 2].map((i) => (
          <Block key={i} className="h-28" />
        ))}
      </div>
    </div>
  )
}

/**
 * docs/ui.md §8 item 11, 057. The header's board view-model, the pinned context, and the items load once each, never
 * polled; the items load again after each action (`tick`, as the Factories list does).
 */
function ProjectContext({ id }) {
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((n) => n + 1), [])
  const { data: page, error: pageError } = usePoll(useCallback(() => boardPage(id), [id]))
  const { data: loaded, error: contextError } = usePoll(useCallback(() => projectContext(id), [id]))
  const { data: items, error: itemsError } = usePoll(useCallback(() => contextItems(id), [id, tick]))
  const [saved, setSaved] = useState(null) // the pinned card's last PUT reply, newer than `loaded`
  const context = saved ?? loaded
  const [dialog, setDialog] = useState(null) // {kind, item, parentId, opener}
  const [open, setOpen] = useState(null) // the group modal's {id, opener}
  const [alert, setAlert] = useState(null) // FE8, FE10, FE14: the page's refusals
  const [groupAlert, setGroupAlert] = useState(null) // and the group modal's
  const name = page?.project.name
  useEffect(() => {
    if (name) document.title = `${name} · Context · Claude Factories`
  }, [name])

  const missing = [pageError, contextError, itemsError].find((e) => e?.status === 404)
  if (missing) return <NotFound detail={missing.message} />
  if (!page) {
    if (pageError) return <ErrorMessage error={pageError} />
    return (
      <Skeleton>
        <ProjectHeaderSkeleton />
        <LibrarySkeleton />
      </Skeleton>
    )
  }

  const projectId = page.project.id
  const failed = contextError ?? itemsError
  const groups = items?.filter((i) => i.kind === 'group') ?? []
  const count = (group) => items.filter((c) => c.parent_id === group.id).length
  const show = (next, event) => setDialog({ ...next, opener: opener(event.currentTarget) })

  /** Focus goes back to what opened the dialog; after a delete, whose card is going, to its + New card. */
  function closeDialog(gone) {
    const back = dialog.opener
    setDialog(null)
    if (gone) back?.closest('dialog, main')?.querySelector('[data-new-card]')?.focus()
    else back?.focus()
  }

  function closeGroup() {
    open.opener?.focus()
    setOpen(null)
    setGroupAlert(null)
  }

  /** FE8, FE10: a move or a reload; a refusal goes to the alert of where it was sent from. */
  async function act(setError, call) {
    setError(null)
    try {
      await call()
    } catch (err) {
      setError(err)
      return
    }
    reload()
  }

  const handlers = (setError) => ({
    open: (item, event) =>
      item.kind === 'group' ? setOpen({ id: item.id, opener: event.currentTarget }) : show({ kind: 'edit', item }, event),
    edit: (item, event) => show({ kind: 'edit', item }, event),
    remove: (item, event) => show({ kind: 'delete', item }, event),
    reload: (item) => act(setError, () => reloadContextItem(item.id)),
    move: (item, parentId) => act(setError, () => patchContextItem(item.id, { parent_id: parentId })),
  })

  function renderDialog() {
    const { kind, item, parentId } = dialog
    if (kind === 'pinned') {
      return <PinnedDialog projectId={projectId} loaded={context} onSaved={setSaved} onClose={() => closeDialog(false)} />
    }
    if (kind === 'delete') {
      return (
        <DeleteDialog
          title={`Delete ${item.title}?`}
          text={item.kind === 'group' ? groupText(count(item)) : ITEM_TEXT}
          remove={() => deleteContextItem(item.id)}
          onDeleted={reload}
          onClose={closeDialog}
        />
      )
    }
    const group = kind === 'new-group' || item?.kind === 'group'
    const save = item
      ? (fields) => patchContextItem(item.id, fields).then(reload)
      : (fields) =>
          createContextItem(projectId, { kind: group ? 'group' : 'item', ...fields, ...(parentId == null ? {} : { parent_id: parentId }) }).then(
            reload,
          )
    return (
      <CardDialog
        heading={item ? `Edit ${item.title}` : group ? 'New group' : 'New card'}
        item={item}
        group={group}
        maxBytes={context.max_bytes}
        save={save}
        onClose={() => closeDialog(false)}
      />
    )
  }

  const group = open && items?.find((i) => i.id === open.id)
  return (
    <>
      <ProjectHeader project={page.project} factory={page.factory} />
      <div className="grid gap-6">
        {failed && <ErrorMessage error={failed} />}
        {context && items ? (
          <>
            <AddControls
              projectId={projectId}
              onNew={(event) => show({ kind: 'new' }, event)}
              onNewGroup={(event) => show({ kind: 'new-group' }, event)}
              onAdded={reload}
              onError={setAlert}
            />
            {alert && <ErrorMessage error={alert} />}
            <Cards shown={items.filter((i) => i.parent_id == null)} all={items} groups={groups} on={handlers(setAlert)}>
              <PinnedCard onOpen={(event) => show({ kind: 'pinned' }, event)} />
            </Cards>
          </>
        ) : (
          // 046 FE15: the header is in, the context or the items aren't yet
          !failed && (
            <Skeleton>
              <LibrarySkeleton />
            </Skeleton>
          )
        )}
      </div>
      {group && (
        <GroupDialog
          group={group}
          alert={groupAlert}
          onClose={closeGroup}
          controls={
            <AddControls
              projectId={projectId}
              parentId={group.id}
              onNew={(event) => show({ kind: 'new', parentId: group.id }, event)}
              onAdded={reload}
              onError={setGroupAlert}
            />
          }
        >
          {items.some((i) => i.parent_id === group.id) ? (
            <Cards shown={items.filter((i) => i.parent_id === group.id)} all={items} groups={groups} on={handlers(setGroupAlert)} />
          ) : (
            <p className={muted}>No cards in this group yet.</p>
          )}
        </GroupDialog>
      )}
      {dialog && renderDialog()}
    </>
  )
}

/** 033 FE24: keyed by id, so another project's page never shows this one's cards, drafts, or dialogs. */
export function ContextPage() {
  const { id } = useParams()
  return <ProjectContext key={id} id={id} />
}
