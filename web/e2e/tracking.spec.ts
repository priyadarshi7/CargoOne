import { devices, expect, test } from '@playwright/test'
import { failOnBrowserErrors, login, shot } from './helpers'

test.use({ geolocation: { latitude: 19.9101, longitude: 75.3302 }, permissions: ['geolocation'] })

test('driver agrees to share location, ops sees the truck on the live map, a client gets a tracking link', async ({ page, browser }) => {
  // --- the driver's phone
  const ctx = await browser.newContext({ ...devices['Pixel 7'], geolocation: { latitude: 19.9101, longitude: 75.3302 }, permissions: ['geolocation'] })
  const phone = await ctx.newPage()
  const phoneErrors = failOnBrowserErrors(phone)
  await login(phone, '9000000099', '4821')
  const consent = phone.getByRole('region', { name: 'Share your location during trips?' })
  await expect(consent).toBeVisible()
  await shot(phone, 'driver-location-consent')
  await consent.getByRole('button', { name: 'Allow' }).click()
  await expect(phone.getByRole('status', { name: 'Location on' })).toBeVisible({ timeout: 20_000 }) // first fix has reached the server
  await shot(phone, 'driver-location-on')

  // --- ops: the live map
  const noErrors = failOnBrowserErrors(page)
  await login(page, 'ops@cargoone.dev')
  await page.getByRole('link', { name: 'Live map' }).click()
  await expect(page.getByRole('heading', { name: 'Live map' })).toBeVisible()
  const row = page.locator('li', { hasText: 'TRP-E2E-GPS' }).getByRole('button', { name: /TRP-E2E-GPS/ }).first()
  await expect(row).toBeVisible()
  await expect(page.locator('li', { hasText: 'TRP-E2E-GPS' })).toContainText('Moving')
  await expect(page.locator('.map-pin').first()).toBeVisible()
  await row.click()
  await page.waitForTimeout(800) // map fly-to
  await shot(page, 'live-map')

  // --- share with a client
  await page.locator('li', { hasText: 'TRP-E2E-GPS' }).getByRole('button', { name: 'Share tracking' }).click()
  const dialog = page.getByRole('dialog', { name: 'Share live tracking' })
  await dialog.getByRole('button', { name: 'Create tracking link' }).click()
  const url = await dialog.getByLabel('Share live tracking').inputValue()
  expect(url).toMatch(/\/t\/[\w-]{40,}$/)

  const clientCtx = await browser.newContext({ ...devices['Pixel 7'] })
  const client = await clientCtx.newPage()
  const clientErrors = failOnBrowserErrors(client)
  await client.goto(new URL(url).pathname)
  await expect(client.getByRole('heading', { name: 'Where is my load?' })).toBeVisible()
  await expect(client.getByText('Nanded')).toBeVisible()
  await expect(client.getByText(/position is approximate/)).toBeVisible()
  await expect(client.getByText(/GPS Test Driver/)).toHaveCount(0) // never the driver's name
  await shot(client, 'client-tracking')
  await dialog.getByRole('button', { name: 'Revoke link' }).click()
  await client.reload()
  await expect(client.getByText(/expired/)).toBeVisible()

  await noErrors(); await phoneErrors(); await clientErrors()
  await ctx.close(); await clientCtx.close()
})

test('billing and drivers cannot open the live map; the MD can', async ({ page }) => {
  await login(page, 'billing@cargoone.dev')
  await expect(page.getByRole('link', { name: 'Trips' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Live map' })).toHaveCount(0)
  await page.goto('/office/live')
  await expect(page).not.toHaveURL(/\/office\/live/)
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible()
  await page.getByRole('button', { name: 'Sign out' }).click()
  await login(page, 'md@cargoone.dev')
  await page.getByRole('link', { name: 'Live map' }).click()
  await expect(page.getByRole('heading', { name: 'Live map' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Share tracking' })).toHaveCount(0) // MD watches; ops shares
})
