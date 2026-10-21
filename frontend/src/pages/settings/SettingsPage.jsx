import { useEffect, useRef, useState } from 'react'
import { activateAccount, deleteAccount, getAccounts, planName, sendLoginCode, startLogin } from '../../api/auth.js'
import { ActionButton } from '../../components/ActionButton.jsx'
import { ActivePill } from '../../components/Badge.jsx'
import { DeleteDialog } from '../../components/DeleteDialog.jsx'
import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { Block, ButtonBlock, Rows, Skeleton } from '../../components/Skeleton.jsx'
import { button, field, muted } from '../../components/styles.js'
import { usePoll } from '../../hooks/usePoll.js'

/** 056 Q11: what Disconnect does; the active account's adds that runs stop with it. */
const disconnectText = (account) => (
  <>
    This signs the account out with <code>claude auth logout</code> and removes it from the app, with its config folder
    if the app created it.{account.active && ' Runs stay disabled until you make another account active.'}
  </>
)

/** FE3: whether runs can start, from the active account; the run's own auth check is what decides (Q14). */
function RunsLine({ accounts }) {
  const active = accounts.find((a) => a.active)
  if (active?.signed_in) return <p>Runs enabled</p>
  return (
    <p className="font-semibold text-danger">
      {active ? 'Not signed in with a Claude subscription — runs disabled' : 'No active account — runs disabled'}
    </p>
  )
}

/**
 * FE1, FE2, Q10, Q11: one account as a card: its email (or that it isn't signed in) and the active pill, its rows, then
 * Make active (inactive only), its login, and Disconnect. `children` is its pending login's form. After Make active,
 * focus goes to this item's login button, which stays mounted as Make active goes.
 */
function AccountItem({ account, loginLabel, onActivate, onLogin, onDisconnect, children }) {
  const login = useRef(null)
  const rows = [
    ['Auth method', account.auth_method ?? '—'],
    ['Plan', account.signed_in ? planName(account.plan) : '—'],
    ['Folder', account.config_dir, `font-mono text-sm wrap-anywhere ${muted}`],
  ]
  return (
    <li className="grid gap-3 rounded-md border border-line px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="m-0 font-semibold wrap-anywhere">{account.email ?? 'Not signed in'}</h3>
        {account.active && <ActivePill />}
      </div>
      <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-6 gap-y-1">
        {rows.map(([name, value, className]) => (
          <div key={name} className="contents">
            <dt className={muted}>{name}</dt>
            <dd className={className}>{value}</dd>
          </div>
        ))}
      </dl>
      <div className="flex flex-wrap gap-2">
        {!account.active && (
          <ActionButton action={async () => (await onActivate()) && login.current?.focus()}>Make active</ActionButton>
        )}
        <ActionButton ref={login} action={onLogin}>
          {loginLabel}
        </ActionButton>
        {/* 055: outlined, its danger kept for the dialog's filled confirm */}
        <button type="button" onClick={onDisconnect} className={`${button} text-danger`}>
          Disconnect
        </button>
      </div>
      {children}
    </li>
  )
}

/**
 * docs/ui.md §8 item 9: the Claude accounts the app holds, the one runs use marked active (056). The page loads
 * /api/auth/accounts once; after a good code, a Make active, or a Disconnect, the shown list is a fresh load. One login
 * is pending at a time (039): its form sits in its account's item, or under + Add account for a new account the list
 * doesn't show yet, and that item's button, or + Add account, reads Start over and resends its account_id (Q3).
 * Subscription only (MVP §4.3): no API key field.
 */
export function SettingsPage() {
  const { data: loaded, error } = usePoll(getAccounts) // no interval: once
  const [list, setList] = useState(null) // the last reload, once there is one
  const [pending, setPending] = useState(null) // the pending login: { accountId, url }
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState(null)
  const [status, setStatus] = useState(null) // FE7: Logged in as …
  const [asking, setAsking] = useState(null) // the Disconnect dialog's { account, opener }
  const addButton = useRef(null)
  useEffect(() => {
    document.title = 'Settings · Claude Factories'
  }, [])
  const shown = list ?? loaded

  /** A fresh list after a code, activate, or delete; a failed one shows in the alert, over the last list. */
  async function reload() {
    try {
      const fresh = await getAccounts()
      setList(fresh)
      return fresh
    } catch (err) {
      setFailure(err)
      return null
    }
  }

  async function begin(accountId) {
    setFailure(null)
    setStatus(null)
    try {
      const started = await startLogin(accountId)
      setPending({ accountId: started.account_id, url: started.url })
      setCode('')
    } catch (err) {
      setPending(null) // the backend stopped the old login before trying this one
      setFailure(err)
    }
  }

  async function submit(event) {
    event.preventDefault()
    const { accountId } = pending
    setBusy(true)
    try {
      await sendLoginCode(code.trim(), accountId)
    } catch (err) {
      setFailure(err) // 039: the form and the typed code stay
      return
    } finally {
      setBusy(false)
    }
    setPending(null)
    setFailure(null)
    const email = (await reload())?.find((a) => a.id === accountId)?.email
    setStatus(email ? `Logged in as ${email}` : 'Logged in')
  }

  /** FE5: true once activated, so the item can move focus; a refusal shows in the alert and nothing reloads. */
  async function activate(id) {
    setFailure(null)
    try {
      await activateAccount(id)
    } catch (err) {
      setFailure(err)
      return false
    }
    setStatus(null) // round 1 review-ui, review-ux: a Logged in as … line would read as the new active account
    await reload()
    return true
  }

  const form = pending && (
    <form onSubmit={submit} className="grid gap-2">
      <p>
        <a href={pending.url} target="_blank" rel="noopener noreferrer">
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
  )
  const adding = pending && !shown?.some((a) => a.id === pending.accountId) // a new account, not listed yet
  return (
    <>
      <h1 className="mb-6">Settings</h1>
      {!shown ? (
        error ? (
          <ErrorMessage error={error} />
        ) : (
          // 046 Q5: under the static h1, the Claude accounts heading, one account card, and + Add account
          <Skeleton>
            <div className="grid max-w-xl gap-4">
              <Block className="h-7 w-44" />
              <div className="grid gap-3 rounded-md border border-line px-4 py-3">
                <Block className="h-6 w-56" />
                <Rows n={3} />
                <ButtonBlock className="w-64" />
              </div>
              <ButtonBlock className="w-36" />
            </div>
          </Skeleton>
        )
      ) : (
        <section aria-labelledby="claude-accounts" className="grid max-w-xl gap-4">
          <h2 id="claude-accounts" className="mt-0 mb-0">
            Claude accounts
          </h2>
          {shown.length ? (
            <ul className="grid gap-3">
              {shown.map((account) => (
                <AccountItem
                  key={account.id}
                  account={account}
                  loginLabel={
                    pending?.accountId === account.id ? 'Start over' : account.signed_in ? 'Log in again' : 'Log in'
                  }
                  onActivate={() => activate(account.id)}
                  onLogin={() => begin(account.id)}
                  onDisconnect={(event) => setAsking({ account, opener: event.currentTarget })}
                >
                  {pending?.accountId === account.id && form}
                </AccountItem>
              ))}
            </ul>
          ) : (
            <p className={muted}>No Claude accounts yet.</p>
          )}
          <RunsLine accounts={shown} />
          {status && (
            <p role="status" className="font-semibold text-success">
              {status}
            </p>
          )}
          <ActionButton
            ref={addButton}
            action={() => begin(adding ? pending.accountId : undefined)}
            className={`${button} justify-self-start`}
          >
            {adding ? 'Start over' : '+ Add account'}
          </ActionButton>
          {adding && form}
          {failure && <ErrorMessage error={failure} />}
          {asking && (
            <DeleteDialog
              title={asking.account.email ? `Disconnect ${asking.account.email}?` : 'Disconnect this account?'}
              text={disconnectText(asking.account)}
              confirmLabel="Disconnect"
              remove={() => deleteAccount(asking.account.id)}
              onDeleted={async () => {
                const { id } = asking.account
                setPending((p) => (p?.accountId === id ? null : p)) // Q12: the backend stopped only this one's login
                setStatus(null)
                setFailure(null)
                await reload()
                addButton.current?.focus() // Q11: the opener is gone
              }}
              onClose={(done) => {
                setAsking(null)
                if (!done) asking.opener.focus()
              }}
            />
          )}
        </section>
      )}
    </>
  )
}
