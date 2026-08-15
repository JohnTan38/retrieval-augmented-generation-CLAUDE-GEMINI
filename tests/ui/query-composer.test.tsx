import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { QueryComposer } from '@/components/QueryComposer'

test('submits a trimmed study question and blocks empty input', async () => {
  const onSubmit = vi.fn()
  const user = userEvent.setup()
  render(<QueryComposer disabled={false} onSubmit={onSubmit} />)

  const button = screen.getByRole('button', { name: /find evidence/i })
  expect(button).toBeDisabled()

  await user.type(screen.getByRole('textbox'), '  Explain Arnett  ')
  await user.click(button)

  expect(onSubmit).toHaveBeenCalledWith('Explain Arnett')
})

test('does not submit a whitespace-only question when the form is submitted directly', () => {
  const onSubmit = vi.fn()
  const { container } = render(<QueryComposer disabled={false} onSubmit={onSubmit} />)

  fireEvent.submit(container.querySelector('form')!)

  expect(onSubmit).not.toHaveBeenCalled()
})
