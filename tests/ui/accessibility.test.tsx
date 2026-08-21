import { render, screen } from '@testing-library/react'
import { AnswerSurface } from '@/components/AnswerSurface'
import { CorpusStrip } from '@/components/CorpusStrip'
import type { CorpusDocument } from '@/lib/api/types'


const document: CorpusDocument = {
  document_id: 'jul-2025',
  filename: 'swk501-July2025-deep-research-model-answers.pdf',
  title: 'SWK501 July 2025 Deep-Research Model Answers',
  semester: 'July 2025',
  variant: 'research',
  pages: 36,
  sha256: '57d8a0be84911246c36dafb484534a0b1d9311088969d8afcf1af32aae4babed',
  download_url: '/documents/swk501-July2025-deep-research-model-answers.pdf',
  topics: ['emerging adulthood'],
}


test('provides the PDF filename to assistive download clients', () => {
  render(<CorpusStrip documents={[document]} />)

  expect(screen.getByRole('link', { name: /download research pdf for july 2025/i })).toHaveAttribute(
    'download',
    document.filename,
  )
})


test('announces a streamed answer as it changes', () => {
  render(
    <AnswerSurface
      answer="An evidence-backed response [S1]."
      citedSourceIds={['S1']}
      status="streaming"
    />,
  )

  const answer = screen.getByText(/evidence-backed response/i).closest('.answer-copy')
  expect(answer).toHaveAttribute('aria-live', 'polite')
  expect(answer).toHaveAttribute('aria-atomic', 'false')
})
