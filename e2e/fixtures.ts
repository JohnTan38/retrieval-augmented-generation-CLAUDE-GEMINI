import type { Page, Route } from '@playwright/test'

export type SseFixture = {
  status?: number
  contentType?: string
  body: string
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

export const fixtures = {
  tanArnett: {
    body: [
      event('sources', { request_id: 'e2e-tan-arnett', retrieval_mode: 'hybrid', sources: [source], timings: { retrieval_ms: 8 } }),
      event('token', { delta: 'This evidence-backed response applies Arnett to the Tan family [S1].' }),
      event('complete', { request_id: 'e2e-tan-arnett', cited_source_ids: ['S1'], citation_valid: true, timings: { total_ms: 24 } }),
    ].join(''),
  },
  providerError: {
    status: 503,
    contentType: 'application/json',
    body: JSON.stringify({ code: 'generation_unavailable', message: 'Answer generation is temporarily unavailable.', retryable: true }),
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
