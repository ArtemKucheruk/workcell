import { popover } from './styles.js'

/**
 * 049 FE3, Q16: hidden by opacity only from md up, so Tab still reaches it; shown while its row (the `group/row`) is
 * hovered or holds focus, while its menu is open, and on touch screens, which can't hover. Below md, the drawer, it shows.
 * 057: moved from the sidebar, which shares it with the Context page's cards.
 */
const actionsButton = [
  'grid size-7 shrink-0 cursor-pointer place-items-center rounded-md text-muted hover:bg-line hover:text-fg motion-safe:transition-opacity',
  'md:opacity-0 md:group-hover/row:opacity-100 md:group-focus-within/row:opacity-100 md:group-has-[:popover-open]/row:opacity-100 md:pointer-coarse:opacity-100',
].join(' ')

// a menu item; buttons inherit the menu's fg, so Delete's text-danger has no color to fight
export const menuItem = 'cursor-pointer rounded px-2 py-1 text-left hover:bg-raised hover:no-underline'

/** 049 FE1, FE2, Q9: `⋯` and its native popover menu, placed under it where the browser has anchor positioning (044 Q10). */
export function Actions({ id, label, ref, children }) {
  return (
    <>
      <button ref={ref} type="button" popoverTarget={id} aria-label={label} style={{ anchorName: `--${id}` }} className={actionsButton}>
        ⋯
      </button>
      <div
        id={id}
        popover="auto"
        style={{ positionAnchor: `--${id}` }}
        className={`${popover} w-48 cursor-default p-1 open:grid [position-area:bottom_span-left]`}
      >
        {children}
      </div>
    </>
  )
}

/** A menu button: it hides its menu natively as it's chosen. */
export function Item({ menu, onClick, className = '', children, ...rest }) {
  return (
    <button type="button" popoverTarget={menu} popoverTargetAction="hide" onClick={onClick} className={`${menuItem} ${className}`} {...rest}>
      {children}
    </button>
  )
}
