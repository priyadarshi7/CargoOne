import { expect, test, type Page } from '@playwright/test'
import { join } from 'node:path'
import { failOnBrowserErrors, login, shot } from './helpers'

const PHOTO = join(import.meta.dirname, 'fixtures', 'pod.png')

const when = (days: number, hour: number) => {
  const d = new Date(Date.now() + days * 86_400_000)
  d.setHours(hour, 0, 0, 0)
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

const soon = (minutes: number) => { const d = new Date(Date.now() + minutes * 60_000); return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16) }
const ewb = () => String(Math.floor(Math.random() * 9e11) + 1e11) // one e-way bill covers one trip: every trip here gets its own

async function fill(page: Page, o: { dest: string; lr: string; vehicle: string; driver: string; start: string; end: string }) {
  const d = page.getByRole('dialog', { name: 'New trip' })
  await d.getByLabel('To', { exact: true }).fill(o.dest)
  await d.getByLabel('Vehicle').selectOption({ label: o.vehicle })
  await d.getByLabel('Driver').selectOption({ label: o.driver })
  await d.getByLabel('Start').fill(o.start)
  await d.getByLabel('End (optional)').fill(o.end)
  await d.getByLabel('Freight (₹)').fill('24500')
  await d.getByLabel('Consignee name').fill('Receiver Traders')
  await d.getByLabel('Consignee phone').fill('9876500321')
  await d.getByLabel('Consignee email').fill('receiver@example.com')
  await d.getByLabel('E-way bill (12 digits)').fill(ewb())
  await d.getByLabel('E-way bill valid until').fill(when(40, 8))
  return d
}

test('ops plans a trip, a clash is flagged, then the driver starts it from the phone', async ({ page, browser }) => {
  const noErrors = failOnBrowserErrors(page)
  await login(page, 'ops@cargoone.dev')
  await page.getByRole('link', { name: 'Planning' }).click()
  await expect(page.getByRole('heading', { name: 'Trip planning' })).toBeVisible()

  await page.getByRole('button', { name: 'New trip' }).click()
  let d = await fill(page, { dest: 'Akola', lr: 'LR-PLAN-1', vehicle: 'MH20 GT 7718', driver: 'Plan Test Driver', start: soon(60), end: soon(660) })
  await d.getByRole('button', { name: 'Create trip' }).click()
  await expect(d.getByLabel('LR number')).toHaveText(/^LR\/[A-Z0-9]+\/\d{2}-\d{2}\/\d{6}$/) // issued automatically, never typed
  await shot(page, 'planning-lr-created')
  await d.getByRole('button', { name: 'Done' }).click()
  await expect(page.getByRole('button', { name: /^Trip TRP-7\d+$/ }).first()).toBeVisible()
  await shot(page, 'planning-board')

  // the same driver and truck at an overlapping time -> flagged, with an explicit way to override
  await page.getByRole('button', { name: 'New trip' }).click()
  d = await fill(page, { dest: 'Jalgaon', lr: 'LR-PLAN-2', vehicle: 'MH20 GT 7718', driver: 'Plan Test Driver', start: soon(120), end: soon(300) })
  await d.getByRole('button', { name: 'Create trip' }).click()
  await expect(d.getByRole('alert')).toContainText('already booked')
  await shot(page, 'planning-clash')
  await expect(d.getByRole('button', { name: 'Book anyway' })).toBeVisible()
  await d.getByLabel('Start').fill(when(4, 8)) // fix it instead
  await d.getByLabel('End (optional)').fill(when(4, 18))
  await expect(d.getByRole('button', { name: 'Book anyway' })).toHaveCount(0) // editing clears the override
  await d.getByRole('button', { name: 'Create trip' }).click()
  await d.getByRole('button', { name: 'Done' }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)

  // a trip can be cancelled, but only with a reason
  await page.getByRole('button', { name: 'New trip' }).click()
  d = await fill(page, { dest: 'Dhule', lr: 'LR-PLAN-3', vehicle: 'MH20 EL 4521', driver: 'No driver yet', start: when(6, 8), end: when(6, 18) })
  await d.getByRole('button', { name: 'Create trip' }).click()
  const code = (await d.getByRole('heading', { name: /TRP-/ }).textContent())!.match(/TRP-\d+/)![0]
  await d.getByRole('button', { name: 'Done' }).click()
  await page.getByRole('button', { name: `Trip ${code}` }).click()
  await page.getByRole('button', { name: 'Cancel this trip' }).click()
  const cancelNow = page.getByRole('button', { name: 'Cancel this trip' }).last()
  await expect(cancelNow).toBeDisabled() // no reason yet
  await page.getByLabel('Why is this trip being cancelled?').fill('Client postponed the load')
  await cancelNow.click()
  await expect(page.getByRole('dialog')).toHaveCount(0)

  // --- the driver
  const ctx = await browser.newContext({ viewport: { width: 412, height: 860 } })
  const phone = await ctx.newPage()
  await login(phone, '9000000088', '4821')
  await expect(phone.locator('button', { hasText: 'Truck is loaded' })).toBeVisible() // loading comes first, with a photo
  await expect(phone.getByRole('button', { name: /Start trip/ })).toHaveCount(0)
  await phone.getByLabel('Truck is loaded').setInputFiles(PHOTO)
  await expect(phone.getByRole('button', { name: /Start trip/ })).toBeVisible()
  await shot(phone, 'driver-start-trip')
  await phone.getByRole('button', { name: /Start trip/ }).click()
  await expect(phone.getByRole('button', { name: /Start trip/ })).toHaveCount(0)
  await expect(phone.getByRole('button', { name: /Goods reached/ })).toBeVisible() // once on the road: hand over with the receiver's code, then the photo
  await expect(phone.getByRole('button', { name: /Delay or problem/ })).toBeVisible()
  await ctx.close()

  await page.reload()
  await expect(page.getByRole('button', { name: /^Trip TRP-7\d+$/ }).first()).toBeVisible()
  await noErrors()
})

test('billing can look at the board but not plan; planning is translated', async ({ page }) => {
  await login(page, 'billing@cargoone.dev')
  await page.getByRole('link', { name: 'Planning' }).click()
  await expect(page.getByRole('heading', { name: 'Trip planning' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'New trip' })).toHaveCount(0)
  await page.getByLabel('Language').selectOption('hi')
  await expect(page.getByRole('heading', { name: 'ट्रिप की योजना' })).toBeVisible()
  await page.getByLabel('भाषा').selectOption('en')
})

test('trips of one truck that overlap in time are drawn in separate lanes, none hidden behind another', async ({ page }) => {
  await login(page, 'ops@cargoone.dev')
  await page.getByRole('link', { name: 'Planning' }).click()
  await expect(page.getByRole('heading', { name: 'Trip planning' })).toBeVisible()

  // a long trip, then a second one on the same truck inside it (booked anyway): the second used to be drawn under the first
  await page.getByRole('button', { name: 'New trip' }).click()
  let d = await fill(page, { dest: 'Lane-long', lr: 'LR-LANE-1', vehicle: 'MH20 EL 4521', driver: 'No driver yet', start: when(6, 6), end: when(10, 20) })
  await d.getByRole('button', { name: 'Create trip' }).click()
  await d.getByRole('button', { name: 'Done' }).click()
  await page.getByRole('button', { name: 'New trip' }).click()
  d = await fill(page, { dest: 'Lane-short', lr: 'LR-LANE-2', vehicle: 'MH20 EL 4521', driver: 'No driver yet', start: when(7, 9), end: when(7, 18) })
  await d.getByRole('button', { name: 'Create trip' }).click()
  await d.getByRole('button', { name: 'Book anyway' }).click()
  await d.getByRole('button', { name: 'Done' }).click()

  const long = page.locator('button[title*="Lane-long"]')
  const short = page.locator('button[title*="Lane-short"]')
  await expect(long).toBeVisible()
  await expect(short).toBeVisible()
  const a = (await long.boundingBox())!
  const b = (await short.boundingBox())!
  expect(b.y >= a.y + a.height || a.y >= b.y + b.height, 'bars must not overlap on screen').toBe(true)
  await shot(page, 'planning-lanes')
})
