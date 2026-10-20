import { cleanup, render } from '@testing-library/react'
import { afterEach, expect, test } from 'vitest'
import { EscalatedPill, RunningBadge, StatusPill, TaskState, WaitingPill } from './Badge.jsx'
import { Chip } from './Chip.jsx'

afterEach(cleanup)

const one = (el) => render(el).container.firstElementChild
const has = (el, cls) => el.className.split(/\s+/).includes(cls)
const bg = (el) => el.className.split(/\s+/).filter((c) => c.startsWith('bg-'))

test('FE1: each status is a pill with its label and token, and no bg-* class', () => {
  const cases = [
    ['backlog', 'Backlog', 'text-muted'],
    ['in_progress', 'In progress', 'text-accent'],
    ['review', 'Review', 'text-warning'],
    ['done', 'Done', 'text-success'],
  ]
  for (const [status, label, token] of cases) {
    const pill = one(<StatusPill status={status} />)
    expect(pill.textContent).toBe(label)
    expect(has(pill, token)).toBe(true)
    expect(has(pill, 'rounded-full')).toBe(true)
    expect(bg(pill)).toEqual([])
    cleanup()
  }
})

test('FE2: waiting on you is bg-warning text-surface; escalated is bg-danger text-surface', () => {
  const waiting = one(<WaitingPill />)
  expect(waiting.textContent).toBe('waiting on you')
  expect([has(waiting, 'bg-warning'), has(waiting, 'text-surface')]).toEqual([true, true])
  cleanup()
  const escalated = one(<EscalatedPill />)
  expect(escalated.textContent).toBe('escalated')
  expect([has(escalated, 'bg-danger'), has(escalated, 'text-surface')]).toEqual([true, true])
})

test('FE3: the running badge reads ● running in accent; its dot is aria-hidden and pulses only under motion-safe', () => {
  const badge = one(<RunningBadge />)
  expect(badge.textContent).toBe('● running')
  expect(has(badge, 'text-accent')).toBe(true)
  const dot = [...badge.querySelectorAll('*')].find((el) => el.textContent === '●')
  expect(dot.getAttribute('aria-hidden')).toBe('true')
  expect(has(dot, 'motion-safe:animate-pulse')).toBe(true)
  const bare = [badge, ...badge.querySelectorAll('*')].flatMap((el) => el.className.split(/\s+/)).filter((c) => /^animate-/.test(c))
  expect(bare).toEqual([])
})

test('FE4: TaskState is the status pill, then the stage: waiting, escalated, muted text, or nothing', () => {
  const cases = [
    ['human_review', 'waiting on you', 'bg-warning'],
    ['escalated', 'escalated', 'bg-danger'],
    ['build', 'build', 'text-muted'],
  ]
  for (const [stage, text, cls] of cases) {
    const state = one(<TaskState task={{ status: 'review', stage }} />)
    const [pill, after, ...rest] = state.children
    expect(pill.textContent).toBe('Review')
    expect(has(pill, 'text-warning')).toBe(true)
    expect(after.textContent).toBe(text)
    expect(has(after, cls)).toBe(true)
    expect(rest).toEqual([])
    cleanup()
  }
  const bare = one(<TaskState task={{ status: 'backlog', stage: null }} />)
  expect([...bare.children].map((el) => el.textContent)).toEqual(['Backlog'])
  expect(bare.textContent).toBe('Backlog')
})

test('FE5: Chip reads <short> <symbol>, titled <who>: <verdict>, colored by verdict; a posted body keeps the button', () => {
  const cases = [
    ['security', 'PASS', 'sec ✓', 'text-success'],
    ['ux', 'CHANGES', 'ux ✗', 'text-danger'],
    ['ui', 'pending', 'ui ·', 'text-muted'],
    ['code', 'SKIPPED', 'code SKIPPED', 'text-muted'],
  ]
  for (const [who, verdict, text, tone] of cases) {
    const chip = one(<Chip n={1} who={who} verdict={verdict} />)
    expect([chip.tagName, chip.textContent, chip.title]).toEqual(['SPAN', text, `${who}: ${verdict}`])
    expect(has(chip, tone)).toBe(true)
    cleanup()
  }
  const posted = { verdict: 'CHANGES', body_md: 'Trusts X-Forwarded-For', body_html: '<p>Trusts X-Forwarded-For</p>' }
  const button = one(<Chip n={1} who="security" verdict="CHANGES" posted={posted} />)
  expect([button.tagName, button.textContent, button.title]).toEqual(['BUTTON', 'sec ✗', 'security: CHANGES'])
  expect(button.getAttribute('popovertarget')).toBe('verdict-1-security')
  expect(has(button, 'text-danger')).toBe(true)
  cleanup()
  const blank = one(<Chip n={1} who="security" verdict="PASS" posted={{ verdict: 'PASS', body_md: ' \n', body_html: '' }} />)
  expect(blank.tagName).toBe('SPAN')
})
