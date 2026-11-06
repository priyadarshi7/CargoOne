import { expect, test, type Page } from '@playwright/test'
import { login, shot } from './helpers'

const tag = () => String(Date.now()).slice(-8)
const inDays = (n: number) => new Date(Date.now() + n * 86_400_000).toISOString().slice(0, 10)

async function ask(page: Page, company: string, phone: string, destination: string) {
  await page.goto('/request')
  await page.getByLabel('Company name').fill(company)
  await page.getByLabel('Your name').fill('Anil Mehta')
  await page.getByLabel('Mobile number').fill(phone)
  await page.getByLabel('Pickup location').fill('Chhatrapati Sambhajinagar')
  await page.getByLabel('Delivery location').fill(destination)
  await page.getByLabel('Material').fill('Steel coils')
  await page.getByLabel('Weight in tonnes (optional)').fill('15')
  await page.getByLabel('Pickup date').fill(inDays(10))
  await page.getByLabel(/I agree that CargoOne may contact me/).check()
  await page.getByRole('button', { name: 'Send request' }).click()
  await expect(page.getByRole('heading', { name: 'Request received' })).toBeVisible()
}

test('a company asks for transport, ops onboards it and books the trip, and the company sees every step', async ({ page, browser }) => {
  const id = tag()
  const company = `Acme Steel ${id}`
  const visitor = await (await browser.newContext({ viewport: { width: 412, height: 860 } })).newPage() // nobody is signed in
  await ask(visitor, company, `97${id}`, 'Nagpur')
  await shot(visitor, 'request-received')
  await visitor.getByRole('link', { name: 'Open my request page' }).click()
  await expect(visitor.getByRole('status')).toContainText('Received. Our team is reviewing it.')
  await expect(visitor.getByText(/Nagpur/)).toBeVisible()
  await shot(visitor, 'request-status-new')
  const statusUrl = visitor.url()

  // ops sees it on the dashboard and in the list, and accepts it: the company becomes a client in the same step
  await login(page, 'ops@cargoone.dev')
  await expect(page.getByRole('region', { name: 'Needs attention' })).toContainText('new transport requests')
  await page.getByRole('link', { name: 'Requests' }).click()
  const row = page.locator('li', { hasText: company })
  await expect(row).toContainText('New')
  await shot(page, 'requests-list')
  await row.getByRole('button', { name: 'Accept' }).click()
  const accept = page.getByRole('dialog')
  await accept.getByLabel('Quoted freight in ₹ (optional)').fill('38000')
  await accept.getByLabel('Message for the requester (optional)').fill('A 32 ft container will come')
  await accept.getByRole('button', { name: 'Accept' }).click()
  await expect(row).toContainText('Accepted')
  await visitor.reload()
  await expect(visitor.getByRole('status')).toContainText('Accepted')
  await expect(visitor.getByText('A 32 ft container will come')).toBeVisible()
  await expect(visitor.getByText('₹38,000').first()).toBeVisible()
  await visitor.getByRole('button', { name: 'Accept the quote' }).click() // the trip can only be booked after the company says yes
  await expect(visitor.getByText(/office will now arrange the truck/)).toBeVisible()

  // the company is now a client in Setup, with its contact details
  await page.goto('/office/setup?tab=clients')
  await expect(page.locator('tr', { hasText: company })).toContainText('Anil Mehta')

  // booking opens the new-trip form with the request already filled in
  await page.goto('/office/requests')
  await page.locator('li', { hasText: company }).getByRole('button', { name: 'Book a trip' }).click()
  const d = page.getByRole('dialog', { name: 'New trip' })
  await expect(d.getByLabel('To', { exact: true })).toHaveValue('Nagpur')
  await expect(d.getByLabel('Goods')).toHaveValue('Steel coils')
  await d.getByLabel('Freight (₹)').fill('38000')
  await d.getByLabel('E-way bill (12 digits)').fill(String(Math.floor(Math.random() * 9e11) + 1e11))
  await d.getByLabel('E-way bill valid until').fill(new Date(Date.now() + 100 * 86_400_000).toISOString().slice(0, 16))
  await d.getByRole('button', { name: 'Create trip' }).click()
  await expect(d.getByLabel('LR number')).toHaveText(/^LR\//)
  await d.getByRole('button', { name: 'Done' }).click()

  await visitor.reload()
  await expect(visitor.getByRole('status')).toContainText(/Booked as trip TRP-\d+/)
  await shot(visitor, 'request-status-booked')
  expect(statusUrl).toContain('/request/REQ-')
  await visitor.context().close()
})

test('a request can be declined with a reason the company reads; a wrong link shows nothing', async ({ page, browser }) => {
  const id = tag()
  const company = `Declined Co ${id}`
  const visitor = await (await browser.newContext()).newPage()
  await ask(visitor, company, `96${id}`, 'Goa')
  await visitor.getByRole('link', { name: 'Open my request page' }).click()

  await login(page, 'ops@cargoone.dev')
  await expect(page.getByRole('link', { name: 'Trips' })).toBeVisible()
  await page.goto('/office/requests')
  await page.locator('li', { hasText: company }).getByRole('button', { name: 'Decline' }).click()
  await page.getByLabel(/Reason/).fill('We do not run to Goa')
  await page.getByRole('dialog').getByRole('button', { name: 'Decline' }).click()
  await expect(page.locator('li', { hasText: company })).toHaveCount(0) // leaves the open list
  await page.getByRole('tab', { name: 'All' }).click()
  await expect(page.locator('li', { hasText: company })).toContainText('Declined')

  await visitor.reload()
  await expect(visitor.getByRole('status')).toContainText('We could not take this one up.')
  await expect(visitor.getByText('We do not run to Goa')).toBeVisible()

  await visitor.goto('/request/REQ-1.' + 'x'.repeat(30))
  await expect(visitor.getByRole('alert')).toContainText('This link is not valid')
  await visitor.context().close()
})

test('billing can read requests but not decide; the request page is translated', async ({ page }) => {
  await login(page, 'billing@cargoone.dev')
  await expect(page.getByRole('link', { name: 'Trips' })).toBeVisible()
  await page.goto('/office/requests')
  await expect(page.getByRole('heading', { name: 'Transport requests' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Accept' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Sign out' }).click()
  await page.goto('/request')
  await page.getByLabel('Language').selectOption('hi')
  await expect(page.getByRole('heading', { name: 'ट्रांसपोर्ट का अनुरोध करें' })).toBeVisible()
})

test('when a client says no to the quote the office sees it with the reason, and can send a new price', async ({ page, browser }) => {
  test.setTimeout(120_000)
  const id = tag()
  const company = `Decline Steel ${id}`
  const visitor = await (await browser.newContext({ viewport: { width: 412, height: 860 } })).newPage()
  await ask(visitor, company, `96${id}`, 'Solapur')
  await visitor.getByRole('link', { name: 'Open my request page' }).click()
  const statusPath = new URL(visitor.url()).pathname

  await login(page, 'ops@cargoone.dev')
  await expect(page).toHaveURL(/\/office/)
  await page.goto('/office/requests')
  await page.locator('li', { hasText: company }).getByRole('button', { name: 'Accept', exact: true }).click()
  const accept = page.getByRole('dialog')
  await accept.getByLabel('Quoted freight in ₹ (optional)').fill('52000')
  await accept.getByRole('button', { name: 'Accept', exact: true }).click()

  await visitor.goto(statusPath)
  await visitor.getByLabel('Reason (optional)').fill('Another transporter is cheaper')
  await visitor.getByRole('button', { name: 'No, thank you' }).click()
  await expect(visitor.getByText('Declined').first()).toBeVisible()

  // the office sees it without looking for it: on the dashboard, on the sidebar, and on the request itself
  await page.goto('/office')
  await expect(page.getByRole('region', { name: 'Needs attention' })).toContainText('said no to the quote')
  await page.goto('/office/requests')
  const row = page.locator('li', { hasText: company })
  await expect(row).toContainText('The client said no to the quote')
  await expect(row).toContainText('Another transporter is cheaper')
  await shot(page, 'request-client-said-no')

  // a new price asks the client again
  await row.getByRole('button', { name: 'Send a new quote' }).click()
  const dialog = page.getByRole('dialog')
  await dialog.getByLabel('Quoted freight in ₹ (optional)').fill('46000')
  await dialog.getByRole('button', { name: 'Send the new quote' }).click()
  await expect(row).toContainText('Waiting for the client')
  await visitor.reload()
  await expect(visitor.getByText('₹46,000').first()).toBeVisible()
  await expect(visitor.getByRole('button', { name: 'Accept the quote' })).toBeVisible()
})
