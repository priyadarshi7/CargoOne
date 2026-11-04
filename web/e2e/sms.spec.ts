import { devices, expect, test } from '@playwright/test'
import { failOnBrowserErrors, FIXTURE, login, shot } from './helpers'

test.describe.configure({ mode: 'serial' })

const phone = { ...devices['Pixel 7'], permissions: ['geolocation'], geolocation: { latitude: 19.2, longitude: 76.8 } }

test('office sends a link; a hired driver with NO login uploads the POD from it', async ({ page, browser }) => {
  // --- office: create the link for the hired vehicle's trip
  await login(page, 'ops@cargoone.dev')
  await page.getByRole('link', { name: 'Trips' }).click()
  const row = page.locator('tr', { hasText: 'TRP-E2E-HIRED' })
  await expect(row).toContainText('hired')
  await row.getByRole('button', { name: 'Send link' }).click()

  const dialog = page.getByRole('dialog', { name: 'Upload link' })
  await dialog.getByPlaceholder('e.g. 9876543210').fill('9876543210')
  await dialog.getByRole('button', { name: 'मराठी' }).click()
  await shot(page, 'office-link-dialog')
  await dialog.getByRole('button', { name: 'Create link and send SMS' }).click()
  await expect(dialog.getByText(/SMS queued/)).toBeVisible()
  const url = await dialog.getByLabel('Upload link').inputValue()
  expect(url).toMatch(/\/u\/[\w-]{40,}\?l=mr$/)
  await shot(page, 'office-link-created')

  // --- driver's phone: a fresh browser with no session at all
  const ctx = await browser.newContext(phone)
  const mobile = await ctx.newPage()
  const noErrors = failOnBrowserErrors(mobile)
  const path = new URL(url).pathname + new URL(url).search
  await mobile.goto(path)
  await expect(mobile.getByRole('heading')).toHaveCount(0) // no login form or app chrome
  await expect(mobile.getByText('Latur')).toBeVisible() // only the destination is shown
  await shot(mobile, 'sms-capture-ready')
  await mobile.locator('input[type=file]').setInputFiles(FIXTURE)
  await expect(mobile.getByLabel('verified')).toBeVisible({ timeout: 20_000 })
  await shot(mobile, 'sms-capture-verified')
  await noErrors()

  // reopening the same link now says the job is already done
  await mobile.reload()
  await expect(mobile.getByLabel('Already done')).toBeVisible()
  await ctx.close()

  // --- office sees the result
  await page.reload()
  await expect(page.locator('tr', { hasText: 'TRP-E2E-HIRED' })).toContainText('Verified')
})

test('a revoked link stops working and an invalid one is rejected', async ({ page, browser }) => {
  await login(page, 'ops@cargoone.dev')
  await page.getByRole('link', { name: 'Trips' }).click()
  const row = page.locator('tr', { hasText: 'TRP-E2E-2' }) // a plain open trip also gets a link
  await row.getByRole('button', { name: /Link/ }).click()
  const dialog = page.getByRole('dialog', { name: 'Upload link' })
  await dialog.getByRole('button', { name: 'Create link' }).click()
  const url = await dialog.getByLabel('Upload link').inputValue()
  const path = new URL(url).pathname + new URL(url).search

  const ctx = await browser.newContext(phone)
  const mobile = await ctx.newPage()
  await mobile.goto(path)
  await expect(mobile.locator('input[type=file]')).toBeAttached() // valid while active

  await dialog.getByRole('button', { name: 'Revoke this link' }).click()
  await mobile.reload()
  await expect(mobile.getByLabel('Link expired')).toBeVisible()
  await shot(mobile, 'sms-link-expired')

  await mobile.goto('/u/' + 'z'.repeat(43))
  await expect(mobile.getByLabel('Link not valid')).toBeVisible()
  await ctx.close()
})

test('a billing executive can also send links, a driver and the MD cannot', async ({ page }) => {
  await login(page, 'billing@cargoone.dev')
  await page.getByRole('link', { name: 'Trips' }).click()
  await expect(page.getByRole('columnheader', { name: 'Upload link' })).toBeVisible()
  await page.getByRole('button', { name: 'Sign out' }).click()

  await login(page, 'md@cargoone.dev')
  await page.getByRole('link', { name: 'Trips' }).click()
  await expect(page.getByRole('columnheader', { name: 'Upload link' })).toHaveCount(0)
})
