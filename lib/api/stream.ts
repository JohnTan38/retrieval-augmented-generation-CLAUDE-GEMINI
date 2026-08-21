import type { StreamEvent } from '@/lib/api/types'

const KNOWN_EVENTS = new Set<StreamEvent['type']>(['sources', 'token', 'complete', 'error'])
const SOURCE_ID = /^S[1-9][0-9]*$/

type JsonObject = Record<string, unknown>
type ParsedBlock = { name: StreamEvent['type']; data: JsonObject }

export class StreamClientError extends Error {
  readonly code: string
  readonly retryable: boolean
  readonly status?: number
  readonly retryAfterSeconds?: number

  constructor(code: string, message: string, options: {
    retryable?: boolean
    status?: number
    retryAfterSeconds?: number
  } = {}) {
    super(message)
    this.name = 'StreamClientError'
    this.code = code
    this.retryable = options.retryable ?? false
    this.status = options.status
    this.retryAfterSeconds = options.retryAfterSeconds
  }
}

function invalidStream(): StreamClientError {
  return new StreamClientError('invalid_stream', 'The answer stream could not be read safely.')
}

function isObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseBlock(block: string): ParsedBlock | undefined {
  const lines = block.split(/\r?\n/)
  const eventName = lines.find((line) => line.startsWith('event:'))?.slice(6).trim()
  if (!eventName || !KNOWN_EVENTS.has(eventName as StreamEvent['type'])) return undefined

  const serialized = lines
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n')
  try {
    const data: unknown = JSON.parse(serialized)
    if (!isObject(data)) throw invalidStream()
    return { name: eventName as StreamEvent['type'], data }
  } catch (error) {
    if (error instanceof StreamClientError) throw error
    throw invalidStream()
  }
}

function optionalString(data: JsonObject, key: string): boolean {
  return data[key] === undefined || typeof data[key] === 'string'
}

function optionalBoolean(data: JsonObject, key: string): boolean {
  return data[key] === undefined || typeof data[key] === 'boolean'
}

function optionalTiming(data: JsonObject, key: string): boolean {
  if (data.timings === undefined) return true
  return isObject(data.timings) && typeof data.timings[key] === 'number'
}

function sourceIds(data: JsonObject): string[] | undefined {
  if (!Array.isArray(data.sources)) return undefined
  const ids = data.sources.map((source) => isObject(source) ? source.source_id : undefined)
  if (ids.some((id) => typeof id !== 'string' || !SOURCE_ID.test(id))) return undefined
  const values = ids as string[]
  return new Set(values).size === values.length ? values : undefined
}

function abortReason(): DOMException {
  return new DOMException('The request was cancelled.', 'AbortError')
}

async function responseError(response: Response): Promise<StreamClientError> {
  let payload: unknown
  try {
    payload = JSON.parse(await response.text())
  } catch {
    payload = undefined
  }
  if (isObject(payload) && typeof payload.code === 'string' && typeof payload.message === 'string') {
    return new StreamClientError(payload.code, payload.message, {
      retryable: typeof payload.retryable === 'boolean' ? payload.retryable : response.status >= 500 || response.status === 429,
      retryAfterSeconds: typeof payload.retry_after_seconds === 'number' ? payload.retry_after_seconds : undefined,
      status: response.status,
    })
  }
  return new StreamClientError('request_failed', 'The study service could not start this request.', {
    retryable: response.status >= 500 || response.status === 429,
    status: response.status,
  })
}

export async function* parseEventStream(
  response: Response,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  if (!response.ok) throw await responseError(response)
  if (!response.body) {
    throw new StreamClientError('missing_stream', 'The study service returned no answer stream.')
  }
  if (signal?.aborted) throw abortReason()

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let sourcesSeen = false
  let terminalSeen = false
  let requestId: string | undefined
  let knownSourceIds = new Set<string>()

  const accept = (block: string): StreamEvent | undefined => {
    const parsed = parseBlock(block)
    if (!parsed) return undefined
    if (terminalSeen) throw invalidStream()
    const { name, data } = parsed

    if (name === 'sources') {
      const ids = sourceIds(data)
      if (sourcesSeen || !ids || !optionalString(data, 'request_id') ||
          (data.retrieval_mode !== undefined && data.retrieval_mode !== 'hybrid' && data.retrieval_mode !== 'lexical_degraded') ||
          !optionalTiming(data, 'retrieval_ms')) throw invalidStream()
      sourcesSeen = true
      requestId = data.request_id as string | undefined
      knownSourceIds = new Set(ids)
    } else if (name === 'token') {
      if (!sourcesSeen || typeof data.delta !== 'string') throw invalidStream()
    } else if (name === 'complete') {
      const citedIds = data.cited_source_ids
      if (!sourcesSeen || !optionalString(data, 'request_id') || !optionalBoolean(data, 'citation_valid') ||
          !optionalBoolean(data, 'generation_complete') || !optionalBoolean(data, 'refusal') || !optionalString(data, 'message') || !optionalTiming(data, 'total_ms') ||
          (requestId !== undefined && data.request_id !== undefined && requestId !== data.request_id) ||
          (citedIds !== undefined && (!Array.isArray(citedIds) || citedIds.some((id) => typeof id !== 'string' || !knownSourceIds.has(id))))) {
        throw invalidStream()
      }
      terminalSeen = true
    } else {
      if (typeof data.code !== 'string' || typeof data.message !== 'string' || typeof data.retryable !== 'boolean' ||
          (data.retry_after_seconds !== undefined && typeof data.retry_after_seconds !== 'number') ||
          (data.partial_text !== undefined && typeof data.partial_text !== 'string')) throw invalidStream()
      terminalSeen = true
    }
    return { type: name, data } as StreamEvent
  }

  const onAbort = () => { void reader.cancel(abortReason()) }
  signal?.addEventListener('abort', onAbort, { once: true })

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (signal?.aborted) throw abortReason()
      buffer += decoder.decode(value, { stream: !done })
      const blocks = buffer.split(/\r?\n\r?\n/)
      buffer = blocks.pop()!
      if (done && buffer.trim()) {
        blocks.push(buffer)
        buffer = ''
      }
      for (const [index, block] of blocks.entries()) {
        const event = accept(block)
        if (event) yield event
        if (terminalSeen) {
          for (const trailingBlock of blocks.slice(index + 1)) accept(trailingBlock)
          await reader.cancel()
          return
        }
      }
      if (done) break
    }
    if (!terminalSeen) throw invalidStream()
  } finally {
    signal?.removeEventListener('abort', onAbort)
    reader.releaseLock()
  }
}
