import { useEffect, useState } from 'react'
import { getAuth, planName, sendLoginCode, startLogin } from '../../api/auth.js'
import { ActionButton } from '../../components/ActionButton.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { Block, ButtonBlock, Rows, Skeleton } from '../../components/Skeleton.jsx'
import { button, field, muted } from '../../components/styles.js'
import { usePoll } from '../../hooks/usePoll.js'

/** 039: GET /api/auth's answer as rows; Q3: a login that isn't claude.ai reports no method, plan, or account. */
function LoginRows({ auth }) {
  const rows = [
    ['Auth method', auth.auth_method ?? '—'],
    ['Plan', auth.runs_enabled ? planName(auth.plan) : '—'],
    ['Account', auth.email ?? '—'],
  ]
  return (
    <>
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-1">
        {rows.map(([name, value]) => (
          <div key={name} className="contents">
            <dt className={muted}>{name}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {auth.runs_enabled ? (
        <p className="mt-2">Runs enabled</p>
      ) : (
        <p className="mt-2 font-semibold text-danger">
          Not signed in with a Claude subscription — runs disabled
        </p>
      )}
    </>
  )
}

/**
 * docs/ui.md §8 item 9: the Claude login runs will use, and a claude.ai login done in the browser (039). The page
 * loads /api/auth once; a successful code's response replaces it. Subscription only (MVP §4.3): no API key field.
 */
export function SettingsPage() {
  const { data: loaded, error } = usePoll(getAuth) // no interval: once
  const [auth, setAuth] = useState(null) // the code response's body, once there is one
  const [url, setUrl] = useState(null) // the pending login's sign-in URL
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState(null)
  const [loggedIn, setLoggedIn] = useState(false)
  useEffect(() => {
    document.title = 'Settings · Claude Factories'
  }, [])
  const shown = auth ?? loaded

  async function begin() {
    setFailure(null)
    setLoggedIn(false)
    try {
      setUrl((await startLogin()).url)
      setCode('')
    } catch (err) {
      setUrl(null) // the backend stopped the old login before trying this one
      setFailure(err)
    }
  }

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    try {
      setAuth(await sendLoginCode(code.trim()))
      setUrl(null)
      setFailure(null)
      setLoggedIn(true)
    } catch (err) {
      setFailure(err) // AC23: the form and the typed code stay
    } finally {
      setBusy(false)
    }
  }

  const label = url ? 'Start over' : shown?.runs_enabled ? 'Log in again' : 'Log in with Claude'
  return (
    <>
      <h1 className="mb-6">Settings</h1>
      {!shown ? (
        error ? (
          <ErrorMessage error={error} />
        ) : (
          // 046 Q5: under the static h1, the Claude login heading, its three rows, and the login button
          <Skeleton>
            <div className="grid max-w-xl gap-4">
              <Block className="h-7 w-36" />
              <Rows n={3} />
              <ButtonBlock className="w-44" />
            </div>
          </Skeleton>
        )
      ) : (
        <section aria-labelledby="claude-login" className="grid max-w-xl gap-4">
          <h2 id="claude-login" className="mt-0 mb-0">
            Claude login
          </h2>
          <div>
            <LoginRows auth={shown} />
          </div>
          {loggedIn && (
            <p role="status" className="font-semibold text-success">
              {shown.email ? `Logged in as ${shown.email}` : 'Logged in'}
            </p>
          )}
          <ActionButton action={begin} className={`${button} justify-self-start`}>
            {label}
          </ActionButton>
          {url && (
            <form onSubmit={submit} className="grid gap-2">
              <p>
                <a href={url} target="_blank" rel="noopener noreferrer">
                  Open the Claude sign-in page
                </a>
                <span className={muted}>, sign in, then paste the code it shows.</span>
              </p>
              <label className="grid gap-1">
                Code
                <input
                  type="text"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                  className={`${field} font-mono`}
                />
              </label>
              <button disabled={busy || !code.trim()} className={`${button} justify-self-start`}>
                Submit code
              </button>
            </form>
          )}
          {failure && <ErrorMessage error={failure} />}
        </section>
      )}
    </>
  )
}
