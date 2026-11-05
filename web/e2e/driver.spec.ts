import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { failOnBrowserErrors, FIXTURE, login, shot } from './helpers'

test.describe.configure({ mode: 'serial' })

test('driver photographs a POD and gets a green "done" screen', async ({ page }) => {
  const noErrors = failOnBrowserErrors(page)
  await login(page, '9000000001', '1234')
  await expect(page).toHaveURL(/\/driver$/)
  await shot(page, 'driver-home')

  // The big button opens the next open trip (the Pune trip waiting for a retake)
  await page.getByRole('link', { name: /POD/ }).click()
  await expect(page).toHaveURL(/\/driver\/trip\//)
  await shot(page, 'driver-capture-ready')

  await page.locator('input[type=file]').setInputFiles(FIXTURE)
  await expect(page.getByLabel('verified')).toBeVisible({ timeout: 20_000 })
  await shot(page, 'driver-result-verified')

  await page.getByRole('link', { name: 'Back' }).click()
  await expect(page).toHaveURL(/\/driver$/)
  await noErrors()
})

test('offline capture is saved on the phone and uploads when the network returns', async ({ page, context }) => {
  await login(page, '9000000001', '1234')
  await page.getByRole('button', { name: 'English' }).click() // this demo driver's own language is Marathi
  await page.getByRole('link', { name: /POD/ }).click()
  await expect(page).toHaveURL(/\/driver\/trip\//)

  await context.setOffline(true)
  await page.locator('input[type=file]').setInputFiles(FIXTURE)
  await expect(page.getByLabel('Saved, waiting for network')).toBeVisible({ timeout: 20_000 })
  await shot(page, 'driver-result-offline')

  await page.getByRole('link', { name: 'Back' }).click()
  await expect(page.getByText(/waiting to send/)).toBeVisible() // pending-upload counter shows the waiting photo

  await context.setOffline(false) // browser fires "online"; the queue drains by itself
  await expect(page.getByText(/waiting to send/)).toHaveCount(0, { timeout: 20_000 })
  await expect(page.getByTitle('Done')).toHaveCount(3) // seeded TRP-66120 + the Pune trip + this offline one
  await shot(page, 'driver-home-after-sync')
})

test('a driver cannot upload to a trip that is not theirs', async ({ page }) => {
  await login(page, '9000000001', '1234')
  await expect(page).toHaveURL(/\/driver$/) // wait until the login finished and the token is stored
  // Unknown / foreign trips answer 404 (not 403), so drivers cannot probe which trips exist.
  const res = await page.request.post('/api/trips/00000000-0000-0000-0000-000000000000/pod', {
    headers: { Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem('cargoone.token'))}` },
    multipart: { client_upload_id: 'e2e-denied-0001', captured_at: new Date().toISOString(), file: { name: 'p.png', mimeType: 'image/png', buffer: Buffer.from('x') } },
  })
  expect(res.status()).toBe(404)
})

test('a blurry photo is caught on the phone before upload; the driver can retake or send it anyway', async ({ page }) => {
  await login(page, '9000000001', '1234')
  await page.getByRole('link', { name: /POD/ }).click()
  await expect(page).toHaveURL(/\/driver\/trip\//)

  const uploads: string[] = []
  page.on('request', (r) => { if (r.method() === 'POST' && /\/pod$/.test(r.url())) uploads.push(r.url()) })
  await page.locator('input[type=file]').setInputFiles(join(import.meta.dirname, 'fixtures', 'pod-blurry.jpg'))
  await expect(page.getByLabel('blurry')).toBeVisible({ timeout: 10_000 })
  await shot(page, 'driver-quality-blurry')
  expect(uploads).toHaveLength(0) // nothing was sent: the driver is asked to retake first

  await page.getByRole('button', { name: /Use this photo|यही फोटो भेजें|हाच फोटो पाठवा/ }).click() // "use anyway" still reaches the server's own AI check
  await expect(page.getByLabel(/verified|retake_requested|review_needed|needs_review|retake/).first()).toBeVisible({ timeout: 20_000 })
  expect(uploads.length).toBeGreaterThan(0)
})
