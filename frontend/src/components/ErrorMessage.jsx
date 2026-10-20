/** A failed request's message, announced to screen readers. */
export function ErrorMessage({ error }) {
  return (
    <p role="alert" className="font-semibold text-danger">
      {error.message}
    </p>
  )
}

/**
 * 046 Q4: a failed 3 s poll over a page that loaded; the next good poll removes it. Polite, and rendered once while
 * failures last, so it's announced once. Fixed at the bottom center of the content column (past the sidebar's w-60 from
 * md up), so the stale page doesn't move, and click-through. It fades in (Q8).
 */
export function OfflineBanner() {
  return (
    <p
      role="status"
      className="pointer-events-none fixed inset-x-0 bottom-4 z-10 mx-auto w-fit rounded-md border border-line bg-raised px-3 py-1.5 text-sm text-muted shadow-sm motion-safe:transition-opacity starting:opacity-0 md:left-60"
    >
      Offline — retrying
    </p>
  )
}
