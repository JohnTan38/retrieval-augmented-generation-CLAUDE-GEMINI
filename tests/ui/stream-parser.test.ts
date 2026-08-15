import { StreamClientError, parseEventStream } from '@/lib/api/stream'

function responseFromChunks(chunks: string[]) {
  const encoder = new TextEncoder()
  return new Response(new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  }), { headers: { 'content-type': 'text/event-stream' } })
}

async function collect(response: Response, signal?: AbortSignal) {
  const events = []
  for await (const event of parseEventStream(response, signal)) events.push(event)
  return events
}

test('parses events split across arbitrary network chunks', async () => {
  const response = responseFromChunks([
    'event: sources\ndata: {"sources":[{"source_id":"S1"}]}\n',
    '\nevent: token\ndata: {"delta":"Arnett"}\n\n',
    'event: complete\ndata: {"citation_valid":true}\n\n',
  ])

  const events = []
  for await (const event of parseEventStream(response)) events.push(event)

  expect(events.map((event) => event.type)).toEqual(['sources', 'token', 'complete'])
})

test('decodes UTF-8 boundaries and multiline data while ignoring heartbeats and unknown events', async () => {
  const encoder = new TextEncoder()
  const payload = encoder.encode([
    ': keep-alive',
    '',
    'event: telemetry',
    'data: {"secret":"ignored"}',
    '',
    'event: sources',
    'data: {"sources":',
    'data: [{"source_id":"S1"}]}',
    '',
    'event: token',
    'data: {"delta":"Baltes — optimisation"}',
    '',
    'event: complete',
    'data: {"citation_valid":true}',
  ].join('\n'))
  const emDash = payload.indexOf(0xe2)
  const response = new Response(new ReadableStream({
    start(controller) {
      controller.enqueue(payload.slice(0, emDash + 1))
      controller.enqueue(payload.slice(emDash + 1))
      controller.close()
    },
  }))

  const events = await collect(response)

  expect(events.map((event) => event.type)).toEqual(['sources', 'token', 'complete'])
  expect(events[1]).toEqual({ type: 'token', data: { delta: 'Baltes — optimisation' } })
})

test('rejects invalid JSON without exposing response content', async () => {
  const response = responseFromChunks([
    'event: sources\ndata: {"sources":[{"source_id":"S1"}]}\n\n',
    'event: token\ndata: {"provider_secret":oops}\n\n',
  ])

  await expect(collect(response)).rejects.toMatchObject({
    name: 'StreamClientError',
    code: 'invalid_stream',
    message: 'The answer stream could not be read safely.',
  })
})

test.each([
  ['token before sources', ['event: token\ndata: {"delta":"early"}\n\n']],
  ['completion before sources', ['event: complete\ndata: {"citation_valid":true}\n\n']],
  ['invalid token payload', [
    'event: sources\ndata: {"sources":[{"source_id":"S1"}]}\n\n',
    'event: token\ndata: {"delta":7}\n\n',
  ]],
  ['mismatched completion request', [
    'event: sources\ndata: {"request_id":"req-1","sources":[{"source_id":"S1"}]}\n\n',
    'event: complete\ndata: {"request_id":"req-2","citation_valid":true}\n\n',
  ]],
  ['unknown cited source', [
    'event: sources\ndata: {"sources":[{"source_id":"S1"}]}\n\n',
    'event: complete\ndata: {"cited_source_ids":["S2"],"citation_valid":true}\n\n',
  ]],
  ['stream without terminal event', [
    'event: sources\ndata: {"sources":[{"source_id":"S1"}]}\n\n',
    'event: token\ndata: {"delta":"partial"}\n\n',
  ]],
])('rejects %s as an invalid stream contract', async (_label, chunks) => {
  await expect(collect(responseFromChunks(chunks))).rejects.toBeInstanceOf(StreamClientError)
})

test('returns a typed server error for a failed response', async () => {
  const response = Response.json(
    { code: 'rate_limited', message: 'Please wait before trying again.', retryable: true, retry_after_seconds: 12 },
    { status: 429 },
  )

  await expect(collect(response)).rejects.toMatchObject({
    name: 'StreamClientError',
    code: 'rate_limited',
    message: 'Please wait before trying again.',
    retryable: true,
    retryAfterSeconds: 12,
    status: 429,
  })
})

test('uses a safe generic error for malformed failed responses', async () => {
  const response = new Response('<h1>proxy secret</h1>', { status: 502 })

  await expect(collect(response)).rejects.toMatchObject({
    code: 'request_failed',
    message: 'The study service could not start this request.',
    retryable: true,
    status: 502,
  })
})

test('rejects a successful response with no body', async () => {
  await expect(collect(new Response(null))).rejects.toMatchObject({
    code: 'missing_stream',
    message: 'The study service returned no answer stream.',
  })
})

test('cancels a pending reader and throws an AbortError when aborted', async () => {
  let cancelled = false
  const controller = new AbortController()
  const response = new Response(new ReadableStream({
    cancel() { cancelled = true },
  }))
  const pending = collect(response, controller.signal)

  controller.abort()

  await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
  expect(cancelled).toBe(true)
})

test('rejects an already-aborted request before reading the response', async () => {
  const controller = new AbortController()
  controller.abort()

  await expect(collect(responseFromChunks([
    'event: error\ndata: {"code":"stopped","message":"Stopped.","retryable":false}\n\n',
  ]), controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
})

test.each([
  ['non-object event data', ['event: sources\ndata: null\n\n']],
  ['missing sources array', ['event: sources\ndata: {}\n\n']],
  ['non-object source', ['event: sources\ndata: {"sources":[null]}\n\n']],
  ['invalid source identifier', ['event: sources\ndata: {"sources":[{"source_id":"first"}]}\n\n']],
  ['duplicate source identifiers', ['event: sources\ndata: {"sources":[{"source_id":"S1"},{"source_id":"S1"}]}\n\n']],
  ['duplicate sources event', [
    'event: sources\ndata: {"sources":[{"source_id":"S1"}]}\n\n',
    'event: sources\ndata: {"sources":[{"source_id":"S2"}]}\n\n',
  ]],
  ['invalid source request identifier', ['event: sources\ndata: {"request_id":7,"sources":[]}\n\n']],
  ['invalid retrieval mode', ['event: sources\ndata: {"retrieval_mode":"dense","sources":[]}\n\n']],
  ['invalid retrieval timings', ['event: sources\ndata: {"sources":[],"timings":{}}\n\n']],
  ['event after completion', [
    'event: sources\ndata: {"sources":[]}\n\n',
    'event: complete\ndata: {"citation_valid":true}\n\n',
    'event: token\ndata: {"delta":"late"}\n\n',
  ]],
  ['invalid completion citation flag', [
    'event: sources\ndata: {"sources":[]}\n\n',
    'event: complete\ndata: {"citation_valid":"yes"}\n\n',
  ]],
  ['invalid completion refusal flag', [
    'event: sources\ndata: {"sources":[]}\n\n',
    'event: complete\ndata: {"refusal":"yes"}\n\n',
  ]],
  ['invalid completion message', [
    'event: sources\ndata: {"sources":[]}\n\n',
    'event: complete\ndata: {"message":7}\n\n',
  ]],
  ['invalid completion timings', [
    'event: sources\ndata: {"sources":[]}\n\n',
    'event: complete\ndata: {"timings":null}\n\n',
  ]],
  ['invalid cited source list', [
    'event: sources\ndata: {"sources":[]}\n\n',
    'event: complete\ndata: {"cited_source_ids":"S1"}\n\n',
  ]],
  ['invalid cited source value', [
    'event: sources\ndata: {"sources":[{"source_id":"S1"}]}\n\n',
    'event: complete\ndata: {"cited_source_ids":[7]}\n\n',
  ]],
  ['invalid error code', ['event: error\ndata: {"code":7,"message":"Failed.","retryable":true}\n\n']],
  ['invalid error message', ['event: error\ndata: {"code":"failed","message":7,"retryable":true}\n\n']],
  ['invalid error retry flag', ['event: error\ndata: {"code":"failed","message":"Failed.","retryable":"yes"}\n\n']],
  ['invalid error retry delay', ['event: error\ndata: {"code":"failed","message":"Failed.","retryable":true,"retry_after_seconds":"soon"}\n\n']],
])('rejects %s', async (_label, chunks) => {
  await expect(collect(responseFromChunks(chunks))).rejects.toBeInstanceOf(StreamClientError)
})

test('accepts a terminal error event with a numeric retry delay', async () => {
  const events = await collect(responseFromChunks([
    'event: error\ndata: {"code":"rate_limited","message":"Wait.","retryable":true,"retry_after_seconds":4}\n\n',
  ]))

  expect(events).toEqual([{ type: 'error', data: { code: 'rate_limited', message: 'Wait.', retryable: true, retry_after_seconds: 4 } }])
})

test.each([
  [503, { code: 'unavailable', message: 'Unavailable.' }, true],
  [429, { code: 'busy', message: 'Busy.' }, true],
  [400, { code: 'bad', message: 'Bad request.' }, false],
])('derives retryability for HTTP %s errors without retry metadata', async (status, payload, retryable) => {
  await expect(collect(Response.json(payload, { status }))).rejects.toMatchObject({ retryable, retryAfterSeconds: undefined })
})

test('does not retry a malformed client-error response', async () => {
  await expect(collect(new Response('bad', { status: 400 }))).rejects.toMatchObject({ retryable: false })
})

test('treats a malformed 429 response as retryable', async () => {
  await expect(collect(new Response('bad', { status: 429 }))).rejects.toMatchObject({ retryable: true })
})
