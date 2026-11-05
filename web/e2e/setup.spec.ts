import { expect, test } from '@playwright/test'
import { login, shot } from './helpers'

const uniq = () => String(Date.now()).slice(-8)
const licence = (tag: string) => `MH20${tag}001`
const nextYear = () => `${new Date().getFullYear() + 2}-06-30`

test('ops registers a hired vendor, their truck and driver; the new driver signs in with the one-time PIN', async ({ page }) => {
  const tag = uniq()
  const phone = `98${tag}`
  const vendor = `Shah Transport ${tag}`
  await login(page, 'ops@cargoone.dev')
  await page.getByRole('link', { name: 'Setup' }).click()

  // vendor
  await page.getByRole('tab', { name: 'Hired vendors' }).click()
  await page.getByRole('button', { name: 'Add a vendor' }).click()
  await page.getByLabel('Vendor name').fill(vendor)
  await page.getByLabel('Contact person').fill('Mr Shah')
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click()
  await expect(page.locator('tr', { hasText: vendor })).toBeVisible()
  await shot(page, 'setup-vendors')

  // truck from that vendor
  await page.getByRole('tab', { name: 'Trucks' }).click()
  await page.getByRole('button', { name: 'Add a truck' }).click()
  await page.getByLabel('Registration number').fill(`mh20hv${tag.slice(-4)}`)
  await page.getByLabel(/^Owner/).selectOption({ label: `Hired · ${vendor}` })
  await page.getByLabel('Insurance valid till').fill('2020-01-01')
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click()
  const truckRow = page.locator('tr', { hasText: `MH20 HV ${tag.slice(-4)}` })
  await expect(truckRow).toContainText('Hired')
  await expect(truckRow).toContainText('Expired')
  await shot(page, 'setup-trucks')

  // driver from that vendor
  await page.getByRole('tab', { name: 'Drivers' }).click()
  await page.getByRole('button', { name: 'Add a driver' }).click()
  await page.getByLabel('Name', { exact: true }).fill('Hired Test Driver')
  await page.getByLabel('Phone').fill(phone)
  await page.getByLabel('Employment type').selectOption({ label: 'Hired through a vendor' })
  await page.getByLabel('Hired from').selectOption({ label: vendor })
  await page.getByLabel('Driving licence number').fill(licence(tag))
  await page.getByLabel('Licence valid till').fill(nextYear())
  await page.getByLabel('Assigned truck').selectOption({ label: `MH20 HV ${tag.slice(-4)}` })
  await page.getByLabel('Licence photo (front)').setInputFiles('e2e/fixtures/pod-blurry.jpg')
  await shot(page, 'setup-add-driver')
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click()
  const pin = (await page.getByLabel('One-time secret').textContent())!.trim()
  expect(pin).toMatch(/^\d{6}$/)
  await shot(page, 'setup-driver-pin')
  await page.getByRole('button', { name: 'Close' }).last().click()
  const row = page.locator('tr', { hasText: 'Hired Test Driver' })
  await expect(row).toContainText(vendor)
  await expect(row).toContainText(`MH20 HV ${tag.slice(-4)}`)

  // the details page shows every field and the licence photo that was uploaded with the form
  await row.getByRole('button', { name: 'Details' }).click()
  const details = page.getByRole('dialog')
  await expect(details).toContainText(licence(tag))
  await expect(details).toContainText('Hired through a vendor')
  await expect(details.locator('li', { hasText: 'Licence photo (front)' })).toContainText('KB')
  await expect(details.locator('li', { hasText: 'Licence photo (back)' })).toContainText('Not uploaded')
  await shot(page, 'setup-driver-details')
  await details.getByRole('button', { name: 'Close' }).last().click()

  // registering the same number again is refused in plain words
  await page.getByRole('button', { name: 'Add a driver' }).click()
  await page.getByLabel('Name', { exact: true }).fill('Copy')
  await page.getByLabel('Phone').fill(phone)
  await page.getByLabel('Driving licence number').fill(licence(tag))
  await page.getByLabel('Licence valid till').fill(nextYear())
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click()
  await expect(page.getByRole('alert')).toContainText('already belongs')
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel' }).click()

  // the new driver signs in with the PIN and is sent to choose their own
  await page.getByRole('button', { name: 'Sign out' }).click()
  await login(page, phone, pin)
  await expect(page).toHaveURL(/\/driver\/pin$/)
})

test('deactivating a driver removes them from planning; billing can look but not change', async ({ page }) => {
  await login(page, 'ops@cargoone.dev')
  await expect(page.getByRole('link', { name: 'Trips' })).toBeVisible()
  await page.goto('/office/setup?tab=drivers')
  await page.getByRole('button', { name: 'Add a driver' }).click()
  const phone = `97${uniq()}`
  await page.getByLabel('Name', { exact: true }).fill('Leaver Test')
  await page.getByLabel('Phone').fill(phone)
  await page.getByLabel('Driving licence number').fill(licence(uniq()))
  await page.getByLabel('Licence valid till').fill(nextYear())
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click()
  await expect(page.getByLabel('One-time secret')).toBeVisible()
  await page.getByRole('button', { name: 'Close' }).last().click()
  await page.locator('tr', { hasText: 'Leaver Test' }).getByRole('button', { name: 'Edit' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Deactivate' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Deactivate' }).click()
  await expect(page.locator('tr', { hasText: 'Leaver Test' })).toHaveCount(0) // hidden by default
  await page.getByLabel('Show inactive').check()
  await expect(page.locator('tr', { hasText: 'Leaver Test' })).toContainText('Inactive')
  await page.getByRole('button', { name: 'Sign out' }).click()

  await login(page, 'billing@cargoone.dev')
  await expect(page.getByRole('link', { name: 'Trips' })).toBeVisible()
  await page.goto('/office/setup?tab=trucks')
  await expect(page.getByText('You can view this list')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Add a truck' })).toHaveCount(0)
})

test('only the admin sees office staff, and a new account must replace its temporary password', async ({ page }) => {
  const email = `staff${uniq()}@example.test`
  await login(page, 'admin@cargoone.dev')
  await expect(page.getByRole('link', { name: 'Trips' })).toBeVisible()
  await page.goto('/office/setup?tab=staff')
  await page.getByRole('button', { name: 'Add office staff' }).click()
  await page.getByLabel('Name', { exact: true }).fill('New Billing Person')
  await page.getByLabel('Email').fill(email)
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click()
  const pw = (await page.getByLabel('One-time secret').textContent())!.trim()
  await shot(page, 'setup-staff')
  await page.getByRole('button', { name: 'Close' }).last().click()
  await page.getByRole('button', { name: 'Sign out' }).click()

  await login(page, email, pw)
  await expect(page).toHaveURL(/\/office\/account$/) // sent to choose a password first
  await page.getByRole('button', { name: 'Sign out' }).click()

  await login(page, 'ops@cargoone.dev')
  await expect(page.getByRole('link', { name: 'Trips' })).toBeVisible()
  await page.goto('/office/setup?tab=staff')
  await expect(page.getByRole('tab', { name: 'Office staff' })).toHaveCount(0)
})
