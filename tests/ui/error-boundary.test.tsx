import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import ErrorPage from '@/app/error'
import NotFound from '@/app/not-found'


test('offers accessible recovery without exposing error details', async () => {
  const retry = vi.fn()
  const user = userEvent.setup()
  const error = Object.assign(new Error('private provider stack detail'), { digest: 'private-digest' })

  render(<ErrorPage error={error} retry={retry} />)

  expect(screen.getByRole('main')).toHaveAccessibleName(/could not load/i)
  expect(screen.getByRole('heading', { name: /could not load the study desk/i })).toBeVisible()
  expect(screen.queryByText(/private provider stack detail/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/private-digest/i)).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /try again/i }))
  expect(retry).toHaveBeenCalledOnce()
  expect(screen.getByRole('link', { name: /return to study desk/i })).toHaveAttribute('href', '/')
})


test('gives an unmatched route a heading and home navigation', () => {
  render(<NotFound />)

  expect(screen.getByRole('main')).toHaveAccessibleName(/page not found/i)
  expect(screen.getByRole('heading', { name: /page not found/i })).toBeVisible()
  expect(screen.getByRole('link', { name: /return to study desk/i })).toHaveAttribute('href', '/')
})
