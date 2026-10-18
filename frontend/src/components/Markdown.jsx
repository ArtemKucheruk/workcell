/**
 * 023 Q7, docs/MVP.md §4.5: one of the app's two dangerouslySetInnerHTML; the other is the review diff's code
 * cells, which insert highlight.js output (024 Q10). `html` is always a view-model's `*_html`, which
 * markdown-it-py renders with raw HTML off. React skips the write when `html` is unchanged (Q2).
 */
export function Markdown({ html, className = '' }) {
  return <div className={`markdown ${className}`} dangerouslySetInnerHTML={{ __html: html }} />
}
