// @vitest-environment node
// 040: the theme, fonts, heading scale, favicon, and docs, read from the files as Layout.test.jsx's AC19 does.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test } from 'vitest'

const here = (rel) => fileURLToPath(new URL(rel, import.meta.url))
const read = (rel) => fs.readFileSync(here(rel), 'utf8')
const css = read('./index.css')
const NAMES = ['surface', 'raised', 'line', 'fg', 'muted', 'accent', 'success', 'warning', 'danger']

/** The text inside the `{…}` that follows the first `head`, braces matched. */
function block(text, head) {
  const open = text.indexOf('{', text.indexOf(head))
  for (let i = open, depth = 0; i < text.length; i++) {
    if (text[i] === '{') depth++
    else if (text[i] === '}' && --depth === 0) return text.slice(open + 1, i)
  }
  throw new Error(`no block after ${head}`)
}

/** A one-level rule's declarations, by its selector at the start of a line. */
const rule = (text, selector) => text.match(new RegExp(`(?:^|\\n)\\s*${selector}\\s*\\{([^}]*)\\}`))?.[1] ?? ''

/** `--color-<name>: #rrggbb;` in a block, as {name: [values]}. */
function colors(text) {
  const out = {}
  for (const [, name, value] of text.matchAll(/--color-([\w-]+)\s*:\s*([^;]+);/g)) (out[name] ??= []).push(value.trim())
  return out
}

const theme = block(css, '@theme')
const dark = block(css, '@media (prefers-color-scheme: dark)')

test('040 FE1: one @theme block, not inline, defines the nine tokens as #rrggbb', () => {
  expect(css.match(/@theme\b/g)).toHaveLength(1)
  expect(css).not.toMatch(/@theme\s+inline/)
  const found = colors(theme)
  expect(Object.keys(found).sort()).toEqual([...NAMES].sort())
  for (const name of NAMES) expect(found[name]).toEqual([expect.stringMatching(/^#[0-9a-f]{6}$/i)])
})

test('040 FE2: one prefers-color-scheme: dark block sets all nine again, once each, and no dark variant', () => {
  expect(css.match(/@media\s*\(prefers-color-scheme:\s*dark\)/g)).toHaveLength(1)
  const found = colors(dark)
  expect(Object.keys(found).sort()).toEqual([...NAMES].sort())
  for (const name of NAMES) expect(found[name]).toEqual([expect.stringMatching(/^#[0-9a-f]{6}$/i)])
  expect(css).not.toMatch(/@(custom-)?variant\s+dark/)
})

// WCAG 2.x relative luminance and contrast ratio
const luminance = (hex) => {
  const [r, g, b] = [1, 3, 5]
    .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

test('040 FE3: fg, muted, accent, success, and danger reach 4.5:1 on surface and raised, light and dark', () => {
  const ratios = []
  for (const [scheme, t] of [['light', colors(theme)], ['dark', colors(dark)]]) {
    for (const text of ['fg', 'muted', 'accent', 'success', 'danger']) {
      for (const bg of ['surface', 'raised']) {
        ratios.push([`${scheme} ${text} on ${bg}`, contrast(t[text][0], t[bg][0])])
      }
    }
  }
  expect(ratios).toHaveLength(20)
  expect(ratios.filter(([, r]) => !(r >= 4.5))).toEqual([])
})

const base = block(css, '@layer base')

test('040 FE4: body sits on surface and fg, links are accent and keep the hover underline', () => {
  expect(rule(base, 'body')).toMatch(/(^|\s)bg-surface(\s|;)/)
  expect(rule(base, 'body')).toMatch(/(^|\s)text-fg(\s|;)/)
  expect(rule(base, 'a')).toMatch(/(^|\s)text-accent(\s|;)/)
  expect(rule(base, 'a')).toMatch(/(^|\s)hover:underline(\s|;)/)
})

// Every non-test .js, .jsx, and .css under src/, by its path relative to src/
const src = here('.')
const sources = fs
  .readdirSync(src, { recursive: true })
  .filter((f) => /\.(jsx?|css)$/.test(f) && !/\.test\./.test(f) && !f.startsWith(`test${path.sep}`))
  .map((f) => [f.split(path.sep).join('/'), fs.readFileSync(path.join(src, f), 'utf8')])

test('040 FE5: no dark: variant, palette color, -white or -black, or Canvas outside the diff tints', () => {
  const palette = [...read('../node_modules/tailwindcss/theme.css').matchAll(/--color-([a-z]+)-50:/g)].map((m) => m[1])
  expect(palette).toContain('gray')
  const banned = [/\bdark:/g, new RegExp(`\\b(?:${palette.join('|')})-(?:50|[1-9]00|950)\\b`, 'g'), /-(?:white|black)\b/g, /\bCanvas\b/g]
  // Q5: the one exception, GitHub's add and del row tints
  const tints = /^\s*\.diff-table tr\.(?:add|del) \{[^}\n]*\}$/gm
  expect(css.match(tints)).toHaveLength(2)
  const hits = sources.flatMap(([f, text]) => {
    const body = f === 'index.css' ? text.replace(tints, '') : text
    return banned.flatMap((re) => [...body.matchAll(re)].map((m) => `${f}: ${m[0]}`))
  })
  expect(sources.length).toBeGreaterThan(20)
  expect(hits).toEqual([])
})

const pkg = JSON.parse(read('../package.json'))
const fonts = Object.keys(pkg.dependencies).filter((name) => name.startsWith('@fontsource-variable/'))
/** Each font package's category (sans-serif or monospace) and the family its CSS declares. */
const families = Object.fromEntries(
  fonts.map((name) => {
    const dir = `../node_modules/${name}/`
    const family = read(`${dir}index.css`).match(/font-family:\s*'([^']+)'/)[1]
    return [JSON.parse(read(`${dir}metadata.json`)).category, { name, family }]
  }),
)

test('040 FE8: two self-hosted variable fonts, imported in main.jsx, head --font-sans and --font-mono', () => {
  expect(fonts).toHaveLength(2)
  expect(Object.keys(pkg.dependencies).filter((name) => !fonts.includes(name))).toEqual([
    'highlight.js', 'react', 'react-dom', 'react-router',
  ])
  expect(Object.keys(families).sort()).toEqual(['monospace', 'sans-serif'])
  const main = read('./main.jsx')
  for (const [category, token, fallback] of [['sans-serif', 'sans', 'sans-serif'], ['monospace', 'mono', 'monospace']]) {
    const { name, family } = families[category]
    expect(family).toMatch(/ Variable$/)
    // Q4: before index.css, so the theme's rules come after the @font-face ones
    expect(main.indexOf(`import '${name}'\n`)).toBeGreaterThan(-1)
    expect(main.indexOf(`import '${name}'\n`)).toBeLessThan(main.indexOf(`import './index.css'`))
    const stack = theme.match(new RegExp(`--font-${token}\\s*:\\s*([^;]+);`))[1].replace(/\s+/g, ' ')
    expect(stack.startsWith(`'${family}', `)).toBe(true)
    expect(stack.endsWith(fallback) || stack.includes(` ${fallback},`)).toBe(true)
  }
  for (const text of [read('../index.html'), css, main]) expect(text).not.toMatch(/https?:\/\//)
})

const SIZE = /(?<![\w-])text-(xs|sm|base|lg|[2-9]?xl)(\/[\w.]+)?(?![\w-])/
const WEIGHT = /(?<![\w-])font-(thin|extralight|light|normal|medium|semibold|bold|extrabold|black)(?![\w-])/

test('040 FE9: @layer base sets the h1 and h2 scale, and no <h1 carries a size or weight class', () => {
  for (const h of ['h1', 'h2']) {
    const r = rule(base, h)
    expect(r).toMatch(SIZE)
    expect(r).toMatch(WEIGHT)
    expect(r).toMatch(/(?<![\w-])(text-\w+\/[\w.]+|leading-[\w.]+)/) // the line height
  }
  expect(rule(base, 'h2')).toMatch(/(^|\s)mt-8 mb-2(\s)/)
  const jsx = sources.filter(([f]) => f.endsWith('.jsx'))
  const h1s = jsx.flatMap(([f, text]) => [...text.matchAll(/<h1\b[^>]*>/g)].map((m) => [f, m[0]]))
  expect(h1s.length).toBeGreaterThanOrEqual(9) // 042: the board and code h1s became ProjectHeader's one
  expect(h1s.filter(([, tag]) => SIZE.test(tag) || WEIGHT.test(tag))).toEqual([])
  expect(jsx.filter(([, text]) => text.includes('text-2xl font-semibold')).map(([f]) => f)).toEqual([])
})

test('040 FE10: favicon.svg is a plain SVG, and index.html links it', () => {
  const svg = read('../public/favicon.svg').trim()
  expect(svg).toMatch(/^<svg\b[^>]*\bxmlns="http:\/\/www\.w3\.org\/2000\/svg"/)
  expect(svg).toMatch(/^<svg\b[^>]*\bviewBox="[\d.\s-]+"/)
  expect(svg).toMatch(/<\/svg>$/)
  expect(svg).not.toMatch(/<script/i)
  expect(svg).not.toMatch(/href\s*=\s*["'](?!#)/i)
  const head = read('../index.html').match(/<head>([\s\S]*)<\/head>/)[1]
  expect(head).toContain('<link rel="icon" type="image/svg+xml" href="/favicon.svg">')
})

test('040 FE12: docs/ui.md §8 and docs/MVP.md §4.2 name the tokens, fonts, favicon, and packages', () => {
  const ui = read('../../docs/ui.md')
  const intro = ui.slice(ui.indexOf('## 8. UI'), ui.indexOf('\n1. **Dashboard**'))
  for (const name of Object.keys(colors(theme))) expect(intro).toContain(`\`${name}\``)
  expect(intro).toMatch(/light value and a dark value/)
  expect(intro).toMatch(/follow the system/)
  expect(intro).toMatch(/favicon/)
  const mvp = read('../../docs/MVP.md')
  const stack = mvp.slice(mvp.indexOf('### 4.2 Stack'), mvp.indexOf('### 4.3'))
  for (const { name, family } of Object.values(families)) {
    expect(intro).toContain(family.replace(/ Variable$/, ''))
    expect(stack).toContain(name)
  }
  expect(stack).toMatch(/self-hosted/)
  expect(stack).toMatch(/offline/)
  expect(stack).toMatch(/CDN/)
})

test('043 FE6: one label set: StatusLine.jsx is gone, SHORT and SYMBOL live in Chip.jsx, In progress in Badge.jsx, no NEEDS YOU', () => {
  expect(fs.existsSync(here('./components/StatusLine.jsx'))).toBe(false)
  const where = (re) => sources.filter(([, text]) => re.test(text)).map(([f]) => f)
  expect(where(/\b(?:const|let|var)\s+(?:SHORT|SYMBOL)\b/)).toEqual(['components/Chip.jsx'])
  expect(where(/'In progress'/)).toEqual(['components/Badge.jsx'])
  expect(where(/NEEDS YOU/)).toEqual([])
})

test('043 FE16: the pills\' pairs reach 4.5:1, light and dark: warning on surface and raised, surface on warning and danger', () => {
  const ratios = []
  for (const [scheme, t] of [['light', colors(theme)], ['dark', colors(dark)]]) {
    for (const [text, bg] of [['warning', 'surface'], ['warning', 'raised'], ['surface', 'warning'], ['surface', 'danger']]) {
      ratios.push([`${scheme} ${text} on ${bg}`, contrast(t[text][0], t[bg][0])])
    }
  }
  expect(ratios).toHaveLength(8)
  expect(ratios.filter(([, r]) => !(r >= 4.5))).toEqual([])
})

test('043 FE17: docs/ui.md describes the pills and chips, and no old chip format or NEEDS YOU is left', () => {
  const ui = read('../../docs/ui.md')
  const intro = ui.slice(ui.indexOf('## 8. UI'), ui.indexOf('\n1. **Dashboard**'))
  for (const text of ['Backlog', 'In progress', 'Review', 'Done', '● running', 'prefers-reduced-motion', 'waiting on you', 'escalated', 'title', '4.5:1']) {
    expect(intro).toContain(text)
  }
  const board = ui.slice(ui.indexOf('### 8.1'), ui.indexOf('### 8.2'))
  expect(board).toContain('sec ✓')
  expect(board).toContain('code ✗')
  expect(ui.match(/\b(?:sec|ux|ui|co|code)[✓✗·]|\bco [✓✗·]/g)).toBeNull()
  expect(ui).not.toContain('NEEDS YOU')
})

test('044 FE21: docs/ui.md item 3 has the Move menu, its popover, Up, Down, and aria-live; §8.1 draws [Move]', () => {
  const ui = read('../../docs/ui.md')
  const item = ui.slice(ui.indexOf('3. **Project board**'), ui.indexOf('4. **Task detail**'))
  for (const text of ['**Move**', 'popover', 'Up', 'Down', 'aria-live']) expect(item).toContain(text)
  for (const text of ['**Code**', 'Create factory', 'Project context', 'Import']) expect(item).not.toContain(text) // 042
  const board = ui.slice(ui.indexOf('### 8.1'), ui.indexOf('### 8.2'))
  expect(board).toContain('[Move')
  expect(board).not.toContain('[Code]')
})

test('046 FE17: the text Loading… is in one source file, components/Skeleton.jsx', () => {
  expect(sources.filter(([, text]) => text.includes('Loading…')).map(([f]) => f)).toEqual(['components/Skeleton.jsx'])
})

/** Each class-like token in a source as [token, its utility]: the part after the last variant colon outside [ ]. */
const tokens = (text) => (text.match(/[^\s'"`{}()<>;,]+/g) ?? []).map((t) => [t, t.split(/:(?![^[]*\])/).at(-1)])

test('046 FE20: transitions are motion-safe opacity or transform, durations at most 150 ms, animations motion-safe; index.css adds none', () => {
  const found = { transition: [], duration: [], animate: [] }
  const bad = []
  for (const [f, text] of sources) {
    for (const [token, util] of tokens(text)) {
      // `transition` alone is a utility; `duration` and `animate` alone are just words
      const kind = util.match(/^(?:(transition)(?:-|$)|(duration|animate)-)/)?.slice(1).find(Boolean)
      if (!kind) continue
      found[kind].push(token)
      const safe = token.startsWith('motion-safe:')
      const ok = kind === 'transition' ? safe && ['transition-opacity', 'transition-transform'].includes(util)
        : kind === 'duration' ? Number(util.match(/^duration-(\d+)$/)?.[1]) <= 150
        : safe
      if (!ok) bad.push(`${f}: ${token}`)
    }
  }
  expect(bad).toEqual([])
  // the chevron, the card, the popover, and the banner; the running dot, the skeleton blocks, and the spinner
  expect(found.transition.length).toBeGreaterThanOrEqual(4)
  expect(found.animate.length).toBeGreaterThanOrEqual(3)
  expect(css).not.toMatch(/(?:^|[\s;{])(?:transition|animation)(?:-[\w-]+)?\s*:/m)
  for (const [, ms] of css.matchAll(/--default-transition-duration\s*:\s*(\d+)ms/g)) expect(Number(ms)).toBeLessThanOrEqual(150)
})

test('046 FE22: docs/ui.md §8 has skeletons, the offline banner, relative times, the spinner, and the motion rule; §8.1 and §8.2 are relative', () => {
  const ui = read('../../docs/ui.md')
  const intro = ui.slice(ui.indexOf('## 8. UI'), ui.indexOf('\n1. **Dashboard**'))
  for (const text of ['skeleton', 'Offline — retrying', '5m ago', 'yesterday', 'title', 'spinner', 'opacity', 'transform', '150 ms']) {
    expect(intro).toContain(text)
  }
  const board = ui.slice(ui.indexOf('### 8.1'), ui.indexOf('### 8.2'))
  expect(board).toContain('started 5m ago')
  expect(board).not.toContain('started 10:02')
  const review = ui.slice(ui.indexOf('### 8.2'), ui.indexOf('### 8.3'))
  expect(review).toContain('ago')
  expect(review).not.toContain('10:02 created')
})
