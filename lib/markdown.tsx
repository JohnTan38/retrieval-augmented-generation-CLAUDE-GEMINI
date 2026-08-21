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
    const sourceOccurrences = new Map<string, number>()
    const visit = (node: MarkdownNode) => {
      if (!node.children || node.type === 'link') return
      node.children = node.children.flatMap((child) => {
        if (child.type !== 'text' || !child.value) {
          visit(child)
          return [child]
        }
        const parts: MarkdownNode[] = []
        let cursor = 0
        for (const match of child.value.matchAll(/\[(S[1-9][0-9]*(?:\s*,\s*S[1-9][0-9]*)*)\]/g)) {
          const index = match.index!
          if (index > cursor) parts.push({ type: 'text', value: child.value.slice(cursor, index) })
          const groupedSourceIds = match[1].split(/\s*,\s*/)
          if (groupedSourceIds.every((sourceId) => sourceIds.has(sourceId))) {
            groupedSourceIds.forEach((sourceId, groupIndex) => {
              if (groupIndex > 0) parts.push({ type: 'text', value: ' ' })
              const occurrence = sourceOccurrences.get(sourceId) ?? 0
              sourceOccurrences.set(sourceId, occurrence + 1)
              parts.push({ type: 'link', url: `#citation-${sourceId}-${occurrence}`, children: [{ type: 'text', value: `[${sourceId}]` }] })
            })
          } else {
            parts.push({ type: 'text', value: match[0] })
          }
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
  onCitationActivate?: (sourceId: string, citationKey: string) => void
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
          const match = href?.match(/^#citation-(S[1-9][0-9]*)-([0-9]+)$/)
          if (match && validSources.has(match[1])) {
            const citationKey = `${match[1]}-${match[2]}`
            return <button type="button" className="citation-control" data-citation-key={citationKey} aria-label={`Source ${match[1]}`} onClick={() => onCitationActivate?.(match[1], citationKey)}>{linkChildren}</button>
          }
          return <a href={href} {...props}>{linkChildren}</a>
        },
      }}
    >
      {children}
    </ReactMarkdown>
  )
}
