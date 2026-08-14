import { render, screen } from '@testing-library/react'
import { StudyWorkspace } from '@/components/StudyWorkspace'

test('introduces the SWK501 evidence workspace without upload or key controls', () => {
  render(<StudyWorkspace />)

  expect(screen.getByRole('heading', { name: /sgcare study desk/i })).toBeVisible()
  expect(screen.getByText(/swk501 evidence workspace/i)).toBeVisible()
  expect(screen.queryByText(/upload pdf/i)).not.toBeInTheDocument()
  expect(screen.queryByLabelText(/api key/i)).not.toBeInTheDocument()
})
