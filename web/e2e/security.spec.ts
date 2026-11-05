import { expect, test } from '@playwright/test'
import { login, PASSWORD, shot } from './helpers'

test('five wrong passwords lock the account with a clear message', async ({ page }) => {
  await page.goto('/login')
  for (let i = 0; i < 5; i++) {
    await page.getByLabel('Email or phone').fill('locktest@cargoone.dev')
    await page.getByLabel('Password or PIN').fill(`wrong-${i}-pass`)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('alert')).toBeVisible()
  }
  await page.getByLabel('Password or PIN').fill(PASSWORD) // even the right one is refused now
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('alert')).toContainText('Try again in')
  await shot(page, 'login-locked')
})

test('changing the password works, rejects weak ones, and the new one signs in', async ({ page }) => {
  await login(page, 'pwchange@cargoone.dev')
  await page.getByRole('link', { name: 'Account' }).click()
  await expect(page.getByRole('heading', { name: 'Account' })).toBeVisible()

  await page.getByLabel('Current password').fill(PASSWORD)
  await page.getByLabel('New password', { exact: true }).fill('short1')
  await page.getByLabel('New password again').fill('short1')
  await page.getByRole('button', { name: 'Change password' }).click()
  await expect(page.getByRole('alert')).toContainText('at least 10')

  await page.getByLabel('New password', { exact: true }).fill('a much better passphrase')
  await page.getByLabel('New password again').fill('a much better passphrase')
  await page.getByRole('button', { name: 'Change password' }).click()
  await expect(page.getByRole('status')).toContainText('Password changed')
  await shot(page, 'account-changed')

  await page.getByRole('button', { name: 'Sign out' }).click()
  await login(page, 'pwchange@cargoone.dev', 'a much better passphrase')
  await expect(page.getByRole('link', { name: 'Trips' })).toBeVisible()
})
