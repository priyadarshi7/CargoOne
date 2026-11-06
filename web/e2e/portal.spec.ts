import { expect, test } from '@playwright/test'
import { failOnBrowserErrors, login, shot } from './helpers'

test('a client gets its own login, asks for a truck, and accepts the quote online before the office books it', async ({ page, browser }) => {
  test.setTimeout(120_000)
  const noErrors = failOnBrowserErrors(page)
  const email = `rekha${Date.now()}@client.example`

  // --- the ops head makes a login for a person at Company D
  await login(page, 'ops@cargoone.dev')
  await expect(page).toHaveURL(/\/office/)
  await page.goto('/office/setup?tab=clients')
  await page.locator('tr', { hasText: 'Company D' }).getByRole('button', { name: 'Logins' }).click()
  const logins = page.getByRole('dialog', { name: /Logins for Company D/ })
  await logins.getByLabel('Name').fill('Rekha Shah')
  await logins.getByLabel('Email').fill(email)
  await logins.getByRole('button', { name: 'Add a login' }).click()
  const shown = logins.getByRole('status')
  await expect(shown).toContainText('shown only once')
  const temp = (await shown.locator('b').textContent())!.trim()
  await shot(page, 'setup-client-logins')

  // --- the client signs in: the temporary password must be replaced first
  const cctx = await browser.newContext({ viewport: { width: 1100, height: 800 } })
  const cl = await cctx.newPage()
  await login(cl, email, temp)
  await expect(cl).toHaveURL(/\/portal\/account/)
  await cl.getByLabel('Current password').fill(temp)
  await cl.getByLabel('New password', { exact: true }).fill('Rekha-Portal-2026')
  await cl.getByLabel('New password again').fill('Rekha-Portal-2026')
  await cl.getByRole('button', { name: 'Change password' }).click()
  await expect(cl.getByRole('status')).toContainText('Password changed')
  await cl.getByRole('link', { name: 'Shipments' }).click()
  await expect(cl.getByRole('heading', { name: 'Your shipments' })).toBeVisible()
  await expect(cl.getByText('Company D').first()).toBeVisible()
  await cl.goto('/office') // not theirs: they are sent back to their own home
  await expect(cl).toHaveURL(/\/portal/)

  // --- they ask for a truck from their login: no company details to type
  await cl.getByRole('link', { name: 'Ask for a truck' }).first().click()
  await cl.getByLabel('Pickup location').fill('Chhatrapati Sambhajinagar')
  await cl.getByLabel('Delivery location').fill('Solapur')
  await cl.getByLabel('Material').fill('Cotton bales')
  await cl.getByLabel('Mobile number').fill('9876509876') // Company D has no phone saved, so the form asks
  await cl.getByLabel('Pickup date').fill(new Date(Date.now() + 4 * 86_400_000).toISOString().slice(0, 10))
  await cl.getByRole('button', { name: 'Send request' }).click()
  await expect(cl).toHaveURL(/\/request\/REQ-/)
  const statusPath = new URL(cl.url()).pathname
  expect(statusPath).toMatch(/^\/request\/REQ-/)

  // --- ops sees it as Company D's own request, accepts it with a quote
  await page.goto('/office/requests')
  const row = page.locator('li', { hasText: 'Solapur' }).filter({ hasText: 'Company D' }).first()
  await row.getByRole('button', { name: 'Accept', exact: true }).click()
  const accept = page.getByRole('dialog', { name: /Accept/ })
  await expect(accept.getByLabel('Client')).toHaveValue(/.+/) // Company D is already chosen
  await accept.getByLabel('Quoted freight in ₹ (optional)').fill('41500')
  await accept.getByRole('button', { name: 'Accept', exact: true }).click()
  await expect(row.getByText("Waiting for the client's answer to the quote")).toBeVisible()
  await expect(row.getByRole('button', { name: 'Book a trip' })).toHaveCount(0) // not before the client says yes

  // --- the client answers on their own page
  await cl.reload()
  await expect(cl.getByText('₹41,500').first()).toBeVisible()
  await shot(cl, 'request-quote-ask')
  await cl.getByRole('button', { name: 'Accept the quote' }).click()
  await expect(cl.getByText(/office will now arrange the truck/)).toBeVisible()

  // --- now the office can book, with the quote as the freight
  await page.reload()
  const again = page.locator('li', { hasText: 'Solapur' }).filter({ hasText: 'Company D' }).first()
  await expect(again.getByText('Client accepted the quote online')).toBeVisible()
  await again.getByRole('button', { name: 'Book a trip' }).click()
  const trip = page.getByRole('dialog', { name: 'New trip' })
  await expect(trip.getByLabel('Freight (₹)')).toHaveValue('41500')

  await cctx.close()
  await noErrors()
})
