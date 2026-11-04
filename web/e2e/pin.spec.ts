import { expect, test } from '@playwright/test'
import { login, shot } from './helpers'

test('office resets a forgotten driver PIN; the driver must choose a new one, then signs in with it', async ({ page }) => {
  // --- office
  await login(page, 'ops@cargoone.dev')
  await page.getByRole('link', { name: 'Drivers' }).click()
  const row = page.locator('tr', { hasText: 'PIN Test Driver' })
  await row.getByRole('button', { name: 'Reset PIN' }).click()
  await shot(page, 'drivers-reset-confirm')
  await page.getByRole('dialog', { name: 'Reset PIN' }).getByRole('button', { name: 'Reset PIN' }).click()
  const pin = (await page.getByLabel('Temporary PIN digits').textContent())!.trim()
  expect(pin).toMatch(/^\d{6}$/)
  await shot(page, 'drivers-temporary-pin')
  await page.getByRole('button', { name: 'Close' }).click()
  await expect(row).toContainText('temporary PIN')
  await page.getByRole('button', { name: 'Sign out' }).click()

  // --- the old PIN no longer works
  await login(page, '9000000077', '4821')
  await expect(page.getByRole('alert')).toBeVisible()

  // --- temporary PIN: signs in, but is sent straight to choose a PIN
  await page.getByLabel('Email or phone').fill('9000000077')
  await page.getByLabel('Password or PIN').fill(pin)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/driver\/pin$/)
  await page.goto('/driver') // cannot skip it
  await expect(page).toHaveURL(/\/driver\/pin$/)

  await page.getByLabel('Current PIN').fill(pin)
  await page.getByLabel('New PIN', { exact: true }).fill('1234')
  await page.getByLabel('New PIN again').fill('1234')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByRole('alert')).toContainText('easy one')
  await shot(page, 'driver-pin-screen')

  await page.getByLabel('New PIN', { exact: true }).fill('730194')
  await page.getByLabel('New PIN again').fill('730194')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page).toHaveURL(/\/driver$/)
  await page.getByRole('button', { name: 'Sign out' }).click()

  await login(page, '9000000077', '730194')
  await expect(page).toHaveURL(/\/driver$/)
})
