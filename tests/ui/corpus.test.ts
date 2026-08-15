import { loadPublicCorpus } from '@/lib/corpus'

test('loads the fixed three-semester SWK501 corpus with all 89 pages', () => {
  const documents = loadPublicCorpus()

  expect(documents.map((document) => ({
    document_id: document.document_id,
    semester: document.semester,
    pages: document.pages,
    download_url: document.download_url,
  }))).toEqual([
    {
      document_id: 'jan-2025',
      semester: 'January 2025',
      pages: 26,
      download_url: '/documents/swk501-Jan2025-evidence-based-model-answers.pdf',
    },
    {
      document_id: 'jul-2025',
      semester: 'July 2025',
      pages: 36,
      download_url: '/documents/swk501-July2025-deep-research-model-answers.pdf',
    },
    {
      document_id: 'jan-2026',
      semester: 'January 2026',
      pages: 27,
      download_url: '/documents/swk501-Jan2026-deep-research-model-answers.pdf',
    },
  ])
  expect(documents.reduce((total, document) => total + document.pages, 0)).toBe(89)
})
