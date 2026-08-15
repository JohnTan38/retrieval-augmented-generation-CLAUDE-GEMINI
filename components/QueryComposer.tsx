'use client'

import { FormEvent, useState } from 'react'

export type QueryComposerProps = { disabled: boolean; onSubmit: (question: string) => void }

export function QueryComposer({ disabled, onSubmit }: QueryComposerProps) {
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
        <button type="submit" disabled={submitDisabled}>Find evidence <span aria-hidden="true">→</span></button>
      </div>
      <p>Searches will be grounded in the three SWK501 model-answer sets.</p>
    </form>
  )
}
