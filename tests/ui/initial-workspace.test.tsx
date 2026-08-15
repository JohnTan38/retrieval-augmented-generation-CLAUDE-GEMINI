import { render, screen } from '@testing-library/react'
import { StudyWorkspace } from '@/components/StudyWorkspace'
import type { CorpusDocument } from '@/lib/api/types'

const corpusFixture: CorpusDocument[] = [
  { document_id: 'jan-2025', filename: 'jan-2025.pdf', title: 'January model answers', semester: 'January 2025', pages: 26, sha256: 'a'.repeat(64), download_url: '/documents/jan-2025.pdf', topics: ['PPCT'] },
  { document_id: 'jul-2025', filename: 'jul-2025.pdf', title: 'July model answers', semester: 'July 2025', pages: 36, sha256: 'b'.repeat(64), download_url: '/documents/jul-2025.pdf', topics: ['Erikson'] },
  { document_id: 'jan-2026', filename: 'jan-2026.pdf', title: 'January model answers', semester: 'January 2026', pages: 27, sha256: 'c'.repeat(64), download_url: '/documents/jan-2026.pdf', topics: ['emotion coaching'] },
]

test('presents the corpus-ready evidence workspace with guided study prompts', () => {
  render(<StudyWorkspace documents={corpusFixture} />)

  expect(screen.getByRole('heading', { name: /sgcare study desk/i })).toBeVisible()
  expect(screen.getByText(/3 documents.*89 pages/i)).toBeVisible()
  expect(screen.getByRole('button', { name: /find evidence/i })).toBeVisible()
  expect(screen.getByRole('button', { name: /how does arnett/i })).toBeVisible()
  expect(screen.queryByText(/upload pdf/i)).not.toBeInTheDocument()
  expect(screen.queryByLabelText(/api key/i)).not.toBeInTheDocument()
})
