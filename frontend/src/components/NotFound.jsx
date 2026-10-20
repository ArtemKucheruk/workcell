import { useEffect } from 'react'
import { Link } from 'react-router'

/** Q10: an unknown route, or the API's 404 with its `detail`. */
export function NotFound({ detail = 'Page not found' }) {
  useEffect(() => {
    document.title = 'Not found · Claude Factories'
  }, [])
  return (
    <section>
      <h1>{detail}</h1>
      <p className="mt-2">
        <Link to="/">Go to the dashboard</Link>
      </p>
    </section>
  )
}
