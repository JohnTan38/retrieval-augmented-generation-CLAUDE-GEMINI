import { render, screen } from '@testing-library/react'
import { CorpusStrip } from '@/components/CorpusStrip'
import type { CorpusDocument } from '@/lib/api/types'

const corpusFixture: CorpusDocument[] = [
  {
    document_id: 'jan-2025',
    filename: 'swk501-Jan2025-evidence-based-model-answers.pdf',
    title: 'SWK501 January 2025 Evidence-Based Model Answers',
    semester: 'January 2025',
    pages: 26,
    sha256: 'ce5e335a78d2c2398452643b65eae5aa85e290b37a32dcc28710ae77cc5783b9',
    download_url: '/documents/swk501-Jan2025-evidence-based-model-answers.pdf',
    topics: ['PPCT', 'wisdom'],
  },
  {
    document_id: 'jul-2025',
    filename: 'swk501-July2025-deep-research-model-answers.pdf',
    title: 'SWK501 July 2025 Deep-Research Model Answers',
    semester: 'July 2025',
    pages: 36,
    sha256: '57d8a0be84911246c36dafb484534a0b1d9311088969d8afcf1af32aae4babed',
    download_url: '/documents/swk501-July2025-deep-research-model-answers.pdf',
    topics: ['Erikson', 'multiple intelligence'],
  },
  {
    document_id: 'jan-2026',
    filename: 'swk501-Jan2026-deep-research-model-answers.pdf',
    title: 'SWK501 January 2026 Deep-Research Model Answers',
    semester: 'January 2026',
    pages: 27,
    sha256: '109601093872bd96a0333386b2e474bd67f3c91331fb873218b560ecdc93e1a7',
    download_url: '/documents/swk501-Jan2026-deep-research-model-answers.pdf',
    topics: ['emotion coaching', 'cognitive ageing'],
  },
]

test('shows and downloads the three semester documents', () => {
  render(<CorpusStrip documents={corpusFixture} />)

  expect(screen.getAllByRole('link', { name: /download/i })).toHaveLength(3)
  expect(screen.getByText('January 2025')).toBeVisible()
  expect(screen.getByText('July 2025')).toBeVisible()
  expect(screen.getByText('January 2026')).toBeVisible()
})
