import { devices, expect, test } from '@playwright/test'
import { failOnBrowserErrors, login, shot } from './helpers'

test('office shares a verified POD; the client opens it with no login and the access log counts the view', async ({ page, browser }) => {
  await login(page, 'billing@cargoone.dev')
  await page.getByRole('link', { name: 'Trips' }).click()

  // only verified/billed PODs can be shared
  await expect(page.locator('tr', { hasText: 'TRP-E2E-2' }).getByRole('button', { name: 'Share' })).toHaveCount(0)
  await page.locator('tr', { hasText: 'TRP-66120' }).getByRole('button', { name: 'Share' }).click()

  const dialog = page.getByRole('dialog', { name: 'Share with client' })
  await dialog.getByRole('button', { name: /Create/ }).click()
  const url = await dialog.getByLabel('Client link').inputValue()
  expect(url).toMatch(/\/v\/[\w-]{40,}$/)
  await expect(dialog.getByText('not opened yet')).toBeVisible()

  // the client: a fresh browser, no session
  const ctx = await browser.newContext({ ...devices['Pixel 7'] })
  const client = await ctx.newPage()
  const noErrors = failOnBrowserErrors(client)
  await client.goto(new URL(url).pathname)
  await expect(client.getByRole('heading', { name: 'Proof of delivery' })).toBeVisible()
  await expect(client.getByText('LR-88120')).toBeVisible()
  await expect(client.getByAltText('Signed delivery receipt')).toBeVisible()
  await expect(client.getByText(/38,?500|Freight/)).toHaveCount(0) // no amounts
  await shot(client, 'client-pod-view')
  await noErrors()

  // the office sees that it was opened
  await dialog.getByRole('button', { name: 'Close' }).click()
  await page.locator('tr', { hasText: 'TRP-66120' }).getByRole('button', { name: 'Share' }).click()
  await expect(page.getByRole('dialog', { name: 'Share with client' }).getByText(/opened \d+×/)).toBeVisible()
  await shot(page, 'client-link-access-log')

  // revoking stops it
  await page.getByRole('button', { name: 'Revoke access' }).click()
  await client.reload()
  await expect(client.getByText(/expired/)).toBeVisible()
  await ctx.close()
})
