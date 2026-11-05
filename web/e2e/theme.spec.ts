import { expect, test } from '@playwright/test'
import { failOnBrowserErrors, login, shot } from './helpers'

const theme = (page: import('@playwright/test').Page) => page.evaluate(() => document.documentElement.dataset.theme)

test('follows the device by default, can be switched, and the choice is remembered', async ({ page }) => {
  const noErrors = failOnBrowserErrors(page)
  await page.emulateMedia({ colorScheme: 'dark' })
  await login(page, 'ops@cargoone.dev')
  await expect.poll(() => theme(page)).toBe('dark') // device is dark, no saved choice
  await page.waitForLoadState('networkidle')
  await expect(page.getByRole('heading', { name: 'Operations desk' })).toBeVisible()
  await shot(page, 'dark-dashboard')

  await page.getByRole('button', { name: /^Theme:/ }).click() // system -> light
  await expect.poll(() => theme(page)).toBe('light')
  await page.getByRole('button', { name: /^Theme:/ }).click() // light -> dark
  await expect.poll(() => theme(page)).toBe('dark')
  await page.reload()
  expect(await theme(page)).toBe('dark') // applied before React renders: no flash
  await expect(page.getByRole('heading', { name: 'Operations' })).toBeVisible()
  await noErrors()
})

test('the main office screens are legible in dark mode', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' })
  await login(page, 'billing@cargoone.dev')
  await page.getByRole('link', { name: 'Trips' }).click()
  await expect(page.getByRole('cell', { name: /TRP-66120/ })).toBeVisible()
  await shot(page, 'dark-trips')
  await page.getByRole('link', { name: 'Review' }).click()
  await page.waitForLoadState('networkidle')
  await shot(page, 'dark-review')
  await page.getByRole('link', { name: 'Billing' }).click()
  await expect(page.getByRole('heading', { name: 'Billing' })).toBeVisible()
  await shot(page, 'dark-billing')
  await page.getByRole('link', { name: 'Import' }).click()
  await page.waitForLoadState('networkidle')
  await shot(page, 'dark-import')
  await page.getByRole('link', { name: 'Setup' }).click()
  await page.waitForLoadState('networkidle')
  await shot(page, 'dark-drivers')
})
