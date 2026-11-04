import { expect, test } from '@playwright/test'
import { login, shot } from './helpers'

test('unauthenticated visitors are sent to login', async ({ page }) => {
  await page.goto('/office')
  await expect(page).toHaveURL(/\/login$/)
  await shot(page, 'login')
})

test('wrong password shows a clear error and stays on login', async ({ page }) => {
  await login(page, 'ops@cargoone.dev', 'not-the-password')
  await expect(page.getByRole('alert')).toHaveText('Wrong login or password.')
  await expect(page).toHaveURL(/\/login$/)
})

test('each role lands on its own home', async ({ page }) => {
  await login(page, 'ops@cargoone.dev')
  await expect(page.getByRole('heading', { name: 'Operations' })).toBeVisible()
  await page.getByRole('button', { name: 'Sign out' }).click()

  await login(page, 'md@cargoone.dev')
  await expect(page.getByRole('heading', { name: 'Business overview' })).toBeVisible()
  await page.getByRole('button', { name: 'Sign out' }).click()

  await login(page, 'billing@cargoone.dev')
  await expect(page.getByRole('heading', { name: 'Review queue' })).toBeVisible()
})

test('a billing executive cannot open the executive dashboard data', async ({ page }) => {
  await login(page, 'billing@cargoone.dev')
  await expect(page.getByRole('heading', { name: 'Review queue' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Dashboard' })).toHaveCount(0)
})

test('a driver is kept out of the office screens', async ({ page }) => {
  await login(page, '9000000001', '1234')
  await expect(page).toHaveURL(/\/driver$/)
  await page.goto('/office')
  await expect(page).toHaveURL(/\/driver$/)
})
