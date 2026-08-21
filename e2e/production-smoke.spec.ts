import { expect, test } from '@playwright/test'


test('production read-only surface is healthy @production', async ({ page }) => {
  test.skip(!process.env.PLAYWRIGHT_BASE_URL, 'Set PLAYWRIGHT_BASE_URL to the deployed application.')
  const response = await page.goto('/')

  expect(response?.ok()).toBe(true)
  await expect(page).toHaveTitle(/SgCare Study Desk/i)
  await expect(page.getByRole('status')).toContainText(/6 documents.*132 pages/i)
})


test('one known Gemini query returns cited evidence @production @live-backend', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'chromium', 'The opt-in live query runs once, in desktop Chromium only.')
  test.skip(process.env.PLAYWRIGHT_LIVE_GEMINI !== '1', 'Set PLAYWRIGHT_LIVE_GEMINI=1 to authorize one provider query.')
  test.skip(!process.env.PLAYWRIGHT_BASE_URL, 'Set PLAYWRIGHT_BASE_URL to the live backend.')

  await page.goto('/')
  await page.getByRole('textbox').fill('Explain Marcia identity status theory')
  await page.getByRole('button', { name: /find evidence/i }).click()

  await expect(page.getByText(/answer complete/i)).toBeVisible({ timeout: 60_000 })
  await expect(page.getByRole('button', { name: /source s1/i }).first()).toBeVisible()
})
