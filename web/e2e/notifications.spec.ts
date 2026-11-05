import { expect, test } from '@playwright/test'
import { login, shot } from './helpers'

const tag = () => String(Date.now()).slice(-8)
const when = (days: number, hour: number) => {
  const d = new Date(Date.now() + days * 86_400_000)
  d.setHours(hour, 0, 0, 0)
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

test('a new driver gets an app link, sets their own PIN from it, and is told about the trip they are given', async ({ page, browser }) => {
  const id = tag()
  const name = `Notify Driver ${id}`
  await login(page, 'ops@cargoone.dev')
  await expect(page.getByRole('link', { name: 'Trips' })).toBeVisible()

  // ops registers the driver: the message result and the link are shown right away
  await page.goto('/office/setup?tab=drivers')
  await page.getByRole('button', { name: 'Add a driver' }).click()
  await page.getByLabel('Name', { exact: true }).fill(name)
  await page.getByLabel('Phone').fill(`96${id}`)
  await page.getByRole('dialog').getByLabel('Language').selectOption('en')
  await page.getByLabel('Driving licence number').fill(`MH20${id}007`)
  await page.getByLabel('Licence valid till').fill(`${new Date().getFullYear() + 3}-01-31`)
  await page.getByRole('dialog').getByRole('button', { name: 'Save' }).click()
  await expect(page.getByRole('status')).toContainText('not connected') // honest: WhatsApp is the recording mock until the Meta keys are set
  const link = await page.getByLabel('App link (one-time)').inputValue()
  expect(link).toMatch(/\/onboard\/[\w-]{20,}$/)
  await expect(page.getByLabel('One-time secret')).toHaveText(/^\d{6}$/) // the backup PIN is still there
  await shot(page, 'driver-invite')
  await page.getByRole('button', { name: 'Close' }).last().click()

  // the driver opens the link on their phone, picks a PIN, and lands in the app with a welcome message waiting
  const ctx = await browser.newContext({ viewport: { width: 412, height: 860 } })
  const phone = await ctx.newPage()
  await phone.goto(new URL(link).pathname)
  await expect(phone.getByRole('heading', { name: `Welcome, ${name}` })).toBeVisible()
  await shot(phone, 'driver-onboard')
  await phone.getByLabel('New PIN').fill('7391')
  await phone.getByLabel('Type it again').fill('7391')
  await phone.getByRole('button', { name: 'Save and open the app' }).click()
  await expect(phone).toHaveURL(/\/driver$/)
  await expect(phone.getByRole('region', { name: 'New messages' })).toContainText('Welcome to CargoOne')
  await phone.getByRole('button', { name: 'Mark all as read' }).click()
  await expect(phone.getByRole('region', { name: 'New messages' })).toHaveCount(0)

  // the same link cannot be used twice
  const second = await ctx.newPage()
  await second.goto(new URL(link).pathname)
  await expect(second.getByRole('alert').first()).toContainText('already been used')

  // ops gives the driver a trip: LR number issued, driver notified
  await page.goto('/office/planning')
  await page.getByRole('button', { name: 'New trip' }).click()
  const d = page.getByRole('dialog', { name: 'New trip' })
  await d.getByLabel('To', { exact: true }).fill('Latur')
  await d.getByLabel('Vehicle').selectOption({ label: 'MH20 EL 4521' })
  await d.getByLabel('Driver').selectOption({ label: name })
  await d.getByLabel('Start').fill(when(25, 8))
  await d.getByLabel('End (optional)').fill(when(25, 20))
  await d.getByLabel('Freight (₹)').fill('21000')
  await d.getByLabel('E-way bill (12 digits)').fill('341000000555')
  await d.getByLabel('Goods').fill('Cement bags')
  await d.getByLabel('Weight (tonnes)').fill('18')
  await d.getByLabel('Consignee name').fill('Demo Consignee')
  await d.getByRole('button', { name: 'Create trip' }).click()
  const lr = (await d.getByLabel('LR number').textContent())!.trim()
  await d.getByRole('button', { name: 'Done' }).click()

  await phone.reload()
  const inbox = phone.getByRole('region', { name: 'New messages' })
  await expect(inbox).toContainText('New trip assigned')
  await expect(inbox).toContainText(lr)
  await inbox.getByRole('link').first().click() // the message opens that trip's details
  await expect(phone.getByRole('region', { name: /^TRP-/ })).toContainText(lr)
  await expect(phone.getByRole('region', { name: /^TRP-/ })).toContainText('Cement bags')
  await expect(phone.getByRole('region', { name: /^TRP-/ })).toContainText('Demo Consignee')
  await shot(phone, 'driver-trip-details')
  await ctx.close()

  // and the office can see exactly what was (not) sent
  await page.goto('/office/setup?tab=messages')
  await expect(page.getByText('WhatsApp is not connected')).toBeVisible()
  const row = page.locator('tr', { hasText: 'Trip assigned' }).first()
  await expect(row).toContainText(name)
  await expect(row).toContainText('Not sent (not connected)')
  await page.getByLabel('Send a test email').fill('owner@example.test')
  await page.getByRole('button', { name: 'Send test' }).click()
  await expect(page.getByRole('status')).toContainText('Email is not connected') // honest: recorded, not sent
  await expect(page.locator('tr', { hasText: 'Test email' }).first()).toContainText('o***@example.test')
  await shot(page, 'setup-messages')
})
