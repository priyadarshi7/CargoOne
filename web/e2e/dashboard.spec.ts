import { expect, test } from '@playwright/test'
import { failOnBrowserErrors, login, shot } from './helpers'

test('ops head sees KPI tiles, missing-POD chart area and the chase list without errors', async ({ page }) => {
  const noErrors = failOnBrowserErrors(page)
  await login(page, 'ops@cargoone.dev')
  await expect(page.getByRole('heading', { name: 'Operations' })).toBeVisible()
  for (const t of ['PODs in system within 24 h', 'POD to invoice', 'Lost or disputed PODs', 'Cash freed by faster billing']) {
    await expect(page.getByText(t, { exact: true })).toBeVisible()
  }
  // the sample PODs reached the system 2 h after delivery, so the 24 h KPI is met
  await expect(page.locator('div', { hasText: /^PODs in system within 24 h/ }).first()).toContainText('100%')
  await expect(page.getByText('Trips without a POD')).toBeVisible()
  await expect(page.getByText('Oldest trips still without a POD')).toBeVisible()
  await expect(page.getByRole('note')).toHaveCount(0) // no demo-data banner on a clean database
  await shot(page, 'dashboard-ops')
  await noErrors()
})

test('MD sees the business overview but not review/billing work screens', async ({ page }) => {
  await login(page, 'md@cargoone.dev')
  await expect(page.getByRole('heading', { name: 'Business overview' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Billing' })).toHaveCount(0)
  await expect(page.getByRole('link', { name: /^Review/ })).toHaveCount(0)
  await shot(page, 'dashboard-md')
})

test('the 90-day window switch reloads the dashboard', async ({ page }) => {
  await login(page, 'md@cargoone.dev')
  await page.getByRole('button', { name: 'Last 90 days' }).click()
  await expect(page.getByText('Trips delivered in the last 90 days')).toBeVisible()
})

test('the public progress page renders the roadmap', async ({ page }) => {
  await page.goto('/progress')
  await expect(page.getByRole('heading', { name: 'Build progress' })).toBeVisible()
  await expect(page.getByRole('progressbar')).toBeVisible()
  await shot(page, 'progress')
})

test('the MD downloads the weekly digest as a PDF', async ({ page }) => {
  await login(page, 'md@cargoone.dev')
  const [file] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download digest' }).click()])
  expect(file.suggestedFilename()).toMatch(/^cargoone-digest-\d{4}-\d{2}-\d{2}\.pdf$/)
  const path = await file.path()
  expect((await import('node:fs')).readFileSync(path).subarray(0, 4).toString()).toBe('%PDF')
})
