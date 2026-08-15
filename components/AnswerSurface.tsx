'use client'

import { SafeMarkdown } from '@/lib/markdown'
import type { WorkspaceState } from '@/lib/api/types'

export type AnswerSurfaceProps = {
  answer: string
  citedSourceIds: string[]
  status: WorkspaceState
  citationValid?: boolean
  onCitationActivate?: (sourceId: string) => void
}

export function AnswerSurface({ answer, citedSourceIds, status, citationValid = true, onCitationActivate }: AnswerSurfaceProps) {
  const waiting = status === 'retrieving' && answer.length === 0
  return (
    <section className="answer-surface" aria-labelledby="answer-heading" aria-busy={status === 'retrieving' || status === 'streaming'}>
      <div className="answer-heading-row">
        <div>
          <p className="eyebrow">Answer thread</p>
          <h2 id="answer-heading">Reasoning, connected to evidence</h2>
        </div>
        <span className={`answer-state answer-state-${status}`}>{status.replace('-', ' ')}</span>
      </div>
      <div className="answer-copy">
        {waiting ? <p className="answer-placeholder">Retrieving the strongest passages…</p> : null}
        {answer ? <SafeMarkdown sourceIds={citedSourceIds} onCitationActivate={onCitationActivate}>{answer}</SafeMarkdown> : null}
        {status === 'streaming' ? <span className="stream-caret" aria-hidden="true" /> : null}
      </div>
      {!citationValid && (status === 'complete' || status === 'degraded') ? (
        <p className="citation-warning" role="alert">We could not verify every citation in this answer. Use only the linked source markers below.</p>
      ) : null}
    </section>
  )
}
