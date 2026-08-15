import { expect, test } from '@playwright/test'
import { fixtures, installMockSse } from './fixtures'


test('streams a cited answer and focuses exact evidence', async ({ page }) => {
  await installMockSse(page, fixtures.tanArnett)
  await page.goto('/')
  await page.getByRole('textbox').fill('How does Arnett apply to the Tan family?')
  await page.getByRole('button', { name: /find evidence/i }).click()
  await expect(page.getByText(/evidence-backed response/i)).toBeVisible()
  await page.getByRole('button', { name: /source s1/i }).click()
  await expect(page.getByTestId('source-S1')).toHaveAttribute('data-active', 'true')
  await expect(page.getByTestId('source-S1')).toBeFocused()
})


test('submits a question through the real keyboard focus order', async ({ page }) => {
  await installMockSse(page, fixtures.tanArnett)
  await page.goto('/')

  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: /download pdf for january 2025/i })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: /download pdf for july 2025/i })).toBeFocused()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: /download pdf for january 2026/i })).toBeFocused()
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
