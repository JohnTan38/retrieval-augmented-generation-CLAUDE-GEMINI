import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { AnswerSurface } from '@/components/AnswerSurface'

test('renders study Markdown without executing raw HTML or unsafe links', () => {
  render(
    <AnswerSurface
      answer={'## Application\n\n- Use **PPCT**.\n\n<img src=x onerror=alert(1)>\n\n[unsafe](javascript:alert(1))'}
      citedSourceIds={[]}
      status="complete"
    />,
  )

  expect(screen.getByRole('heading', { name: 'Application' })).toBeVisible()
  expect(screen.getByText('PPCT')).toBeVisible()
  expect(document.querySelector('img')).not.toBeInTheDocument()
  expect(screen.getByText('unsafe')).not.toHaveAttribute('href')
})

test('turns only current source markers into citation controls', async () => {
  const onCitationActivate = vi.fn()
  const user = userEvent.setup()
  render(
    <AnswerSurface
      answer="Arnett supports this interpretation [S1], but [S9] is unknown."
      citedSourceIds={['S1']}
      status="complete"
      onCitationActivate={onCitationActivate}
    />,
  )

  await user.click(screen.getByRole('button', { name: /source s1/i }))

  expect(onCitationActivate).toHaveBeenCalledWith('S1')
  expect(screen.getByText(/but \[S9\] is unknown/)).toBeVisible()
  expect(screen.queryByRole('button', { name: /source s9/i })).not.toBeInTheDocument()
})

test('shows an integrity warning when completion marks citations invalid', () => {
  render(
    <AnswerSurface
      answer="A claim with an unknown source [S4]."
      citedSourceIds={['S1']}
      citationValid={false}
      status="complete"
    />,
  )

  expect(screen.getByRole('alert')).toHaveTextContent(/could not verify every citation/i)
})

test('shows the same integrity warning for a completed degraded answer', () => {
  render(<AnswerSurface answer="Grounded [S1]." citedSourceIds={['S1']} citationValid={false} status="degraded" />)

  expect(screen.getByRole('alert')).toHaveTextContent(/could not verify every citation/i)
})
