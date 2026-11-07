import { expect, test } from '@playwright/test'
import { failOnBrowserErrors, FIXTURE, login, shot } from './helpers'

const local = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
const soon = (minutes: number) => local(new Date(Date.now() + minutes * 60_000))
const ewb = () => String(Math.floor(Math.random() * 9e11) + 1e11)

test('a shipment from booking to delivery: the driver loads, reports a delay, the receiver reads out a code, and the client and receiver each see their own page', async ({ page, browser }) => {
  test.setTimeout(120_000) // a whole shipment across four browsers
  const noErrors = failOnBrowserErrors(page)

  // --- the office books the trip, with the receiver's phone
  await login(page, 'ops@cargoone.dev')
  await expect(page).toHaveURL(/\/office/) // wait for the sign-in to finish before moving on
  await page.goto('/office/planning')
  await page.getByRole('button', { name: 'New trip' }).click()
  const d = page.getByRole('dialog', { name: 'New trip' })
  await d.getByLabel('To', { exact: true }).fill('Parbhani')
  await d.getByLabel('Vehicle').selectOption({ label: 'MH20 JR 0001 · 20 t' })
  await d.getByLabel('Driver').selectOption({ label: 'Journey Test Driver' })
  await d.getByLabel('Start').fill(soon(60))
  await d.getByLabel('End (optional)').fill(soon(600))
  await d.getByLabel('Freight (₹)').fill('31000')
  await d.getByLabel('E-way bill (12 digits)').fill(ewb())
  await d.getByLabel('E-way bill valid until').fill(local(new Date(Date.now() + 40 * 86_400_000)))
  await d.getByLabel('Goods').fill('Cotton bales')
  await d.getByLabel('Consignee name').fill('Sai Traders')
  await d.getByLabel('Consignee phone').fill('9876501234')
  await d.getByLabel('Consignee email').fill('sai@example.com')
  await d.getByRole('button', { name: 'Create trip' }).click()
  const code = (await d.getByRole('heading', { name: /TRP-/ }).textContent())!.match(/TRP-\d+/)![0]
  await d.getByRole('button', { name: 'Done' }).click()

  // --- the office opens the shipment and takes the two addresses
  await page.goto('/office/trips')
  await page.getByRole('button', { name: `Journey ${code}` }).click()
  const dialog = page.getByRole('dialog', { name: 'Shipment' })
  await expect(dialog.getByText('Driver has seen the job')).toBeVisible()
  const clientUrl = await dialog.getByLabel('Client link').inputValue()
  const receiverUrl = await dialog.getByLabel('Receiver link').inputValue()
  expect(clientUrl).toContain('/s/')
  expect(receiverUrl).not.toEqual(clientUrl)
  await shot(page, 'shipment-office-dialog')

  // --- the driver: accepts by opening, loads with a photo, starts, reports a delay
  const ctx = await browser.newContext({ viewport: { width: 412, height: 860 } })
  const phone = await ctx.newPage()
  await login(phone, '9000000055', '4821')
  await expect(phone).toHaveURL(/\/driver/)
  await phone.getByLabel('Truck is loaded').setInputFiles(FIXTURE)
  const started = phone.waitForResponse((r) => r.url().includes('/start') && r.ok())
  await phone.getByRole('button', { name: /Start trip/ }).click()
  await started // the phone shows "on the road" at once; the server must have it before a delay can be reported
  await phone.getByRole('button', { name: /Delay or problem/ }).click()
  const sheet = phone.getByRole('dialog', { name: 'Delay or problem' })
  await expect(sheet.getByRole('button', { name: 'Send' })).toBeDisabled() // reason and time first
  await sheet.getByRole('button', { name: 'Heavy traffic' }).click()
  await sheet.getByRole('button', { name: '30 min' }).click()
  await sheet.getByRole('button', { name: 'Send' }).click()
  await expect(phone.getByText('Sent to the office and the client.')).toBeVisible()

  // --- the receiver: sees the code and the delay, never a price
  const rctx = await browser.newContext({ viewport: { width: 412, height: 860 } })
  const receiver = await rctx.newPage()
  await receiver.goto(new URL(receiverUrl).pathname) // the address is built from APP_BASE_URL; the test serves its own copy
  await expect(receiver.getByRole('heading', { name: /on its way to you/ })).toBeVisible()
  const codeText = (await receiver.getByRole('region', { name: 'Your delivery code' }).locator('p').nth(0).textContent())!.trim()
  expect(codeText).toMatch(/^\d{4}$/)
  await expect(receiver.getByText('Delay reported')).toBeVisible()
  await expect(receiver.getByText('Heavy traffic')).toBeVisible()
  await expect(receiver.getByText('Freight')).toHaveCount(0)
  await shot(receiver, 'shipment-receiver-page')

  // --- the driver hands over: a wrong code is refused, the right one is accepted, then the photo
  await phone.getByRole('button', { name: /I have reached/ }).click() // the truck is at the door: the receiver is told to keep the code ready
  await phone.getByRole('button', { name: /Goods reached/ }).click()
  const handover = phone.getByRole('dialog', { name: 'Goods reached' })
  const wrong = codeText === '0000' ? '1111' : '0000'
  await handover.getByLabel("Receiver's 4-digit code").fill(wrong)
  await handover.getByRole('button', { name: 'Confirm delivery' }).click()
  await expect(handover.getByRole('alert')).toContainText('not right')
  await handover.getByLabel("Receiver's 4-digit code").fill(codeText)
  await handover.getByLabel('Something was short or damaged').check()
  await handover.getByLabel('What was short or damaged?').fill('2 bales wet')
  await handover.getByRole('button', { name: 'Confirm delivery' }).click()
  await expect(phone.getByRole('link', { name: /POD/ })).toBeVisible() // the photo comes after the code
  await shot(phone, 'driver-after-code')

  // --- the client sees their page, in Hindi too; the receiver's code is gone
  const cctx = await browser.newContext({ viewport: { width: 412, height: 860 } })
  const cl = await cctx.newPage()
  await cl.goto(new URL(clientUrl).pathname)
  await expect(cl.getByRole('heading', { name: 'Your shipment' })).toBeVisible()
  await expect(cl.getByText('₹31,000')).toBeVisible()
  await expect(cl.getByText('shortage or damage was noted', { exact: false })).toBeVisible()
  await expect(cl.getByRole('region', { name: 'Your delivery code' })).toHaveCount(0)
  await cl.getByLabel('Language').selectOption('hi')
  await expect(cl.getByRole('heading', { name: 'आपकी खेप' })).toBeVisible()
  await shot(cl, 'shipment-client-page')
  await receiver.reload()
  await expect(receiver.getByRole('region', { name: 'Your delivery code' })).toHaveCount(0)
  await expect(receiver.getByText(/Delivered on/)).toBeVisible()

  // --- the office sees every step, and the old addresses can be retired
  await page.reload()
  await page.getByRole('button', { name: `Journey ${code}` }).click()
  const again = page.getByRole('dialog', { name: 'Shipment' })
  for (const step of ['Trip booked', 'Loaded', 'On the road', 'Delay reported', 'Reached the delivery point', 'Delivered', 'Shortage or damage noted']) {
    await expect(again.getByText(step).first()).toBeVisible()
  }
  await again.getByRole('button', { name: /Stop every shared address/ }).click()
  await expect(again.getByRole('status')).toContainText('no longer work')
  await cl.reload()
  await expect(cl.getByText('यह लिंक सही नहीं है')).toBeVisible() // still in Hindi: the visitor's choice is remembered

  await ctx.close(); await rctx.close(); await cctx.close()
  await noErrors()
})
