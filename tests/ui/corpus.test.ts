import { loadPublicCorpus } from '@/lib/corpus'

test('loads the fixed paired SWK501 corpus with all 132 pages', () => {
  const documents = loadPublicCorpus()

  expect(documents.map((document) => ({
    document_id: document.document_id,
    semester: document.semester,
    variant: document.variant,
    pages: document.pages,
    download_url: document.download_url,
  }))).toEqual([
    {
      document_id: 'jan-2025',
      semester: 'January 2025',
      variant: 'research',
      pages: 26,
      download_url: '/documents/swk501-Jan2025-evidence-based-model-answers.pdf',
    },
    {
      document_id: 'jan-2025-claude', semester: 'January 2025', variant: 'claude', pages: 15,
      download_url: '/documents/swk501-Jan2025-CLAUDE-model-answers.pdf',
    },
    {
      document_id: 'jul-2025',
      semester: 'July 2025',
      variant: 'research',
      pages: 36,
      download_url: '/documents/swk501-July2025-deep-research-model-answers.pdf',
    },
    {
      document_id: 'jul-2025-claude', semester: 'July 2025', variant: 'claude', pages: 15,
      download_url: '/documents/swk501-July2025-CLAUDE-model-answers.pdf',
    },
    {
      document_id: 'jan-2026',
      semester: 'January 2026',
      variant: 'research',
      pages: 27,
      download_url: '/documents/swk501-Jan2026-deep-research-model-answers.pdf',
    },
    {
      document_id: 'jan-2026-claude', semester: 'January 2026', variant: 'claude', pages: 13,
      download_url: '/documents/swk501-Jan2026-CLAUDE-model-answers.pdf',
    },
  ])
  expect(documents.reduce((total, document) => total + document.pages, 0)).toBe(132)
})
