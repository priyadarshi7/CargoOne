import { expect, test } from '@playwright/test'
import { login, shot } from './helpers'

test('ops home is the operations desk, with the performance figures one click away', async ({ page }) => {
  await login(page, 'ops@cargoone.dev')
  await expect(page.getByRole('heading', { name: 'Operations desk' })).toBeVisible()
  await expect(page.getByText('Companies waiting for a reply')).toBeVisible()
  await expect(page.getByRole('link', { name: 'Plan a trip' })).toBeVisible()
  await shot(page, 'desk-ops')
  await page.getByRole('link', { name: 'Performance' }).click()
  await expect(page).toHaveURL(/\/office\/performance$/)
  await expect(page.getByText('PODs in system within 24 h', { exact: false }).first()).toBeVisible()
})

test('billing home is the billing desk, with its own numbers and shortcuts', async ({ page }) => {
  await login(page, 'billing@cargoone.dev')
  await expect(page.getByRole('heading', { name: 'Billing desk' })).toBeVisible()
  await expect(page.getByText('Ready to invoice', { exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Create an invoice' })).toBeVisible()
  await expect(page.getByText('Companies waiting for a reply')).toHaveCount(0)
  await shot(page, 'desk-billing')
})

test('the MD keeps the performance dashboard as home and sees no freight total on a desk', async ({ page }) => {
  await login(page, 'md@cargoone.dev')
  await expect(page.getByRole('heading', { name: 'Business overview' })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Planning' })).toHaveCount(0)
  await page.goto('/office/performance')
  await expect(page.getByRole('heading', { name: 'Business overview' })).toBeVisible()
})
