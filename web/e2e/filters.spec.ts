import { expect, test } from '@playwright/test'
import { login } from './helpers'

test('ops can narrow the trips list by search and status, and clear it again', async ({ page }) => {
  await login(page, 'ops@cargoone.dev')
  await page.waitForURL(/\/office/)
  await page.goto('/office/trips')
  const rows = page.locator('tbody tr')
  await expect(rows.first()).toBeVisible()
  const all = await rows.count()
  const code = (await rows.first().locator('td').first().locator('button').first().innerText()).trim()

  const search = page.getByRole('searchbox')
  await search.fill(code.toLowerCase())
  await expect(rows).toHaveCount(1)
  await expect(page).toHaveURL(/[?&]q=/)
  await expect(page.getByText(`1 of ${all}`)).toBeVisible()

  await search.fill('zzz no such trip')
  await expect(page.getByText('Nothing matches these filters.')).toBeVisible()
  await page.getByRole('button', { name: 'Clear filters' }).first().click()
  await expect(rows).toHaveCount(all)
  await expect(page).not.toHaveURL(/[?&]q=/)

  await page.getByRole('button', { name: /Needs review/ }).first().click() // the stat card is a filter too
  await expect(page.getByLabel('Status')).toHaveValue('needs_review')
  await page.goto('/office/trips?pod=pending') // the desk links here already filtered
  await expect(page.getByLabel('Status')).toHaveValue('pending')
})

test('the setup lists can be searched', async ({ page }) => {
  await login(page, 'admin@cargoone.dev')
  await page.waitForURL(/\/office/)
  await page.goto('/office/setup?tab=drivers')
  const search = page.getByRole('searchbox')
  await expect(search).toBeVisible()
  await search.fill('zzz nobody')
  await expect(page.getByText('Nothing matches these filters.')).toBeVisible()
  await page.getByRole('tab', { name: /Trucks/ }).click()
  await expect(page.getByRole('searchbox')).toHaveValue('') // a new tab starts unfiltered
})
