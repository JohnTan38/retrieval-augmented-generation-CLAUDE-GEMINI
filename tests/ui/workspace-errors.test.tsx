import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, vi } from 'vitest'
import { StudyWorkspace } from '@/components/StudyWorkspace'

const source = {
  source_id: 'S1',
  document_id: 'jul-2025',
  filename: 'swk501-July2025-deep-research-model-answers.pdf',
  title: 'SWK501 July 2025 Deep-Research Model Answers',
  semester: 'July 2025',
  page: 9,
  excerpt: 'Arnett describes emerging adulthood as a distinct developmental period.',
  score: 0.91,
  download_url: '/documents/swk501-July2025-deep-research-model-answers.pdf',
}

function sseResponse(events: Array<[string, object]>) {
  return new Response(events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join(''))
}

async function ask(user: ReturnType<typeof userEvent.setup>, question = 'Explain Arnett') {
  await user.type(screen.getByRole('textbox'), question)
  await user.click(screen.getByRole('button', { name: /find evidence/i }))
}

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
  })
  Element.prototype.scrollIntoView = vi.fn()
})

test('retains sources and partial answer after a provider error, then retries the same query', async () => {
  const failed = sseResponse([
    ['sources', { request_id: 'req-5', retrieval_mode: 'hybrid', sources: [source], timings: { retrieval_ms: 8 } }],
    ['token', { delta: 'A grounded partial answer [S1].' }],
    ['error', { code: 'generation_unavailable', message: 'Answer generation is temporarily unavailable.', retryable: true }],
  ])
  const recovered = sseResponse([
    ['sources', { request_id: 'req-6', retrieval_mode: 'hybrid', sources: [source], timings: { retrieval_ms: 7 } }],
    ['token', { delta: 'A recovered answer [S1].' }],
    ['complete', { request_id: 'req-6', timings: { total_ms: 18 }, cited_source_ids: ['S1'], citation_valid: true }],
  ])
  const fetchMock = vi.fn().mockResolvedValueOnce(failed).mockResolvedValueOnce(recovered)
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await ask(user)

  expect(await screen.findByText('Answer generation is temporarily unavailable.')).toBeVisible()
  expect(screen.getByText(/grounded partial answer/)).toBeVisible()
  expect(screen.getByTestId('source-S1')).toBeVisible()

  await user.click(screen.getByRole('button', { name: /retry question/i }))

  expect(await screen.findByText(/recovered answer/)).toBeVisible()
  expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({ query: 'Explain Arnett' })
})

test('surfaces a rate limit and preserves the server retry delay', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(
    { code: 'rate_limited', message: 'Too many study requests.', retryable: true, retry_after_seconds: 12 },
    { status: 429 },
  )))
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await ask(user)

  expect(await screen.findByText('Rate limit reached. Try again in 12 seconds.')).toBeVisible()
  expect(screen.getByText('Too many study requests.')).toBeVisible()
  expect(screen.getByRole('button', { name: /retry question/i })).toBeVisible()
})

test('distinguishes an offline request failure and offers retry', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch provider.internal')))
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await ask(user)

  expect(await screen.findByText('You appear to be offline. Check your connection and retry.')).toBeVisible()
  expect(screen.queryByText(/provider\.internal/)).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: /retry question/i })).toBeVisible()
})

test('keeps unknown citation markers literal and warns on invalid completion citations', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([
    ['sources', { request_id: 'req-7', retrieval_mode: 'hybrid', sources: [source], timings: { retrieval_ms: 8 } }],
    ['token', { delta: 'Supported [S1]. Unknown [S9].' }],
    ['complete', { request_id: 'req-7', timings: { total_ms: 19 }, cited_source_ids: ['S1'], citation_valid: false }],
  ])))
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await ask(user)

  expect(await screen.findByRole('alert')).toHaveTextContent(/could not verify every citation/i)
  expect(screen.getByRole('button', { name: /source s1/i })).toBeVisible()
  expect(screen.queryByRole('button', { name: /source s9/i })).not.toBeInTheDocument()
  expect(screen.getByText(/Unknown \[S9\]/)).toBeVisible()
})

test('maps a malformed stream to a safe provider error', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([
    ['token', { delta: 'out of order' }],
  ])))
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await ask(user)

  expect(await screen.findByText('The answer stream could not be read safely.')).toBeVisible()
  expect(screen.getByTestId('workspace-status')).toHaveTextContent('The answer service hit a problem.')
})

test('rejects incomplete source records before rendering evidence links', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([
    ['sources', { request_id: 'req-unsafe', retrieval_mode: 'hybrid', sources: [{ source_id: 'S1' }], timings: { retrieval_ms: 3 } }],
    ['complete', { request_id: 'req-unsafe', timings: { total_ms: 5 }, cited_source_ids: [], citation_valid: true }],
  ])))
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await ask(user)

  expect(await screen.findByText('The answer stream could not be read safely.')).toBeVisible()
  expect(screen.queryByTestId('source-S1')).not.toBeInTheDocument()
})

test('shows a no-delay rate-limit message for an SSE error', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([
    ['error', { code: 'rate_limited', message: 'Request capacity reached.', retryable: false }],
  ])))
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await ask(user)

  expect(await screen.findByText('Rate limit reached. Try again shortly.')).toBeVisible()
  expect(screen.queryByRole('button', { name: /retry question/i })).not.toBeInTheDocument()
})

test('uses a safe generic message for an unexpected request failure', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('provider internals')))
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await ask(user)

  expect(await screen.findByText('The study service could not complete this request.')).toBeVisible()
  expect(screen.queryByText(/provider internals/i)).not.toBeInTheDocument()
})

test('accepts completion metadata with an omitted citation validity flag', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([
    ['sources', { request_id: 'req-optional', retrieval_mode: 'hybrid', sources: [source], timings: { retrieval_ms: 4 } }],
    ['token', { delta: 'Answer without citation metadata.' }],
    ['complete', { request_id: 'req-optional', timings: { total_ms: 9 }, cited_source_ids: [] }],
  ])))
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await ask(user)

  expect(await screen.findByText('Answer complete with 1 source.')).toBeVisible()
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

test('rejects full sources that omit required retrieval metadata', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([
    ['sources', { sources: [source] }],
    ['complete', { cited_source_ids: [], citation_valid: true }],
  ])))
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await ask(user)

  expect(await screen.findByText('The answer stream could not be read safely.')).toBeVisible()
  expect(screen.queryByTestId('source-S1')).not.toBeInTheDocument()
})
