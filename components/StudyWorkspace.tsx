'use client'

import { useEffect, useRef, useState } from 'react'
import { AnswerSurface } from '@/components/AnswerSurface'
import { CorpusStrip } from '@/components/CorpusStrip'
import { EvidenceRibbon } from '@/components/EvidenceRibbon'
import { QueryComposer } from '@/components/QueryComposer'
import { StatusBanner } from '@/components/StatusBanner'
import { StreamClientError, parseEventStream } from '@/lib/api/stream'
import type { CorpusDocument, SourceEvidence, WorkspaceState } from '@/lib/api/types'
import { sampleQueries } from '@/lib/sample-queries'

type StudyWorkspaceProps = { documents?: CorpusDocument[] }

type Failure = { message: string; retryable: boolean; retryAfterSeconds?: number }

const DOCUMENT_LINK = /^\/documents\/[A-Za-z0-9._-]+\.pdf$/

function isSourceEvidence(value: unknown): value is SourceEvidence {
  const source = value as Record<string, unknown>
  return typeof source.source_id === 'string' && /^S[1-9][0-9]*$/.test(source.source_id) &&
    typeof source.document_id === 'string' && typeof source.filename === 'string' &&
    typeof source.title === 'string' && typeof source.semester === 'string' &&
    typeof source.page === 'number' && Number.isInteger(source.page) && source.page > 0 &&
    typeof source.excerpt === 'string' && source.excerpt.length > 0 &&
    typeof source.score === 'number' && Number.isFinite(source.score) && source.score > 0 &&
    typeof source.download_url === 'string' && DOCUMENT_LINK.test(source.download_url)
}

function hasRetrievalMetadata(data: { request_id: string; retrieval_mode: string; timings: { retrieval_ms: number } }): boolean {
  const timings = data.timings as Record<string, unknown> | undefined
  return typeof data.request_id === 'string' && data.request_id.length > 0 &&
    (data.retrieval_mode === 'hybrid' || data.retrieval_mode === 'lexical_degraded') &&
    typeof timings?.retrieval_ms === 'number' && timings.retrieval_ms >= 0
}

function stateMessage(state: WorkspaceState, sourceCount: number, running: boolean, retryAfterSeconds?: number) {
  if (state === 'idle') return 'Ready for a study question.'
  if (state === 'retrieving') return 'Retrieving evidence.'
  if (state === 'streaming') return `Drafting an answer from ${sourceCount} ${sourceCount === 1 ? 'source' : 'sources'}.`
  if (state === 'complete') return `Answer complete with ${sourceCount} ${sourceCount === 1 ? 'source' : 'sources'}.`
  if (state === 'no-evidence') return 'No supporting evidence was found.'
  if (state === 'degraded') return running ? 'Drafting with lexical evidence.' : 'Answer complete using lexical evidence.'
  if (state === 'rate-limited') return retryAfterSeconds === undefined
    ? 'Rate limit reached. Try again shortly.'
    : `Rate limit reached. Try again in ${retryAfterSeconds} seconds.`
  if (state === 'provider-error') return 'The answer service hit a problem.'
  if (state === 'offline') return 'You appear to be offline. Check your connection and retry.'
  return 'Request cancelled.'
}

function providerFailure(error: unknown): { state: WorkspaceState; failure: Failure } {
  if (error instanceof StreamClientError) {
    const rateLimited = error.status === 429 || error.code === 'rate_limited'
    return {
      state: rateLimited ? 'rate-limited' : 'provider-error',
      failure: { message: error.message, retryable: error.retryable, retryAfterSeconds: error.retryAfterSeconds },
    }
  }
  if (error instanceof TypeError) {
    return { state: 'offline', failure: { message: 'The request could not reach the study service.', retryable: true } }
  }
  return { state: 'provider-error', failure: { message: 'The study service could not complete this request.', retryable: true } }
}

export function StudyWorkspace({ documents = [] }: StudyWorkspaceProps) {
  const pageCount = documents.reduce((total, document) => total + document.pages, 0)
  const [state, setState] = useState<WorkspaceState>('idle')
  const [running, setRunning] = useState(false)
  const [answer, setAnswer] = useState('')
  const [sources, setSources] = useState<SourceEvidence[]>([])
  const [activeSourceId, setActiveSourceId] = useState<string | null>(null)
  const [evidenceActivation, setEvidenceActivation] = useState(0)
  const [citationValid, setCitationValid] = useState(true)
  const [failure, setFailure] = useState<Failure | null>(null)
  const [citationOriginId, setCitationOriginId] = useState<string | null>(null)
  const lastQuery = useRef('')
  const requestSequence = useRef(0)
  const controllerRef = useRef<AbortController | null>(null)

  useEffect(() => () => {
    requestSequence.current += 1
    controllerRef.current?.abort()
  }, [])

  async function runQuery(query: string) {
    controllerRef.current?.abort()
    const requestId = ++requestSequence.current
    const controller = new AbortController()
    controllerRef.current = controller
    lastQuery.current = query
    setState('retrieving')
    setRunning(true)
    setAnswer('')
    setSources([])
    setActiveSourceId(null)
    setEvidenceActivation(0)
    setCitationValid(true)
    setFailure(null)
    setCitationOriginId(null)

    let receivedSources: SourceEvidence[] = []
    let retrievalMode: 'hybrid' | 'lexical_degraded' = 'hybrid'
    try {
      const response = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify({ query }),
        signal: controller.signal,
      })
      for await (const event of parseEventStream(response, controller.signal)) {
        if (event.type === 'sources') {
          if (!hasRetrievalMetadata(event.data) || !event.data.sources.every(isSourceEvidence)) {
            throw new StreamClientError('invalid_stream', 'The answer stream could not be read safely.')
          }
          receivedSources = event.data.sources
          retrievalMode = event.data.retrieval_mode
          setSources(receivedSources)
          if (retrievalMode === 'lexical_degraded') setState('degraded')
        } else if (event.type === 'token') {
          setAnswer((current) => current + event.data.delta)
          setState(retrievalMode === 'lexical_degraded' ? 'degraded' : 'streaming')
        } else if (event.type === 'complete') {
          setCitationValid(event.data.citation_valid ?? true)
          if (event.data.refusal || receivedSources.length === 0) {
            if (event.data.message) setAnswer((current) => current || event.data.message!)
            setState('no-evidence')
          } else {
            setState(retrievalMode === 'lexical_degraded' ? 'degraded' : 'complete')
          }
          setRunning(false)
        } else {
          const rateLimited = event.data.code === 'rate_limited'
          setFailure({ message: event.data.message, retryable: event.data.retryable, retryAfterSeconds: event.data.retry_after_seconds })
          setState(rateLimited ? 'rate-limited' : 'provider-error')
          setRunning(false)
        }
      }
    } catch (error) {
      if (requestSequence.current !== requestId || controller.signal.aborted) return
      const mapped = providerFailure(error)
      setFailure(mapped.failure)
      setState(mapped.state)
      setRunning(false)
    } finally {
      if (requestSequence.current === requestId) controllerRef.current = null
    }
  }

  function cancelRequest() {
    requestSequence.current += 1
    controllerRef.current?.abort()
    controllerRef.current = null
    setRunning(false)
    setState('cancelled')
    setFailure(null)
  }

  const message = stateMessage(state, sources.length, running, failure?.retryAfterSeconds)
  const showAnswer = answer.length > 0 || state === 'retrieving' || state === 'streaming' || state === 'degraded'
  const showFailure = state === 'provider-error' || state === 'rate-limited' || state === 'offline'

  function activateCitation(sourceId: string) {
    setCitationOriginId(sourceId)
    setActiveSourceId(sourceId)
    setEvidenceActivation((current) => current + 1)
  }

  return (
    <main className="study-workspace">
      <header className="desk-nav">
        <div className="desk-identity">
          <p className="eyebrow">SWK501 evidence workspace · Singapore social work</p>
          <h1>SgCare Study Desk</h1>
        </div>
        <StatusBanner documentCount={documents.length} pageCount={pageCount} />
      </header>

      <div className="workspace-intro">
        <p className="eyebrow">Evidence desk</p>
        <h2>Trace your exam reasoning to the page that supports it.</h2>
        <p>A focused reading workspace for working through cases, concepts, and interventions in the SWK501 model answers.</p>
      </div>

      <CorpusStrip documents={documents} />

      <section className="question-section" aria-labelledby="question-heading">
        <div className="question-copy">
          <p className="eyebrow">Start a study thread</p>
          <h2 id="question-heading">Ask once. Follow the evidence.</h2>
        </div>
        <QueryComposer
          disabled={false}
          busy={running}
          onCancel={cancelRequest}
          onSubmit={(query) => { void runQuery(query) }}
        />
        <div className="sample-queries" aria-label="Suggested study questions">
          <p>Try a guided question</p>
          <div>
            {sampleQueries.map((query) => (
              <button
                key={query}
                type="button"
                onClick={() => { void runQuery(query) }}
              >
                {query}
              </button>
            ))}
          </div>
        </div>
      </section>

      {state !== 'idle' ? (
        <section className="result-workspace" aria-label="Study answer and evidence">
          <p className={`workspace-state workspace-state-${state}`} role="status" aria-live="polite" data-testid="workspace-status">{message}</p>
          {showFailure ? (
            <div className="workspace-failure" role="alert">
              <p>{failure?.message}</p>
              {failure?.retryable ? <button type="button" onClick={() => { void runQuery(lastQuery.current) }}>Retry question</button> : null}
            </div>
          ) : null}
          {showAnswer ? (
            <AnswerSurface
              answer={answer}
              citedSourceIds={sources.map((source) => source.source_id)}
              status={state}
              citationValid={citationValid}
              onCitationActivate={activateCitation}
            />
          ) : null}
          <EvidenceRibbon sources={sources} activeSourceId={activeSourceId} onSelect={setActiveSourceId} activationKey={evidenceActivation} restoreFocusSourceId={citationOriginId} />
        </section>
      ) : null}

      <p className="educational-note">For study and exam preparation. Read the cited material before drawing conclusions.</p>
    </main>
  )
}
