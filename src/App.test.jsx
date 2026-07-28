import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';

const baseStatus = {
  indexed: true,
  total_chunks: 2,
  files: [{ name: 'aac-operations-standard.pdf', pages: 2, size: '10.0 KB' }],
};

const baseQuestions = [
  {
    id: 'q1',
    question: 'What are the eligibility criteria?',
    category: 'Client Management',
    description: 'Checks eligibility rules.',
  },
];

function mockFetch() {
  const calls = [];
  globalThis.fetch = vi.fn(async (url, options = {}) => {
    calls.push({ url: String(url), options });

    if (String(url).startsWith('/api/index-status')) {
      return Response.json(baseStatus);
    }

    if (String(url).startsWith('/api/sample-questions')) {
      return Response.json(baseQuestions);
    }

    if (String(url) === '/api/upload-pdfs') {
      return Response.json({
        indexed: true,
        uploaded_files: [{ name: 'aap.pdf', pages: 1, size: '12.0 KB' }],
        total_uploaded_chunks: 1,
      });
    }

    if (String(url) === '/api/query') {
      return Response.json({
        answer: 'Retrieved uploaded content.',
        context: [{ id: 'aap.pdf_p1', source: 'aap.pdf', page: 1, text: 'AAP content' }],
        queries: ['What is AAP?'],
        api_key_required: true,
      });
    }

    return Response.json({});
  });
  return calls;
}

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

test('uploads a selected PDF and refreshes indexed documents and sample questions', async () => {
  const calls = mockFetch();
  render(<App />);

  const file = new File(['%PDF-1.4'], 'aap.pdf', { type: 'application/pdf' });
  await userEvent.upload(await screen.findByLabelText(/Upload PDF files/i), file);

  await waitFor(() => expect(screen.getByText(/aap.pdf indexed/i)).toBeInTheDocument());

  const uploadCall = calls.find((call) => call.url === '/api/upload-pdfs');
  expect(uploadCall).toBeTruthy();
  expect(uploadCall.options.method).toBe('POST');
  expect(uploadCall.options.body.get('session_id')).toMatch(/^session-/);
  expect(uploadCall.options.body.getAll('files')[0].name).toBe('aap.pdf');

  const statusCalls = calls.filter((call) => call.url.startsWith('/api/index-status'));
  expect(statusCalls.length).toBeGreaterThan(1);
  expect(statusCalls[statusCalls.length - 1].url).toContain('session_id=');
});

test('shows validation error for non-PDF uploads before calling the backend', async () => {
  const calls = mockFetch();
  render(<App />);

  const file = new File(['plain text'], 'notes.txt', { type: 'text/plain' });
  await userEvent.upload(await screen.findByLabelText(/Upload PDF files/i), file, { applyAccept: false });

  expect(await screen.findByText(/Only PDF files can be uploaded/i)).toBeInTheDocument();
  expect(calls.some((call) => call.url === '/api/upload-pdfs')).toBe(false);
});

test('supports drag and drop PDF uploads', async () => {
  const calls = mockFetch();
  render(<App />);

  const dropZone = await screen.findByTestId('pdf-drop-zone');
  const file = new File(['%PDF-1.4'], 'dragged.pdf', { type: 'application/pdf' });

  fireEvent.drop(dropZone, {
    dataTransfer: {
      files: [file],
    },
  });

  await waitFor(() => expect(calls.some((call) => call.url === '/api/upload-pdfs')).toBe(true));
});

test('includes session id when submitting a query', async () => {
  const calls = mockFetch();
  render(<App />);

  await userEvent.type(await screen.findByPlaceholderText(/Ask about indexed or uploaded PDFs/i), 'What is AAP?');
  await userEvent.click(screen.getByTitle('Search knowledgebase'));

  await waitFor(() => expect(calls.some((call) => call.url === '/api/query')).toBe(true));
  const queryCall = calls.find((call) => call.url === '/api/query');
  const body = JSON.parse(queryCall.options.body);
  expect(body.session_id).toMatch(/^session-/);
});
