/** 040: the class strings pages share, on the theme's tokens (index.css). */
export const muted = 'text-muted'

export const button =
  'cursor-pointer rounded-md border border-line px-3 py-1 font-medium hover:bg-raised disabled:cursor-not-allowed disabled:opacity-50'

// Q10: moved unchanged; which padding wins follows Tailwind's CSS order, not this string's
export const smallButton = `${button} px-2 py-0.5 text-sm`

// Q6: one field for every page; the opacity keeps a disabled box looking disabled
export const field = 'rounded-md border border-line bg-surface px-2 py-1 disabled:opacity-50'
