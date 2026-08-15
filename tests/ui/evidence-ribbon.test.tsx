import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { EvidenceRibbon } from '@/components/EvidenceRibbon'
import type { SourceEvidence } from '@/lib/api/types'

const sources: SourceEvidence[] = [
  {
    source_id: 'S1',
    document_id: 'jul-2025',
    filename: 'swk501-July2025-deep-research-model-answers.pdf',
    title: 'SWK501 July 2025 Deep-Research Model Answers',
    semester: 'July 2025',
    page: 9,
    excerpt: 'Arnett describes emerging adulthood as a distinct developmental period.',
    score: 0.91,
    download_url: '/documents/swk501-July2025-deep-research-model-answers.pdf',
  },
  {
    source_id: 'S2',
    document_id: 'jan-2026',
    filename: 'swk501-Jan2026-deep-research-model-answers.pdf',
    title: 'SWK501 January 2026 Deep-Research Model Answers',
    semester: 'January 2026',
    page: 14,
    excerpt: 'Selective optimisation with compensation supports adaptive ageing.',
    score: 0.82,
    download_url: '/documents/swk501-Jan2026-deep-research-model-answers.pdf',
  },
]

function setMobile(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockReturnValue({
      matches,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  })
}

test('shows ranked source cards with exact page links and selection state', async () => {
  setMobile(false)
  const onSelect = vi.fn()
  const user = userEvent.setup()
  render(<EvidenceRibbon sources={sources} activeSourceId="S1" onSelect={onSelect} />)

  const source = screen.getByTestId('source-S1')
  expect(source).toHaveAttribute('data-active', 'true')
  expect(within(source).getByRole('link', { name: /open exact page/i })).toHaveAttribute(
    'href',
    '/documents/swk501-July2025-deep-research-model-answers.pdf#page=9',
  )

  await user.click(within(screen.getByTestId('source-S2')).getByRole('button', { name: /select evidence s2/i }))
  expect(onSelect).toHaveBeenCalledWith('S2')
})

test('mobile evidence sheet traps focus, closes on Escape, and restores its trigger', async () => {
  setMobile(true)
  const user = userEvent.setup()
  render(<EvidenceRibbon sources={sources} activeSourceId={null} onSelect={() => undefined} />)

  const trigger = screen.getByRole('button', { name: /review 2 sources/i })
  await user.click(trigger)

  const dialog = screen.getByRole('dialog', { name: /evidence from your results/i })
  const close = within(dialog).getByRole('button', { name: /close evidence/i })
  expect(close).toHaveFocus()

  await user.keyboard('{Shift>}{Tab}{/Shift}')
  expect(within(dialog).getAllByRole('link', { name: /open exact page/i }).at(-1)).toHaveFocus()

  await user.keyboard('{Tab}')
  expect(close).toHaveFocus()

  await user.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(trigger).toHaveFocus()
})

test('activating a source opens the mobile sheet and focuses the matching evidence', async () => {
  setMobile(true)
  const user = userEvent.setup()
  const scrollIntoView = vi.fn()
  Element.prototype.scrollIntoView = scrollIntoView
  const { rerender } = render(<EvidenceRibbon sources={sources} activeSourceId={null} onSelect={() => undefined} />)

  rerender(<EvidenceRibbon sources={sources} activeSourceId="S1" onSelect={() => undefined} />)

  const source = screen.getByTestId('source-S1')
  expect(screen.getByRole('dialog')).toBeVisible()
  expect(source).toHaveFocus()
  expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'nearest' })

  await user.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
})

test('uses singular mobile copy for one source', () => {
  setMobile(true)

  render(<EvidenceRibbon sources={[sources[0]]} activeSourceId={null} onSelect={() => undefined} />)

  expect(screen.getByRole('button', { name: 'Review 1 source' })).toBeVisible()
})

test('responds when the viewport crosses the mobile breakpoint', () => {
  let matches = false
  let listener: (() => void) | undefined
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: vi.fn().mockReturnValue({
      get matches() { return matches },
      addEventListener: (_name: string, next: () => void) => { listener = next },
      removeEventListener: vi.fn(),
    }),
  })
  render(<EvidenceRibbon sources={sources} activeSourceId={null} onSelect={() => undefined} />)
  expect(screen.getByRole('heading', { name: /evidence behind/i })).toBeVisible()

  act(() => {
    matches = true
    listener?.()
  })

  expect(screen.getByRole('button', { name: /review 2 sources/i })).toBeVisible()
})

test('falls back to desktop evidence when matchMedia is unavailable', () => {
  Reflect.deleteProperty(window, 'matchMedia')

  render(<EvidenceRibbon sources={sources} activeSourceId={null} onSelect={() => undefined} />)

  expect(screen.getByRole('heading', { name: /evidence behind/i })).toBeVisible()
})
