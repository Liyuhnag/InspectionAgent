import { describe, expect, it } from 'vitest'

import { renderMarkdown } from './renderMarkdown'

describe('renderMarkdown', () => {
  it('把标题和强调渲染成标签', () => {
    const html = renderMarkdown('## 压力\n\n**待复核**')
    expect(html).toContain('<h2>压力</h2>')
    expect(html).toContain('<strong>待复核</strong>')
  })

  it('不执行原文里的 HTML', () => {
    const html = renderMarkdown('<script>alert(1)</script>\n\n[点这里](javascript:alert(1))')
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('href="javascript:')
    expect(html).toContain('&lt;script&gt;')
  })
})
