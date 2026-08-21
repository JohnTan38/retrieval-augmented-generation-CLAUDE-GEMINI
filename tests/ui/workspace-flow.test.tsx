import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, vi } from 'vitest'
import { StudyWorkspace } from '@/components/StudyWorkspace'

const source = {
  source_id: 'S1',
  document_id: 'jul-2025',
  filename: 'swk501-July2025-deep-research-model-answers.pdf',
  title: 'SWK501 July 2025 Deep-Research Model Answers',
  semester: 'July 2025',
  variant: 'research',
  page: 9,
  excerpt: 'Arnett describes emerging adulthood as a distinct developmental period.',
  score: 0.91,
  download_url: '/documents/swk501-July2025-deep-research-model-answers.pdf',
}

const encoder = new TextEncoder()

function sseResponse(events: Array<[string, object]>) {
  return new Response(events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join(''), {
    headers: { 'content-type': 'text/event-stream' },
  })
}

beforeEach(() => {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
  })
  Element.prototype.scrollIntoView = vi.fn()
})

test('streams source-first evidence, concatenates tokens, and focuses an activated citation', async () => {
  let streamController!: ReadableStreamDefaultController<Uint8Array>
  const fetchMock = vi.fn().mockResolvedValue(new Response(new ReadableStream({
    start(controller) { streamController = controller },
  })))
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await user.type(screen.getByRole('textbox'), '  Explain Arnett  ')
  await user.click(screen.getByRole('button', { name: /find evidence/i }))

  expect(screen.getByTestId('workspace-status')).toHaveTextContent('Retrieving evidence.')
  expect(fetchMock).toHaveBeenCalledWith('/api/query', expect.objectContaining({
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ query: 'Explain Arnett' }),
  }))

  await act(async () => {
    streamController.enqueue(encoder.encode(`event: sources\ndata: ${JSON.stringify({ request_id: 'req-1', retrieval_mode: 'hybrid', sources: [source], timings: { retrieval_ms: 14 } })}\n\n`))
  })
  expect(await screen.findByTestId('source-S1')).toBeVisible()
  expect(screen.queryByText(/Arnett frames/)).not.toBeInTheDocument()

  await act(async () => {
    streamController.enqueue(encoder.encode('event: token\ndata: {"delta":"Arnett frames "}\n\n'))
    streamController.enqueue(encoder.encode('event: token\ndata: {"delta":"this transition [S1]."}\n\n'))
  })
  expect(await screen.findByText(/Arnett frames this transition/)).toBeVisible()
  expect(screen.getByTestId('workspace-status')).toHaveTextContent('Drafting an answer from 1 source.')

  await act(async () => {
    streamController.enqueue(encoder.encode('event: complete\ndata: {"request_id":"req-1","timings":{"total_ms":42},"cited_source_ids":["S1"],"citation_valid":true}\n\n'))
    streamController.close()
  })
  expect(await screen.findByText('Answer complete with 1 source.')).toBeVisible()

  await user.click(screen.getByRole('button', { name: /source s1/i }))
  const evidence = screen.getByTestId('source-S1')
  expect(evidence).toHaveAttribute('data-active', 'true')
  expect(evidence).toHaveFocus()
  expect(within(evidence).getByRole('link', { name: /open exact page/i })).toHaveAttribute(
    'href',
    '/documents/swk501-July2025-deep-research-model-answers.pdf#page=9',
  )
})

test('aborts old work before a guided question starts a new request', async () => {
  const signals: AbortSignal[] = []
  const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
    signals.push(init?.signal as AbortSignal)
    if (signals.length === 1) return Promise.resolve(new Response(new ReadableStream()))
    return Promise.resolve(sseResponse([
      ['sources', { request_id: 'req-2', retrieval_mode: 'hybrid', sources: [source], timings: { retrieval_ms: 8 } }],
      ['token', { delta: 'Guided answer [S1].' }],
      ['complete', { request_id: 'req-2', timings: { total_ms: 20 }, cited_source_ids: ['S1'], citation_valid: true }],
    ]))
  })
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await user.type(screen.getByRole('textbox'), 'First question')
  await user.click(screen.getByRole('button', { name: /find evidence/i }))
  await user.click(screen.getByRole('button', { name: /how does arnett apply/i }))

  expect(signals[0].aborted).toBe(true)
  expect(await screen.findByText(/Guided answer/)).toBeVisible()
  expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({ query: 'How does Arnett apply to the Tan family?' })
})

test('cancels a running request without reporting an offline failure', async () => {
  let requestSignal!: AbortSignal
  vi.stubGlobal('fetch', vi.fn((_url: string, init?: RequestInit) => {
    requestSignal = init?.signal as AbortSignal
    return Promise.resolve(new Response(new ReadableStream()))
  }))
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await user.type(screen.getByRole('textbox'), 'Explain Baltes')
  await user.click(screen.getByRole('button', { name: /find evidence/i }))
  await user.click(screen.getByRole('button', { name: /cancel request/i }))

  expect(requestSignal.aborted).toBe(true)
  expect(await screen.findByText('Request cancelled.')).toBeVisible()
  expect(screen.queryByText(/offline/i)).not.toBeInTheDocument()
})

test('finishes in degraded mode while preserving the grounded answer', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([
    ['sources', { request_id: 'req-3', retrieval_mode: 'lexical_degraded', sources: [source], timings: { retrieval_ms: 9 } }],
    ['token', { delta: 'Lexically grounded answer [S1].' }],
    ['complete', { request_id: 'req-3', timings: { total_ms: 23 }, cited_source_ids: ['S1'], citation_valid: true }],
  ])))
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await user.type(screen.getByRole('textbox'), 'Explain Arnett')
  await user.click(screen.getByRole('button', { name: /find evidence/i }))

  expect(await screen.findByText('Answer complete using lexical evidence.')).toBeVisible()
  expect(screen.getByText(/Lexically grounded answer/)).toBeVisible()
})

test('shows the backend refusal as a no-evidence state', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([
    ['sources', { request_id: 'req-4', retrieval_mode: 'hybrid', sources: [], timings: { retrieval_ms: 7 } }],
    ['complete', { request_id: 'req-4', timings: { total_ms: 8 }, cited_source_ids: [], citation_valid: true, refusal: true, message: 'I do not have enough evidence in the supplied study materials to answer this question.' }],
  ])))
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await user.type(screen.getByRole('textbox'), 'An unrelated question')
  await user.click(screen.getByRole('button', { name: /find evidence/i }))

  expect(await screen.findByText('No supporting evidence was found.')).toBeVisible()
  expect(screen.getByText(/I do not have enough evidence/)).toBeVisible()
  expect(screen.queryByTestId('source-S1')).not.toBeInTheDocument()
})

test('announces degraded retrieval while lexical evidence is still streaming', async () => {
  let streamController!: ReadableStreamDefaultController<Uint8Array>
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new ReadableStream({
    start(controller) { streamController = controller },
  }))))
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await user.type(screen.getByRole('textbox'), 'Explain Arnett')
  await user.click(screen.getByRole('button', { name: /find evidence/i }))
  await act(async () => {
    streamController.enqueue(encoder.encode(`event: sources\ndata: ${JSON.stringify({ request_id: 'req-live-degraded', retrieval_mode: 'lexical_degraded', sources: [source], timings: { retrieval_ms: 5 } })}\n\n`))
  })

  expect(await screen.findByText('Drafting with lexical evidence.')).toBeVisible()

  await act(async () => {
    streamController.enqueue(encoder.encode('event: complete\ndata: {"request_id":"req-live-degraded","cited_source_ids":[],"citation_valid":true,"timings":{"total_ms":9}}\n\n'))
    streamController.close()
  })
})

test('uses plural source copy while streaming and when complete', async () => {
  const secondSource = { ...source, source_id: 'S2', page: 10, score: 0.84 }
  let streamController!: ReadableStreamDefaultController<Uint8Array>
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new ReadableStream({
    start(controller) { streamController = controller },
  }))))
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await user.type(screen.getByRole('textbox'), 'Compare two passages')
  await user.click(screen.getByRole('button', { name: /find evidence/i }))
  await act(async () => {
    streamController.enqueue(encoder.encode(`event: sources\ndata: ${JSON.stringify({ request_id: 'req-plural', retrieval_mode: 'hybrid', sources: [source, secondSource], timings: { retrieval_ms: 6 } })}\n\n`))
    streamController.enqueue(encoder.encode('event: token\ndata: {"delta":"Two passages."}\n\n'))
  })
  expect(await screen.findByText('Drafting an answer from 2 sources.')).toBeVisible()

  await act(async () => {
    streamController.enqueue(encoder.encode('event: complete\ndata: {"request_id":"req-plural","cited_source_ids":[],"citation_valid":true,"timings":{"total_ms":11}}\n\n'))
    streamController.close()
  })
  expect(await screen.findByText('Answer complete with 2 sources.')).toBeVisible()
})

test('aborts a live request when the workspace unmounts', async () => {
  let requestSignal!: AbortSignal
  vi.stubGlobal('fetch', vi.fn((_url: string, init?: RequestInit) => {
    requestSignal = init?.signal as AbortSignal
    return Promise.resolve(new Response(new ReadableStream()))
  }))
  const user = userEvent.setup()
  const { unmount } = render(<StudyWorkspace />)

  await user.type(screen.getByRole('textbox'), 'Explain lifecycle cleanup')
  await user.click(screen.getByRole('button', { name: /find evidence/i }))
  unmount()

  expect(requestSignal.aborted).toBe(true)
})

test('restores focus to the exact activating mobile citation among duplicate markers', async () => {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
  })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([
    ['sources', { request_id: 'req-mobile', retrieval_mode: 'hybrid', sources: [source], timings: { retrieval_ms: 4 } }],
    ['token', { delta: 'First citation [S1], then the invoking citation [S1].' }],
    ['complete', { request_id: 'req-mobile', timings: { total_ms: 8 }, cited_source_ids: ['S1'], citation_valid: true }],
  ])))
  const user = userEvent.setup()
  render(<StudyWorkspace />)

  await user.type(screen.getByRole('textbox'), 'Explain mobile evidence')
  await user.click(screen.getByRole('button', { name: /find evidence/i }))
  const citation = (await screen.findAllByRole('button', { name: /source s1/i }))[1]
  await user.click(citation)
  expect(await screen.findByRole('dialog')).toBeVisible()

  await user.keyboard('{Escape}')

  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: /source s1/i })[1]).toHaveFocus()
})
