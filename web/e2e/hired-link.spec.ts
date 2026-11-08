import { devices, expect, test } from '@playwright/test'
import { failOnBrowserErrors, FIXTURE, login, shot } from './helpers'

const local = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
const soon = (minutes: number) => local(new Date(Date.now() + minutes * 60_000))
const ewb = () => String(Math.floor(Math.random() * 9e11) + 1e11)
const phoneDevice = { ...devices['Pixel 7'], permissions: ['geolocation'], geolocation: { latitude: 19.2, longitude: 76.8 } }

/** A hired truck with no driver record: the office makes one private link, and the hired driver does the whole journey from it, including the
 *  part with no network. It is the same driver app an own driver uses, just opened by the link instead of a sign-in. */
test('a hired driver does the whole journey from a private link, with the network dropping in the middle', async ({ page, browser }) => {
  test.setTimeout(150_000)
  const noErrors = failOnBrowserErrors(page)

  // --- the office books a trip on the hired truck, with no driver, and makes the driver's link
  await login(page, 'ops@cargoone.dev')
  await expect(page).toHaveURL(/\/office/)
  await page.goto('/office/planning')
  await page.getByRole('button', { name: 'New trip' }).click()
  const d = page.getByRole('dialog', { name: 'New trip' })
  await d.getByLabel('To', { exact: true }).fill('Ahilyanagar')
  await d.getByLabel('Vehicle').selectOption({ label: (await d.getByLabel('Vehicle').locator('option', { hasText: 'MH20 HJ 0002' }).textContent())! })
  await d.getByLabel('Start').fill(soon(60))
  await d.getByLabel('End (optional)').fill(soon(600))
  await d.getByLabel('Freight (₹)').fill('26000')
  await d.getByLabel('E-way bill (12 digits)').fill(ewb())
  await d.getByLabel('E-way bill valid until').fill(local(new Date(Date.now() + 40 * 86_400_000)))
  await d.getByLabel('Goods').fill('Cement bags')
  await d.getByLabel('Consignee name').fill('Om Traders')
  await d.getByLabel('Consignee phone').fill('9876501299')
  await d.getByLabel('Consignee email').fill('om@example.com')
  await d.getByRole('button', { name: 'Create trip' }).click()
  const code = (await d.getByRole('heading', { name: /TRP-/ }).textContent())!.match(/TRP-\d+/)![0]
  await d.getByRole('button', { name: 'Done' }).click()

  await page.goto('/office/trips')
  await page.locator('tr', { hasText: code }).getByRole('button', { name: /link/i }).click()
  const link = page.getByRole('dialog', { name: 'Driver link' })
  await link.getByLabel("Driver's mobile (optional)").fill('9812345670')
  await link.getByLabel("Driver's name (optional)").fill('Kailas Shinde')
  await link.getByRole('button', { name: 'English' }).click()
  await link.getByRole('button', { name: 'Create link and send SMS' }).click()
  await expect(link.getByText(/SMS queued/)).toBeVisible() // simulated here: nothing is sent from a test
  const url = await link.getByLabel('Driver link').inputValue()
  const path = new URL(url).pathname + new URL(url).search

  // the receiver's address, to read the delivery code from
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: `Journey ${code}` }).click()
  const receiverUrl = await page.getByRole('dialog', { name: 'Shipment' }).getByLabel('Receiver link').inputValue()

  // --- the hired driver's phone: no install, no sign-in
  const ctx = await browser.newContext({ ...phoneDevice, viewport: { width: 412, height: 860 } })
  const phone = await ctx.newPage()
  const phoneErrors = failOnBrowserErrors(phone)
  await phone.goto(path)
  await expect(phone.getByRole('heading', { name: 'Kailas Shinde' })).toBeVisible()
  await expect(phone.getByText('Ahilyanagar').first()).toBeVisible()
  await expect(phone.getByRole('link', { name: 'Expenses' })).toBeVisible() // the same tabs an own driver has
  await expect(phone.getByRole('link', { name: 'Help' })).toBeVisible()
  await shot(phone, 'hired-link-home')

  await phone.getByLabel('Truck is loaded').setInputFiles(FIXTURE)
  const started = phone.waitForResponse((r) => r.url().includes('/start') && r.ok())
  await phone.getByRole('button', { name: /Start trip/ }).click()
  await started
  await expect(phone.getByRole('button', { name: /Start trip/ })).toHaveCount(0) // the phone has shown the trip on the road before the network drops
  await expect(phone.getByRole('button', { name: /Delay or problem/ })).toBeVisible()

  // --- the network drops: the delay report and "reached" are kept on the phone
  await ctx.setOffline(true)
  await phone.getByRole('button', { name: /Delay or problem/ }).click()
  const sheet = phone.getByRole('dialog', { name: 'Delay or problem' })
  await sheet.getByRole('button', { name: 'Heavy traffic' }).click()
  await sheet.getByRole('button', { name: '30 min' }).click()
  await sheet.getByRole('button', { name: 'Send' }).click()
  await phone.getByRole('button', { name: /I have reached/ }).click()
  await expect(phone.getByText(/waiting to send/)).toBeVisible()
  await shot(phone, 'hired-link-offline')

  await ctx.setOffline(false) // the link signs the saved actions in again by itself
  await expect(phone.getByText(/waiting to send/)).toHaveCount(0, { timeout: 20_000 })

  // --- the receiver reads out the code; the driver hands over, then sends the proof photo
  const rctx = await browser.newContext({ viewport: { width: 412, height: 860 } })
  const receiver = await rctx.newPage()
  await receiver.goto(new URL(receiverUrl).pathname)
  const codeText = (await receiver.getByRole('region', { name: 'Your delivery code' }).locator('p').nth(0).textContent())!.trim()
  await expect(receiver.getByText('Delay reported')).toBeVisible() // what the driver saved offline reached the receiver
  await phone.getByRole('button', { name: /Goods reached/ }).click()
  const handover = phone.getByRole('dialog', { name: 'Goods reached' })
  await handover.getByLabel("Receiver's 4-digit code").fill(codeText)
  await handover.getByRole('button', { name: 'Confirm delivery' }).click()
  await phone.getByRole('link', { name: /POD/ }).click()
  await phone.locator('input[type=file]').setInputFiles(FIXTURE)
  await expect(phone.getByLabel('verified')).toBeVisible({ timeout: 20_000 })

  // --- an alert tapped later, or the installed app's start page, finds its way back to the link (there is no sign-in to go to)
  await phone.goto('/driver/messages')
  await expect(phone).toHaveURL(/\/u\/[\w-]+\/messages/)
  await phone.goto('/')
  await expect(phone).toHaveURL(/\/u\/[\w-]+$/)

  // --- the office sees every step
  await page.reload()
  await page.getByRole('button', { name: `Journey ${code}` }).click()
  const again = page.getByRole('dialog', { name: 'Shipment' })
  for (const step of ['Loaded', 'On the road', 'Delay reported', 'Reached the delivery point', 'Delivered']) await expect(again.getByText(step).first()).toBeVisible()

  await ctx.close(); await rctx.close()
  await phoneErrors()
  await noErrors()
})
