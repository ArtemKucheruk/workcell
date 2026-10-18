/** A failed request's message, announced to screen readers. */
export function ErrorMessage({ error }) {
  return (
    <p role="alert" className="font-semibold text-red-700 dark:text-red-400">
      {error.message}
    </p>
  )
}
