import { expect, test } from '@playwright/test'
import { login } from './helpers'

// A screen that is already open shows a change made by someone else, with no reload.
test('a new transport request appears on the ops screen by itself', async ({ page, browser }) => {
  const id = String(Date.now()).slice(-8)
  const company = `Live Cement ${id}`
  await login(page, 'ops@cargoone.dev')
  await page.getByRole('link', { name: 'Requests' }).click()
  await expect(page.getByRole('heading', { name: 'Transport requests' })).toBeVisible()
  await expect(page.locator('li', { hasText: company })).toHaveCount(0)

  const visitor = await (await browser.newContext()).newPage()
  const inTen = new Date(Date.now() + 10 * 86_400_000).toISOString().slice(0, 10)
  await visitor.goto('/request')
  await visitor.getByLabel('Company name').fill(company)
  await visitor.getByLabel('Your name').fill('Rita Shah')
  await visitor.getByLabel('Mobile number').fill(`96${id}`)
  await visitor.getByLabel('Pickup location').fill('Chhatrapati Sambhajinagar')
  await visitor.getByLabel('Delivery location').fill('Pune')
  await visitor.getByLabel('Material').fill('Cement')
  await visitor.getByLabel('Weight in tonnes (optional)').fill('20')
  await visitor.getByLabel('Pickup date').fill(inTen)
  await visitor.getByLabel(/I agree that CargoOne may contact me/).check()
  await visitor.getByRole('button', { name: 'Send request' }).click()
  await expect(visitor.getByRole('heading', { name: 'Request received' })).toBeVisible()

  await expect(page.locator('li', { hasText: company })).toBeVisible({ timeout: 10_000 }) // no page.reload() anywhere
})
