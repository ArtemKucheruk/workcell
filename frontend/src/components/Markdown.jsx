/**
 * 023 Q7, docs/MVP.md §4.5: the app's only dangerouslySetInnerHTML. `html` is always a view-model's `*_html`,
 * which markdown-it-py renders with raw HTML off. React skips the write when `html` is unchanged (Q2).
 */
export function Markdown({ html, className = '' }) {
  return <div className={`markdown ${className}`} dangerouslySetInnerHTML={{ __html: html }} />
}
