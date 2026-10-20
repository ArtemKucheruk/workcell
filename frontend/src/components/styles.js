/** 040: the class strings pages share, on the theme's tokens (index.css). */
export const muted = 'text-muted'

export const button =
  'cursor-pointer rounded-md border border-line px-3 py-1 font-medium hover:bg-raised disabled:cursor-not-allowed disabled:opacity-50'

// Q10: moved unchanged; which padding wins follows Tailwind's CSS order, not this string's
export const smallButton = `${button} px-2 py-0.5 text-sm`

// Q6: one field for every page; the opacity keeps a disabled box looking disabled
export const field = 'rounded-md border border-line bg-surface px-2 py-1 disabled:opacity-50'

// 042: a tab link in a tabs <nav>; the current one (aria-current="page") is underlined and bold
export const tab =
  '-mb-px border-b-2 border-transparent px-2 py-1 text-inherit hover:no-underline aria-[current=page]:border-current aria-[current=page]:font-semibold'

// 044 Q10, moved here by 047 for the Move menu, + New task, Export, and Review changes: below its button where the
// browser has anchor positioning, flipped when it would leave the viewport; else the UA's centered placement, which needs
// m-auto back after preflight's margin reset. 046 Q8: it fades in as it opens, from an opacity-0 starting style; no exit
// fade, which would have to animate display and overlay too
export const popover = [
  'm-auto rounded-md border border-line bg-surface text-fg shadow-lg motion-safe:transition-opacity starting:open:opacity-0',
  'supports-[position-area:bottom]:m-0 supports-[position-area:bottom]:mt-1 [position-try-fallbacks:flip-block,flip-inline]',
].join(' ')
