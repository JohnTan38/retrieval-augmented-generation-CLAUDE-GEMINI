import { render, screen } from '@testing-library/react'
import { CorpusStrip } from '@/components/CorpusStrip'
import type { CorpusDocument } from '@/lib/api/types'

const corpusFixture: CorpusDocument[] = [
  {
    document_id: 'jan-2025',
    filename: 'swk501-Jan2025-evidence-based-model-answers.pdf',
    title: 'SWK501 January 2025 Evidence-Based Model Answers',
    semester: 'January 2025',
    variant: 'research',
    pages: 26,
    sha256: 'ce5e335a78d2c2398452643b65eae5aa85e290b37a32dcc28710ae77cc5783b9',
    download_url: '/documents/swk501-Jan2025-evidence-based-model-answers.pdf',
    topics: ['PPCT', 'wisdom'],
  },
  { document_id: 'jan-2025-claude', filename: 'swk501-Jan2025-CLAUDE-model-answers.pdf', title: 'SWK501 January 2025 CLAUDE Recall Pack', semester: 'January 2025', variant: 'claude', pages: 15, sha256: '7a1e8a977ed91c7914cde3253011cee23b0331405ffcbc000674dce01bc1e0de', download_url: '/documents/swk501-Jan2025-CLAUDE-model-answers.pdf', topics: ['active recall', 'PPCT'] },
  {
    document_id: 'jul-2025',
    filename: 'swk501-July2025-deep-research-model-answers.pdf',
    title: 'SWK501 July 2025 Deep-Research Model Answers',
    semester: 'July 2025',
    variant: 'research',
    pages: 36,
    sha256: '57d8a0be84911246c36dafb484534a0b1d9311088969d8afcf1af32aae4babed',
    download_url: '/documents/swk501-July2025-deep-research-model-answers.pdf',
    topics: ['Erikson', 'multiple intelligence'],
  },
  { document_id: 'jul-2025-claude', filename: 'swk501-July2025-CLAUDE-model-answers.pdf', title: 'SWK501 July 2025 CLAUDE Recall Pack', semester: 'July 2025', variant: 'claude', pages: 15, sha256: '472245168c666fd582447837f3f6b834d0bf369ec30ec0f1893f40579e5ba117', download_url: '/documents/swk501-July2025-CLAUDE-model-answers.pdf', topics: ['active recall', 'Bandura'] },
  {
    document_id: 'jan-2026',
    filename: 'swk501-Jan2026-deep-research-model-answers.pdf',
    title: 'SWK501 January 2026 Deep-Research Model Answers',
    semester: 'January 2026',
    variant: 'research',
    pages: 27,
    sha256: '109601093872bd96a0333386b2e474bd67f3c91331fb873218b560ecdc93e1a7',
    download_url: '/documents/swk501-Jan2026-deep-research-model-answers.pdf',
    topics: ['emotion coaching', 'cognitive ageing'],
  },
  { document_id: 'jan-2026-claude', filename: 'swk501-Jan2026-CLAUDE-model-answers.pdf', title: 'SWK501 January 2026 CLAUDE Recall Pack', semester: 'January 2026', variant: 'claude', pages: 13, sha256: '2dd0c32eb4f59d8c676f4f58e553eba0a3ef2c6c2ddd34d08978b994bb955c3b', download_url: '/documents/swk501-Jan2026-CLAUDE-model-answers.pdf', topics: ['active recall', 'emotion coaching'] },
]

test('shows and downloads paired sources for all three semesters', () => {
  render(<CorpusStrip documents={corpusFixture} />)

  expect(screen.getAllByRole('link', { name: /download/i })).toHaveLength(6)
  expect(screen.getAllByText('Research answer')).toHaveLength(3)
  expect(screen.getAllByText('CLAUDE recall pack')).toHaveLength(3)
  expect(screen.getByText('January 2025')).toBeVisible()
  expect(screen.getByText('July 2025')).toBeVisible()
  expect(screen.getByText('January 2026')).toBeVisible()
})
