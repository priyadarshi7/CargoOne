import { expect, test } from '@playwright/test'
import { failOnBrowserErrors, login, shot } from './helpers'

/** The whole money hand-off: billing sends the invoice (an email with a private link), the client opens it and says they paid, billing checks the bank and confirms. */
test('billing sends an invoice, the client opens it on the private page and says it paid, and billing confirms', async ({ page, browser }) => {
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
  await card.getByRole('button', { name: 'I have paid' }).click()
  await card.getByLabel(/Bank reference/).fill('UTR-E2E-0001')
  await shot(client, 'client-invoice-pay')
  await card.getByRole('button', { name: 'Tell billing' }).click()
  await expect(card).toContainText('Waiting for billing to check')
  await expect(card).toContainText('To pay') // nothing changes until billing confirms

  // billing sees it waiting, and confirms
  await page.getByRole('link', { name: 'Billing' }).click()
  await page.getByRole('button', { name: /Payments to check/ }).click()
  const claim = page.locator('li', { hasText: 'UTR-E2E-0001' })
  await expect(claim).toContainText('Company B')
  await shot(page, 'billing-claims')
  await claim.getByRole('button', { name: 'Confirm payment' }).click()
  await expect(page.getByText('No payments are waiting to be checked.')).toBeVisible()

  // the client's page now shows it paid
  await client.reload()
  await expect(client.getByRole('region', { name: /^Invoice / })).toContainText('Paid')
  await expect(client.getByRole('region', { name: /^Invoice / })).toContainText('Confirmed by billing')
  await ctx.close()
  await clientErrors()
  await noErrors()
})
