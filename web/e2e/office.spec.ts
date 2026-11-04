import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { failOnBrowserErrors, login, shot } from './helpers'

test.describe.configure({ mode: 'serial' })

test('billing executive reviews a shortage POD, bills it and downloads PDF + Tally files', async ({ page }) => {
  const noErrors = failOnBrowserErrors(page)
  await login(page, 'billing@cargoone.dev')

  // 1. Review queue holds the shortage POD from the sample data
  await expect(page.getByRole('heading', { name: 'Review queue' })).toBeVisible()
  const row = page.getByRole('link', { name: /TRP-66141/ })
  await expect(row).toContainText('Shortage / damage remark')
  await shot(page, 'review-list')
  await row.click()

  // 2. The POD photo really loads (it is fetched with the auth header, so a broken <img> would mean a bug)
  const img = page.getByRole('img', { name: 'Proof of delivery' })
  await expect(img).toBeVisible()
  await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0)
  await expect(page.getByLabel('LR number')).toHaveValue('LR-88141')
  await shot(page, 'review-detail')

  // 3. Approve (shortage was recorded on the paper; the executive accepts it)
  await page.getByRole('button', { name: /Approve/ }).click()
  await expect(page.getByText('Nothing waiting for review.')).toBeVisible()
  // regression: the nav badge used to keep saying "Review 1" after the last item was approved
  await expect(page.getByRole('link', { name: 'Review', exact: true })).toBeVisible()

  // 4. It now appears under Ready to bill, grouped by client and period
  await page.getByRole('link', { name: 'Billing' }).click()
  const group = page.locator('section', { hasText: 'Company D' })
  await expect(group).toContainText('TRP-66141')
  await shot(page, 'billing-ready')
  await group.getByRole('button', { name: 'Create invoice' }).click()

  // 5. Invoice exists; PDF and Tally XML download and have real content
  const invoiceRow = page.locator('tr', { hasText: 'Company D' })
  await expect(invoiceRow).toContainText('CO/')
  await shot(page, 'billing-invoices')

  const [pdf] = await Promise.all([page.waitForEvent('download'), invoiceRow.getByRole('button', { name: 'PDF' }).click()])
  expect(pdf.suggestedFilename()).toMatch(/\.pdf$/)
  const pdfBytes = readFileSync(await pdf.path())
  expect(pdfBytes.subarray(0, 4).toString()).toBe('%PDF')
  expect(pdfBytes.length).toBeGreaterThan(3000)

  const [tally] = await Promise.all([page.waitForEvent('download'), invoiceRow.getByRole('button', { name: 'Tally' }).click()])
  expect(tally.suggestedFilename()).toMatch(/\.xml$/)
  const xml = readFileSync(await tally.path(), 'utf-8')
  expect(xml).toContain('<VOUCHER VCHTYPE="Sales"')
  expect(xml).toContain('41200.00')

  await expect(invoiceRow).not.toContainText('Not yet') // exported date is now stamped
  await noErrors()
})

test('the trips list shows sample trips without consignee personal data', async ({ page }) => {
  await login(page, 'ops@cargoone.dev')
  await page.getByRole('link', { name: 'Trips' }).click()
  await expect(page.getByRole('cell', { name: /TRP-66120/ })).toBeVisible()
  await expect(page.getByText('Demo Consignee')).toHaveCount(0)
  await shot(page, 'trips')
})

test('office screens switch to Hindi and Marathi and remember the choice', async ({ page }) => {
  await login(page, 'ops@cargoone.dev')
  await page.getByLabel('Language').selectOption('hi')
  await expect(page.getByRole('link', { name: 'ट्रिप' })).toBeVisible()
  await page.getByRole('link', { name: 'ट्रिप' }).click()
  await expect(page.getByRole('columnheader', { name: 'ग्राहक' })).toBeVisible()
  await expect(page.getByText('सत्यापित').first()).toBeVisible()
  await shot(page, 'office-trips-hindi')

  await page.reload()
  await expect(page.getByLabel('भाषा')).toHaveValue('hi') // remembered
  await page.getByLabel('भाषा').selectOption('mr')
  await page.getByRole('link', { name: 'तपासणी' }).click()
  await expect(page.getByRole('heading', { name: 'तपासणी यादी' })).toBeVisible()
  await shot(page, 'office-review-marathi')

  await page.getByLabel('भाषा').selectOption('en') // leave English for other tests in this browser context
  await expect(page.getByRole('link', { name: 'Trips' })).toBeVisible()
})

test('billing, import, dashboard and review detail also switch language', async ({ page }) => {
  await login(page, 'billing@cargoone.dev')
  await page.getByLabel('Language').selectOption('hi')
  await page.getByRole('link', { name: 'बिलिंग' }).click()
  await expect(page.getByRole('heading', { name: 'बिलिंग' })).toBeVisible()
  await expect(page.getByRole('button', { name: /बिल के लिए तैयार/ })).toBeVisible()
  await shot(page, 'billing-hindi')
  await page.getByRole('link', { name: 'आयात' }).click()
  await expect(page.getByRole('heading', { name: 'ट्रिप आयात करें' })).toBeVisible()
  await page.getByRole('link', { name: 'ड्राइवर' }).click()
  await expect(page.getByRole('heading', { name: 'ड्राइवर' })).toBeVisible()
  await page.getByLabel('भाषा').selectOption('mr')
  await page.getByRole('link', { name: 'तपासणी' }).click()
  await expect(page.getByRole('heading', { name: 'तपासणी यादी' })).toBeVisible()
  await shot(page, 'review-queue-marathi')
  await page.getByLabel('भाषा').selectOption('en')
})

test('the ops dashboard switches language', async ({ page }) => {
  await login(page, 'ops@cargoone.dev')
  await page.getByLabel('Language').selectOption('mr')
  await expect(page.getByRole('heading', { name: 'कामकाज' })).toBeVisible()
  await expect(page.getByText('24 तासांत सिस्टममध्ये आलेल्या पावत्या')).toBeVisible()
  await shot(page, 'dashboard-marathi')
  await page.getByLabel('भाषा').selectOption('en')
})
