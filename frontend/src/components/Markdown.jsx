/**
 * 023 Q7, docs/MVP.md §4.5: one of the app's four dangerouslySetInnerHTML; the others insert highlight.js
 * output, which escapes the text: the review diff's code cells (024 Q10), the code page's file viewer
 * (025 Q5), and the factory Files preview (052 FE4). `html` is always a view-model's `*_html`, which markdown-it-py renders with raw HTML off. React
 * skips the write when `html` is unchanged (Q2).
 */
export function Markdown({ html, className = '' }) {
  return <div className={`markdown ${className}`} dangerouslySetInnerHTML={{ __html: html }} />
}
