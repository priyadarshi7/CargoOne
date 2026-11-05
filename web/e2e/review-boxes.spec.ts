import { expect, test } from '@playwright/test'
import { login, shot } from './helpers'

// The local reader returns where it found each field. This test feeds Review a response with boxes (no model needed)
// and checks what the reviewer sees: a tagged box for each found field, "not found" for the rest, and the link both ways.
const BOXES = [
  { field: 'lr_no', x: 0.1, y: 0.12, w: 0.4, h: 0.05, text: 'LR No: LR-88141', conf: 0.95, source: 'ocr' },
  { field: 'remarks', x: 0.1, y: 0.7, w: 0.4, h: 0.05, text: 'short by 6 cartons', conf: 0.8, source: 'ocr' },
  { field: 'stamp', x: 0.6, y: 0.75, w: 0.3, h: 0.15, source: 'vlm' },
]

test('review shows what the AI found as tagged boxes on the photo, linked with the form', async ({ page }) => {
  await page.route(/\/api\/review\/[0-9a-f-]{36}$/, async (route) => {
    const res = await route.fetch()
    const body = await res.json()
    await route.fulfill({ response: res, json: { ...body, ai: { ...body.ai, boxes: BOXES } } })
  })
  await login(page, 'billing@cargoone.dev')
  await expect(page.getByRole('heading', { name: 'Billing desk' })).toBeVisible()
  // open the sample shortage trip's POD directly (other tests may already have approved it out of the queue; its photo is still there)
  const token = await page.evaluate(() => Object.values(localStorage).find((v) => typeof v === 'string' && v.split('.').length === 3) as string)
  const trips = await (await page.request.get('/api/trips', { headers: { Authorization: `Bearer ${token}` } })).json()
  await page.goto(`/office/review/${trips.find((t: { trip_code: string }) => t.trip_code === 'TRP-66141').id}`)
  const img = page.getByRole('img', { name: 'Proof of delivery' })
  await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0)

  // a tagged box for each found field, none for the ones the AI did not find
  await expect(page.getByRole('button', { name: 'LR number: LR No: LR-88141' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Remarks on the paper: short by 6 cartons' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Stamp' })).toHaveCount(2) // the box on the photo and its chip in the list
  await expect(page.getByRole('button', { name: 'Signature' })).toHaveCount(1) // only the chip: nothing was found to draw
  await expect(page.getByRole('button', { name: 'Signature' })).toBeDisabled()

  // the list names what was found and what was not
  const chips = page.getByRole('list').filter({ hasText: 'LR number' }).first()
  await expect(chips.getByTitle('Found on the photo', { exact: true })).toHaveCount(3)
  await expect(chips.getByTitle('Not found on the photo', { exact: true })).toHaveCount(3)

  // placed where the AI said: 10% across, 12% down the photo
  const photo = (await img.boundingBox())!
  const box = (await page.getByRole('button', { name: /^LR number: / }).boundingBox())!
  expect(box.x - photo.x).toBeCloseTo(photo.width * 0.1, -1)
  expect(box.y - photo.y).toBeCloseTo(photo.height * 0.12, -1)

  // focusing a form field lights its box; hovering a box does the same for the form
  await page.getByRole('textbox', { name: 'LR number' }).focus()
  await expect(page.getByRole('button', { name: /^LR number: / })).toHaveClass(/bg-accent\/15/)
  await shot(page, 'review-boxes')

  // the reviewer can hide them
  await page.getByRole('button', { name: 'Show what the AI found' }).first().click()
  await expect(page.getByRole('button', { name: /^LR number: / })).toHaveCount(0)
})
