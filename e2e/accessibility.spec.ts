import AxeBuilder from '@axe-core/playwright'
import { expect, test, type Page } from '@playwright/test'
import { fixtures, fulfillSse, installMockSse } from './fixtures'


async function expectNoAxeViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze()
  expect(results.violations).toEqual([])
}


test('has no detectable accessibility violations in the initial state', async ({ page }) => {
  await page.goto('/')
  await expectNoAxeViolations(page)
})


test('has no detectable accessibility violations while retrieving', async ({ page }) => {
  let releaseResponse!: () => void
  const responseGate = new Promise<void>((resolve) => { releaseResponse = resolve })
  await page.route('**/api/query', async (route) => {
    await responseGate
    await fulfillSse(route, fixtures.tanArnett)
  })
  await page.goto('/')
  await page.getByRole('textbox').fill('How does Arnett apply to the Tan family?')
  await page.getByRole('button', { name: /find evidence/i }).click()
  await expect(page.getByText('Retrieving evidence.')).toBeVisible()

  await expectNoAxeViolations(page)
  releaseResponse()
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
