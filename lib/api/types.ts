export type CorpusDocument = {
  document_id: string
  filename: string
  title: string
  semester: string
  variant: 'research' | 'claude'
  pages: number
  sha256: string
  download_url: string
  topics: string[]
}

export type CorpusResponse = {
  documents: CorpusDocument[]
}

export type SourceEvidence = {
  source_id: string
  document_id: string
  filename: string
  title: string
  semester: string
  variant: 'research' | 'claude'
  page: number
  excerpt: string
  score: number
  download_url: string
}

export type StreamEvent =
  | { type: 'sources'; data: { request_id: string; retrieval_mode: 'hybrid' | 'lexical_degraded'; sources: SourceEvidence[]; timings: { retrieval_ms: number } } }
  | { type: 'token'; data: { delta: string } }
  | { type: 'complete'; data: { request_id: string; timings: { total_ms: number }; cited_source_ids: string[]; citation_valid: boolean; generation_complete: true; refusal?: boolean; message?: string } }
  | { type: 'error'; data: { code: string; message: string; retryable: boolean; retry_after_seconds?: number; partial_text?: string } }

export type WorkspaceState = 'idle' | 'retrieving' | 'streaming' | 'complete' | 'no-evidence' | 'degraded' | 'rate-limited' | 'provider-error' | 'offline' | 'cancelled'
