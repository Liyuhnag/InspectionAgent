import MarkdownIt from 'markdown-it'

/** 只解析 Markdown。关闭原文 HTML，避免助手回复执行页面脚本。 */
const markdown = new MarkdownIt({
  html: false,
  linkify: false,
  breaks: true,
})

const renderLink = markdown.renderer.rules.link_open
markdown.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  const href = String(token.attrGet('href') ?? '')
  if (!/^https?:\/\//i.test(href)) {
    token.attrSet('href', '#')
  }
  token.attrSet('rel', 'noopener noreferrer')
  token.attrSet('target', '_blank')
  if (renderLink) {
    return renderLink(tokens, idx, options, env, self)
  }
  return self.renderToken(tokens, idx, options)
}

/** 把助手回复转成可显示的 HTML。 */
export function renderMarkdown(source: string): string {
  return markdown.render(source)
}
