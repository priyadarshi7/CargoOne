import { expect, test } from '@playwright/test'
import { login, shot } from './helpers'

test('a visitor sees the landing page and can start a request', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Move the load')
  await expect(page.getByRole('heading', { name: 'Three steps, no phone tag.' })).toBeVisible()
  await page.waitForTimeout(3500) // let the route finish drawing before the picture
  await shot(page, 'landing')
  await page.getByRole('main').getByRole('link', { name: 'Request transport' }).first().click()
  await expect(page).toHaveURL(/\/request$/)
  await expect(page.getByRole('heading', { name: 'Request transport' })).toBeVisible()
})

test('the landing page offers sign in, and the language switch changes the text', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Language').selectOption('hi')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('माल भेजिए')
  await page.getByLabel('Language').selectOption('en')
  await page.getByRole('link', { name: 'Staff and driver sign in' }).first().click()
  await expect(page).toHaveURL(/\/login$/)
})

test('a signed-in person skips the landing page', async ({ page }) => {
  await login(page, 'ops@cargoone.dev')
  await expect(page.getByRole('link', { name: 'Trips' })).toBeVisible()
  await page.goto('/')
  await expect(page).toHaveURL(/\/office$/)
})

test('the landing page fits a phone without sideways scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 })
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  const wide = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
  expect(wide).toBe(false)
  await shot(page, 'landing-mobile')
})

test('the landing page keeps the scene in dark mode', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  await shot(page, 'landing-dark')
})
