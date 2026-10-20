import { useState } from 'react'
import { useNavigate } from 'react-router'
import { createWorkspace } from '../api/workspaces.js'

/** 041 Q8: the name field of the workspace page's + Workspace and the sidebar's + New workspace. */
export function WorkspaceNameField(props) {
  return (
    <input
      type="text"
      name="name"
      required
      pattern=".*\S.*"
      title="A name that isn't blank"
      aria-label="New workspace name"
      placeholder="New workspace"
      {...props}
    />
  )
}

/**
 * Q9, 041 Q8: the submit both forms share. The API returns the existing workspace's id when the name is
 * taken (§6.1), so either way it opens /workspaces/<id>. `onDone` runs before that navigation.
 */
export function useNewWorkspace(onDone) {
  const navigate = useNavigate()
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(event) {
    event.preventDefault()
    const form = event.currentTarget
    setBusy(true)
    try {
      const { id } = await createWorkspace(new FormData(form).get('name'))
      setError(null)
      form.reset()
      onDone?.()
      navigate(`/workspaces/${id}`)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  return { submit, error, busy }
}
