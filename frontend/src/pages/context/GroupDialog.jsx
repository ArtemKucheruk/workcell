import { ErrorMessage } from '../../components/ErrorMessage.jsx'
import { muted } from '../../components/styles.js'
import { Modal } from './CardDialog.jsx'

/**
 * FE11, FE12: a group's modal: its title as the heading, its description and folder, then the page's add controls
 * (`controls`, sending the group's id), the modal's own alert for refusals sent from here (FE10), and the page's grid
 * of the group's cards (`children`). Esc or Close closes it.
 */
export function GroupDialog({ group, controls, alert, onClose, children }) {
  return (
    <Modal heading={group.title} size="w-6xl" onClose={onClose}>
      {(group.description || group.source_path) && (
        <div className="-mt-2 grid gap-1">
          {group.description && <p className={muted}>{group.description}</p>}
          {group.source_path && <p className={`font-mono text-xs wrap-anywhere ${muted}`}>{group.source_path}</p>}
        </div>
      )}
      {controls}
      {alert && <ErrorMessage error={alert} />}
      {children}
    </Modal>
  )
}
