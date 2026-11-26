import { fireEvent } from '@testing-library/react'

/** 107 Q7: a Select's listbox, opened by a click if it's closed. */
export function openSelect(combobox) {
  if (combobox.getAttribute('aria-expanded') !== 'true') fireEvent.click(combobox)
  return document.getElementById(combobox.getAttribute('aria-controls'))
}

/** Picks the option whose value is `value`, as a click on it would. */
export function pick(combobox, value) {
  const option = openSelect(combobox).querySelector(`[role="option"][data-value="${value}"]`)
  if (!option) throw new Error(`no option with value ${value}`)
  fireEvent.click(option)
}

/** The options' labels, read by opening the list and closing it again with Esc. */
export function optionLabels(combobox) {
  const labels = [...openSelect(combobox).querySelectorAll('[role="option"]')].map((o) => o.textContent)
  fireEvent.keyDown(combobox, { key: 'Escape' })
  return labels
}
