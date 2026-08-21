import { forwardRef } from 'react'
import type { SourceEvidence } from '@/lib/api/types'

type SourceCardProps = {
  source: SourceEvidence
  rank: number
  active: boolean
  onSelect: (sourceId: string) => void
}

export const SourceCard = forwardRef<HTMLElement, SourceCardProps>(function SourceCard({ source, rank, active, onSelect }, ref) {
  return (
    <article ref={ref} tabIndex={-1} className="source-card" data-testid={`source-${source.source_id}`} data-active={active ? 'true' : 'false'}>
      <div className="source-card-heading">
        <span className="source-rank" aria-hidden="true">{String(rank).padStart(2, '0')}</span>
        <button type="button" className="source-select" onClick={() => onSelect(source.source_id)} aria-pressed={active}>
          Select evidence {source.source_id}
        </button>
      </div>
      <div className="source-context">
        <p className="semester-label">{source.semester} · page {source.page}</p>
        <span className="variant-badge" data-variant={source.variant}>{source.variant === 'research' ? 'Research source' : 'CLAUDE recall'}</span>
      </div>
      <h3>{source.title}</h3>
      <blockquote>{source.excerpt}</blockquote>
      <div className="source-card-footer">
        <span>{Math.round(source.score * 100)}% match</span>
        <a href={`${source.download_url}#page=${source.page}`}>Open exact page <span aria-hidden="true">↗</span></a>
      </div>
    </article>
  )
})
