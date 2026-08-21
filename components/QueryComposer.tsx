'use client'

import { FormEvent, useState } from 'react'

export type QueryComposerProps = {
  disabled: boolean
  onSubmit: (question: string) => void
  busy?: boolean
  onCancel?: () => void
}

export function QueryComposer({ disabled, onSubmit, busy = false, onCancel }: QueryComposerProps) {
  const [question, setQuestion] = useState('')
  const trimmedQuestion = question.trim()
  const submitDisabled = disabled || trimmedQuestion.length === 0

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitDisabled) return
    onSubmit(trimmedQuestion)
  }

  return (
    <form className="query-composer" onSubmit={handleSubmit}>
      <label htmlFor="study-question">What do you want to understand?</label>
      <div className="query-controls">
        <textarea id="study-question" name="study-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about a case, theory, intervention, or life-stage concept…" rows={3} disabled={disabled} />
        <div className="query-actions">
          <button type="submit" disabled={submitDisabled}>{busy ? 'Start new search' : 'Find evidence'} <span aria-hidden="true">→</span></button>
          {busy && onCancel ? <button type="button" className="cancel-query" onClick={onCancel}>Cancel request</button> : null}
        </div>
      </div>
      <p>Searches are grounded in 6 documents · 132 pages across three SWK501 exam sets.</p>
    </form>
  )
}
