/** A failed request's message, announced to screen readers. */
export function ErrorMessage({ error }) {
  return (
    <p role="alert" className="font-semibold text-danger">
      {error.message}
    </p>
  )
}
