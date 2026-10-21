import { useEffect, useRef, useState } from 'react'
import { getAuth, logout, planName, sendLoginCode, startLogin } from '../../api/auth.js'
import { ActionButton } from '../../components/ActionButton.jsx'
import { DeleteDialog } from '../../components/DeleteDialog.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { Block, ButtonBlock, Rows, Skeleton } from '../../components/Skeleton.jsx'
import { button, field, muted } from '../../components/styles.js'
import { usePoll } from '../../hooks/usePoll.js'

/** 055 Q5: what Disconnect does, and that outside Docker it is the machine's own claude login too. */
const DISCONNECT_TEXT = (
  <>
    This signs the app out of Claude with <code>claude auth logout</code>. Runs stay disabled until you log in again.
    Outside Docker, this is also your own claude login on this machine.
  </>
)

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
 * loads /api/auth once; a successful code's or Disconnect's response replaces it. Subscription only (MVP §4.3): no API
 * key field. 055: Disconnect, shown only while runs are enabled (Q8), asks in the delete dialog, then posts the logout.
 */
export function SettingsPage() {
  const { data: loaded, error } = usePoll(getAuth) // no interval: once
  const [auth, setAuth] = useState(null) // the code response's body, once there is one
  const [url, setUrl] = useState(null) // the pending login's sign-in URL
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState(null)
  const [loggedIn, setLoggedIn] = useState(false)
  const [asking, setAsking] = useState(false) // the Disconnect dialog is open
  const signedOut = useRef(null) // the logout's body, applied once the dialog has closed so its title doesn't change
  const loginButton = useRef(null)
  const disconnectButton = useRef(null)
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
          <div className="flex flex-wrap gap-2">
            <ActionButton ref={loginButton} action={begin}>
              {label}
            </ActionButton>
            {shown.runs_enabled && (
              // 055: outlined, its danger kept for the dialog's filled confirm
              <button ref={disconnectButton} type="button" onClick={() => setAsking(true)} className={`${button} text-danger`}>
                Disconnect
              </button>
            )}
          </div>
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
          {asking && (
            <DeleteDialog
              title={shown.email ? `Disconnect ${shown.email}?` : 'Disconnect Claude?'}
              text={DISCONNECT_TEXT}
              confirmLabel="Disconnect"
              remove={async () => {
                signedOut.current = await logout()
              }}
              onDeleted={() => {
                setAuth(signedOut.current)
                setUrl(null)
                setLoggedIn(false)
                setFailure(null)
                // Q6: the opener is gone, so focus goes to Log in with Claude; here, as the dialog may have closed already
                loginButton.current?.focus()
              }}
              onClose={(done) => {
                setAsking(false)
                if (!done) disconnectButton.current?.focus()
              }}
            />
          )}
        </section>
      )}
    </>
  )
}
