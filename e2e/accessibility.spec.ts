import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { fixtures, installChunkedSse, installMockSequence, installMockSse } from './fixtures'


async function expectNoAxeViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
}


function isMobileViewport(page: Page) {
  return (page.viewportSize()?.width ?? Number.POSITIVE_INFINITY) <= 760
}


async function expectEvidenceAvailable(page: Page) {
  if (isMobileViewport(page)) {
    await expect(page.getByRole('button', { name: /review 1 source/i })).toBeVisible()
    return
  }
  await expect(page.getByTestId('source-S1')).toBeVisible()
}


test('has no detectable accessibility violations in the initial state', async ({ page }) => {
  await page.goto('/')
  await expectNoAxeViolations(page)
})


test('shows sources before tokens and has no violations while streaming', async ({ page }) => {
  const stream = await installChunkedSse(page, fixtures.tanArnett)
  await page.goto('/')
  await page.getByRole('textbox').fill('How does Arnett apply to the Tan family?')
  await page.getByRole('button', { name: /find evidence/i }).click()
  await expect(page.getByText('Retrieving evidence.')).toBeVisible()

  await stream.releaseSources()
  await expectEvidenceAvailable(page)
  await expect(page.getByText(/evidence-backed response/i)).toHaveCount(0)

  if (isMobileViewport(page)) {
    await page.getByRole('button', { name: /review 1 source/i }).click()
    await expect(page.getByTestId('source-S1')).toBeVisible()
  }

  await stream.releaseToken()
  await expect(page.getByText('Drafting an answer from 1 source.')).toBeVisible()
  await expect(page.getByText(/evidence-backed response/i)).toBeVisible()
  await expectNoAxeViolations(page)

  await stream.releaseComplete()
  await expect(page.getByText(/answer complete with 1 source/i)).toBeVisible()
})


test('has no detectable accessibility violations for complete and error states', async ({ page }) => {
  await installMockSse(page, fixtures.tanArnett)
  await page.goto('/')
  await page.getByRole('textbox').fill('How does Arnett apply to the Tan family?')
  await page.getByRole('button', { name: /find evidence/i }).click()
  await expect(page.getByText(/answer complete with 1 source/i)).toBeVisible()
  await expectNoAxeViolations(page)

  await page.unroute('**/api/query')
  await installMockSse(page, fixtures.providerError)
  await page.getByRole('textbox').fill('Retry this question')
  await page.getByRole('button', { name: /find evidence/i }).click()
  await expect(page.locator('.workspace-failure[role="alert"]')).toContainText('temporarily unavailable')
  await expectNoAxeViolations(page)
})


test('recovers accessibly from rate limiting after the stated cooldown', async ({ page }) => {
  await installMockSequence(page, [fixtures.rateLimited, fixtures.tanArnett])
  await page.goto('/')
  await page.getByRole('textbox').fill('How does Arnett apply to the Tan family?')
  await page.getByRole('button', { name: /find evidence/i }).click()

  await expect(page.getByText('Rate limit reached. Try again in 12 seconds.')).toBeVisible()
  await expect(page.locator('.workspace-failure[role="alert"]')).toContainText('Too many study requests.')
  await expectNoAxeViolations(page)

  await page.getByRole('button', { name: 'Retry question' }).click()
  await expect(page.getByText(/answer complete with 1 source/i)).toBeVisible()
  await expectNoAxeViolations(page)
})


test('retains evidence and recovers accessibly from a provider stream error', async ({ page }) => {
  await installMockSequence(page, [fixtures.providerStreamError, fixtures.tanArnett])
  await page.goto('/')
  await page.getByRole('textbox').fill('How does Arnett apply to the Tan family?')
  await page.getByRole('button', { name: /find evidence/i }).click()

  await expect(page.getByText(/partial evidence-backed response/i)).toBeVisible()
  await expect(page.locator('.workspace-failure[role="alert"]')).toContainText('temporarily unavailable')
  await expectEvidenceAvailable(page)
  if (isMobileViewport(page)) {
    await page.getByRole('button', { name: /review 1 source/i }).click()
    await expect(page.getByTestId('source-S1')).toBeVisible()
  }
  await expectNoAxeViolations(page)

  if (isMobileViewport(page)) await page.keyboard.press('Escape')

  await page.getByRole('button', { name: 'Retry question' }).click()
  await expect(page.getByText(/answer complete with 1 source/i)).toBeVisible()
  await expectNoAxeViolations(page)
})


test('has no detectable accessibility violations in the mobile evidence sheet', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await installMockSse(page, fixtures.tanArnett)
  await page.goto('/')
  await page.getByRole('textbox').fill('How does Arnett apply to the Tan family?')
  await page.getByRole('button', { name: /find evidence/i }).click()
  await expect(page.getByText(/answer complete with 1 source/i)).toBeVisible()
  await page.getByRole('button', { name: /review 1 source/i }).click()
  await expect(page.getByRole('dialog')).toBeVisible()

  await expectNoAxeViolations(page)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: /review 1 source/i })).toBeFocused()
})
