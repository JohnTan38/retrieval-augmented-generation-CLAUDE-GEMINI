import { expect, test } from '@playwright/test'
import { fixtures, installChunkedSse, installMockSse } from './fixtures'


function isMobileViewport(width: number | undefined) {
  return (width ?? Number.POSITIVE_INFINITY) <= 760
}


test('streams a cited answer and focuses exact evidence', async ({ page }) => {
  const stream = await installChunkedSse(page, fixtures.tanArnett)
  await page.goto('/')
  await page.getByRole('textbox').fill('How does Arnett apply to the Tan family?')
  await page.getByRole('button', { name: /find evidence/i }).click()

  await stream.releaseSources()
  if (isMobileViewport(page.viewportSize()?.width)) {
    await expect(page.getByRole('button', { name: /review 1 source/i })).toBeVisible()
  } else {
    await expect(page.getByTestId('source-S1')).toBeVisible()
  }
  await expect(page.getByText(/evidence-backed response/i)).toHaveCount(0)

  await stream.releaseToken()
  await expect(page.getByText(/evidence-backed response/i)).toBeVisible()
  await expect(page.getByText('Drafting an answer from 1 source.')).toBeVisible()

  await stream.releaseComplete()
  await expect(page.getByText(/answer complete with 1 source/i)).toBeVisible()
  await page.getByRole('button', { name: /source s1/i }).click()
  const exactEvidence = page.getByTestId('source-S1')
  await expect(exactEvidence).toHaveAttribute('data-active', 'true')
  await expect(exactEvidence).toBeFocused()
  await expect(exactEvidence).toContainText('July 2025 · page 9')
  await expect(exactEvidence.getByRole('link', { name: /open exact page/i })).toHaveAttribute(
    'href',
    '/documents/swk501-July2025-deep-research-model-answers.pdf#page=9',
  )
})


test('submits a question through the real keyboard focus order', async ({ page }) => {
  await installMockSse(page, fixtures.tanArnett)
  await page.goto('/')

  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: /download research pdf for january 2025/i })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: /download claude recall pdf for january 2025/i })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: /download research pdf for july 2025/i })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: /download claude recall pdf for july 2025/i })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: /download research pdf for january 2026/i })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: /download claude recall pdf for january 2026/i })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('textbox')).toBeFocused()
  await page.keyboard.type('How does Arnett apply to the Tan family?')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('button', { name: /find evidence/i })).toBeFocused()
  await page.keyboard.press('Enter')

  await expect(page.getByText(/answer complete with 1 source/i)).toBeVisible()
})


test('renders accessible navigation for an unmatched route', async ({ page }) => {
  const response = await page.goto('/missing-study-route')

  expect(response?.status()).toBe(404)
  await expect(page.getByRole('heading', { name: /page not found/i })).toBeVisible()
  await expect(page.getByRole('link', { name: /return to study desk/i })).toHaveAttribute('href', '/')
})
