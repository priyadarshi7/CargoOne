import { expect, test } from '@playwright/test'
import { failOnBrowserErrors, login, shot } from './helpers'

/** The money hand-off: billing sends the invoice (an email with a private link), the client opens it, and what billing records (cash, a transfer) shows there. */
test('billing sends an invoice, the client opens it on the private page, and a payment billing records shows there as paid', async ({ page, browser }) => {
  const noErrors = failOnBrowserErrors(page)

  // the client company gets a billing email, under Setup
  await login(page, 'ops@cargoone.dev')
  await expect(page).toHaveURL(/\/office/)
  await page.goto('/office/setup?tab=clients')
  await page.getByRole('row', { name: /Company B/ }).getByRole('button').last().click()
  await page.getByLabel('Billing email (invoices are sent here)').fill('accounts@company-b.example')
  await page.getByRole('button', { name: /^Save/ }).click()
  await expect(page.getByRole('dialog')).toHaveCount(0)

  // billing makes the invoice for the verified trip and sends it
  await page.context().clearCookies()
  await page.evaluate(() => localStorage.clear())
  await login(page, 'billing@cargoone.dev')
  await expect(page).toHaveURL(/\/office/)
  await page.getByRole('link', { name: 'Billing' }).click()
  const group = page.locator('section', { hasText: 'Company B' }).first()
  await group.getByRole('button', { name: 'Create invoice' }).click()
  const row = page.locator('tr', { hasText: 'Company B' }).first()
  await expect(row).toContainText('Draft')
  await row.getByRole('button', { name: 'Send to client' }).click()
  await expect(page.getByRole('status')).toContainText('was sent to the client')
  await expect(row).toContainText('Sent')
  await shot(page, 'billing-invoice-sent')

  // the private link of that shipment, as the office sees it
  await page.getByRole('link', { name: 'Trips' }).click()
  await page.getByRole('button', { name: 'Journey TRP-66120' }).click()
  const url = await page.getByRole('dialog', { name: 'Shipment' }).getByLabel('Client link').inputValue()

  await page.keyboard.press('Escape')
  // the client: no login, only the private address
  const ctx = await browser.newContext({ viewport: { width: 412, height: 860 } })
  const client = await ctx.newPage()
  const clientErrors = failOnBrowserErrors(client)
  await client.goto(new URL(url).pathname)
  const card = client.getByRole('region', { name: /^Invoice / })
  await expect(card).toContainText('To pay')
  await expect(card.getByRole('button', { name: /View invoice/ })).toBeVisible()
  await expect(card.getByRole('button', { name: /I have paid/ })).toHaveCount(0) // the client does not report payments: billing records what arrived
  await shot(client, 'client-invoice')

  // the client hands over cash; billing records it in the invoice's Payments
  await page.getByRole('link', { name: 'Billing' }).click()
  await page.getByRole('button', { name: /^Invoices/ }).click()
  await row.getByRole('button', { name: 'Payments' }).click()
  const pay = page.getByRole('dialog', { name: /Payments for CO\// })
  const balance = Number((await pay.getByText(/^Balance Rs/).textContent())!.replace(/[^\d.]/g, ''))
  await pay.getByLabel('Amount received (Rs)').fill(String(balance))
  await pay.getByLabel(/Reference/).fill('Cash, receipt 12')
  await pay.getByRole('button', { name: 'Record payment' }).click()
  await page.keyboard.press('Escape')

  // the client's page now shows it paid
  await client.reload()
  await expect(client.getByRole('region', { name: /^Invoice / })).toContainText('Paid')
  await expect(client.getByRole('region', { name: /^Invoice / })).toContainText('Cash, receipt 12')
  await ctx.close()
  await clientErrors()
  await noErrors()
})
