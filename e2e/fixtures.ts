import type { Page, Route } from '@playwright/test'

export type SseFixture = {
  status?: number
  contentType?: string
  body: string
  chunks?: readonly [string, string, string]
}

const source = {
  source_id: 'S1',
  document_id: 'jul-2025',
  filename: 'swk501-July2025-deep-research-model-answers.pdf',
  title: 'SWK501 July 2025 Deep-Research Model Answers',
  semester: 'July 2025',
  page: 9,
  excerpt: 'Arnett describes emerging adulthood as a distinct developmental period of exploration.',
  score: 0.91,
  download_url: '/documents/swk501-July2025-deep-research-model-answers.pdf',
}

function event(name: string, data: object) {
  return `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`
}

const tanArnettChunks = [
  event('sources', { request_id: 'e2e-tan-arnett', retrieval_mode: 'hybrid', sources: [source], timings: { retrieval_ms: 8 } }),
  event('token', { delta: 'This evidence-backed response applies Arnett to the Tan family [S1].' }),
  event('complete', { request_id: 'e2e-tan-arnett', cited_source_ids: ['S1'], citation_valid: true, timings: { total_ms: 24 } }),
] as const

export const fixtures = {
  tanArnett: {
    chunks: tanArnettChunks,
    body: tanArnettChunks.join(''),
  },
  providerError: {
    status: 503,
    contentType: 'application/json',
    body: JSON.stringify({ code: 'generation_unavailable', message: 'Answer generation is temporarily unavailable.', retryable: true }),
  },
  rateLimited: {
    status: 429,
    contentType: 'application/json',
    body: JSON.stringify({ code: 'rate_limited', message: 'Too many study requests.', retryable: true, retry_after_seconds: 12 }),
  },
  providerStreamError: {
    body: [
      event('sources', { request_id: 'e2e-provider-error', retrieval_mode: 'hybrid', sources: [source], timings: { retrieval_ms: 8 } }),
      event('token', { delta: 'Partial evidence-backed response [S1].' }),
      event('error', { code: 'generation_unavailable', message: 'Answer generation is temporarily unavailable.', retryable: true }),
    ].join(''),
  },
} satisfies Record<string, SseFixture>

export async function fulfillSse(route: Route, fixture: SseFixture) {
  await route.fulfill({
    status: fixture.status ?? 200,
    contentType: fixture.contentType ?? 'text/event-stream',
    headers: fixture.status ? undefined : { 'cache-control': 'no-cache' },
    body: fixture.body,
  })
}

export async function installMockSse(page: Page, fixture: SseFixture) {
  await page.route('**/api/query', (route) => fulfillSse(route, fixture))
}

export async function installMockSequence(page: Page, sequence: readonly [SseFixture, ...SseFixture[]]) {
  let requestIndex = 0
  await page.route('**/api/query', (route) => {
    const fixture = sequence[Math.min(requestIndex, sequence.length - 1)]
    requestIndex += 1
    return fulfillSse(route, fixture)
  })
}

type ChunkedStreamController = {
  releaseSources: () => Promise<void>
  releaseToken: () => Promise<void>
  releaseComplete: () => Promise<void>
}

type BrowserStreamHarness = {
  controller?: ReadableStreamDefaultController<Uint8Array>
  chunks: readonly string[]
}

export async function installChunkedSse(page: Page, fixture: SseFixture): Promise<ChunkedStreamController> {
  if (!fixture.chunks) throw new Error('A chunked SSE fixture requires exactly three chunks.')

  await page.addInitScript((chunks: readonly string[]) => {
    const originalFetch = window.fetch.bind(window)
    const harness: BrowserStreamHarness = { chunks }
    const harnessWindow = window as typeof window & { __sgcareStreamHarness?: BrowserStreamHarness }
    harnessWindow.__sgcareStreamHarness = harness

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const requestUrl = input instanceof Request ? input.url : input.toString()
      if (new URL(requestUrl, window.location.href).pathname !== '/api/query') {
        return originalFetch(input, init)
      }
      return new Response(new ReadableStream<Uint8Array>({
        start(controller) { harness.controller = controller },
      }), {
        status: 200,
        headers: { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' },
      })
    }
  }, fixture.chunks)

  const release = async (index: number) => {
    await page.waitForFunction(() => {
      const harnessWindow = window as typeof window & { __sgcareStreamHarness?: BrowserStreamHarness }
      return Boolean(harnessWindow.__sgcareStreamHarness?.controller)
    })
    await page.evaluate((chunkIndex: number) => {
      const harnessWindow = window as typeof window & { __sgcareStreamHarness?: BrowserStreamHarness }
      const harness = harnessWindow.__sgcareStreamHarness
      if (!harness?.controller) throw new Error('The browser SSE stream has not started.')
      harness.controller.enqueue(new TextEncoder().encode(harness.chunks[chunkIndex]))
    }, index)
  }

  return {
    releaseSources: () => release(0),
    releaseToken: () => release(1),
    releaseComplete: () => release(2),
  }
}
