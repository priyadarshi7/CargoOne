import { devices, expect, test } from '@playwright/test'
import { failOnBrowserErrors, FIXTURE, login, shot } from './helpers'

test('driver logs expenses, the office approves and rejects, trip profit and advances follow', async ({ page, browser }) => {
  // --- the driver's phone
  const ctx = await browser.newContext({ ...devices['Pixel 7'] })
  const phone = await ctx.newPage()
  const phoneErrors = failOnBrowserErrors(phone)
  await login(phone, '9000000066', '4821')
  await phone.getByRole('link', { name: 'Expenses' }).click()
  await expect(phone.getByRole('heading', { name: 'Add expense' })).toBeVisible()

  await phone.getByRole('radio', { name: 'Toll' }).click()
  await phone.getByLabel('Amount (₹)').fill('450')
  await phone.getByLabel('Bill photo (optional)').setInputFiles(FIXTURE)
  await shot(phone, 'driver-expense-form')
  await phone.getByRole('button', { name: 'Save' }).click()
  await expect(phone.getByRole('status')).toContainText('Saved')
  await phone.getByRole('button', { name: 'Add another' }).click()

  await phone.getByRole('radio', { name: 'Diesel' }).click()
  await phone.getByLabel('Amount (₹)').fill('9000')
  await phone.getByRole('button', { name: 'Save' }).click()
  await expect(phone.getByRole('alert')).toContainText('litres') // diesel needs litres + odometer
  await phone.getByLabel('Litres').fill('100')
  await phone.getByLabel('Odometer (km)').fill('20000')
  await phone.getByRole('button', { name: 'Save' }).click()
  await expect(phone.getByRole('status')).toContainText('Saved')

  // --- the office
  const noErrors = failOnBrowserErrors(page)
  await login(page, 'ops@cargoone.dev')
  await page.getByRole('link', { name: 'Expenses' }).click()
  await expect(page.getByRole('heading', { name: 'Expenses and profit' })).toBeVisible()
  const toll = page.locator('li', { hasText: 'Toll' }).filter({ hasText: 'Money Test Driver' })
  const diesel = page.locator('li', { hasText: 'Fuel' }).filter({ hasText: 'Money Test Driver' })
  await expect(toll).toContainText('₹450')
  await expect(diesel).toContainText('100 L')
  await toll.getByRole('button', { name: 'View receipt' }).click()
  await expect(page.getByRole('dialog', { name: 'Receipt' }).getByRole('img')).toBeVisible()
  await shot(page, 'office-expense-receipt')
  await page.getByRole('button', { name: 'Close' }).click()
  await shot(page, 'office-expenses-review')

  await toll.getByRole('button', { name: 'Approve' }).click()
  await expect(toll).toHaveCount(0)
  await diesel.getByRole('button', { name: 'Reject' }).click()
  await page.getByLabel(/Why is it rejected/).fill('no bill attached')
  await page.getByRole('button', { name: 'Reject', exact: true }).last().click()
  await expect(diesel).toHaveCount(0)

  // --- profit: only the approved Rs 450 counts
  await page.getByRole('tab', { name: 'Trip profit' }).click()
  const row = page.locator('tr', { hasText: 'TRP-E2E-MONEY' })
  await expect(row).toContainText('₹30,000')
  await expect(row).toContainText('₹450')
  await expect(row).toContainText('₹29,550')
  await shot(page, 'office-trip-profit')

  // --- advance and settlement
  await page.getByRole('tab', { name: 'Advances' }).click()
  await page.getByLabel('Driver').selectOption({ label: 'Money Test Driver' })
  await page.getByLabel('Amount (₹)').fill('2000')
  await page.getByRole('button', { name: 'Record advance' }).click()
  await expect(page.getByRole('status')).toContainText('Advance recorded')
  await expect(page.locator('tr', { hasText: 'Money Test Driver' })).toContainText('₹1,550') // 2,000 given - 450 approved
  await shot(page, 'office-advances')

  // --- the driver sees the outcome, with the reason
  await phone.reload()
  await expect(phone.locator('li', { hasText: 'Toll' })).toContainText('Approved')
  await expect(phone.locator('li', { hasText: 'Diesel' })).toContainText('Rejected')
  await expect(phone.locator('li', { hasText: 'Diesel' })).toContainText('no bill attached')
  await expect(phone.getByRole('region', { name: 'Cash with you' })).toContainText('₹1,550') // 2,000 advance - 450 approved
  await shot(phone, 'driver-expense-status')
  await noErrors(); await phoneErrors()
  await ctx.close()
})

test('the MD reads profit but cannot approve; Hindi works', async ({ page }) => {
  await login(page, 'md@cargoone.dev')
  await page.getByRole('link', { name: 'Expenses' }).click()
  await expect(page.getByRole('tab', { name: 'To review' })).toHaveCount(0)
  await expect(page.getByRole('tab', { name: 'Trip profit' })).toBeVisible()
  await page.getByLabel('Language').selectOption('hi')
  await expect(page.getByRole('heading', { name: 'खर्चे और मुनाफ़ा' })).toBeVisible()
  await page.getByLabel('भाषा').selectOption('en')
})
