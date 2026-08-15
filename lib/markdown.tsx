'use client'

import type { ComponentPropsWithoutRef } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'

type MarkdownNode = {
  type: string
  value?: string
  url?: string
  children?: MarkdownNode[]
}

const SANITIZE_SCHEMA = {
  tagNames: ['a', 'blockquote', 'br', 'code', 'del', 'em', 'h2', 'h3', 'h4', 'hr', 'li', 'ol', 'p', 'pre', 'strong', 'table', 'tbody', 'td', 'th', 'thead', 'tr', 'ul'],
  attributes: {
    a: ['href', 'title'],
    code: ['className'],
    ol: ['start'],
    td: ['align'],
    th: ['align'],
  },
  protocols: { href: ['http', 'https', 'mailto'] },
}

function citationPlugin(sourceIds: Set<string>) {
  return () => (tree: MarkdownNode) => {
    const visit = (node: MarkdownNode) => {
      if (!node.children || node.type === 'link') return
      node.children = node.children.flatMap((child) => {
        if (child.type !== 'text' || !child.value) {
          visit(child)
          return [child]
        }
        const parts: MarkdownNode[] = []
        let cursor = 0
        for (const match of child.value.matchAll(/\[(S[1-9][0-9]*)\]/g)) {
          const index = match.index!
          if (index > cursor) parts.push({ type: 'text', value: child.value.slice(cursor, index) })
          const sourceId = match[1]
          parts.push(sourceIds.has(sourceId)
            ? { type: 'link', url: `#source-${sourceId}`, children: [{ type: 'text', value: match[0] }] }
            : { type: 'text', value: match[0] })
          cursor = index + match[0].length
        }
        if (cursor === 0) return [child]
        if (cursor < child.value.length) parts.push({ type: 'text', value: child.value.slice(cursor) })
        return parts
      })
    }
    visit(tree)
  }
}

type SafeMarkdownProps = {
  children: string
  sourceIds: string[]
  onCitationActivate?: (sourceId: string) => void
}

export function SafeMarkdown({ children, sourceIds, onCitationActivate }: SafeMarkdownProps) {
  const validSources = new Set(sourceIds)
  return (
    <ReactMarkdown
      skipHtml
      remarkPlugins={[remarkGfm, citationPlugin(validSources)]}
      rehypePlugins={[[rehypeSanitize, SANITIZE_SCHEMA]]}
      components={{
        a: ({ href, children: linkChildren, ...props }: ComponentPropsWithoutRef<'a'>) => {
          const match = href?.match(/^#source-(S[1-9][0-9]*)$/)
          if (match && validSources.has(match[1])) {
            return <button type="button" className="citation-control" data-citation-source={match[1]} aria-label={`Source ${match[1]}`} onClick={() => onCitationActivate?.(match[1])}>{linkChildren}</button>
          }
          return <a href={href} {...props}>{linkChildren}</a>
        },
      }}
    >
      {children}
    </ReactMarkdown>
  )
}
