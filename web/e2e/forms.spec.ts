import { expect, test } from '@playwright/test'
import { shot } from './helpers'

// What the place search returns is replaced here, so this checks the screen, not the internet. The server side is covered by api/tests/test_places.py.
const PLACES = [
  { label: 'Waluj MIDC, Chhatrapati Sambhajinagar, Maharashtra', name: 'Waluj MIDC', detail: 'Chhatrapati Sambhajinagar, Maharashtra', lat: 19.8601, lng: 75.2145 },
  { label: 'Waluj Gaon, Chhatrapati Sambhajinagar, Maharashtra', name: 'Waluj Gaon', detail: 'Chhatrapati Sambhajinagar, Maharashtra', lat: 19.8512, lng: 75.2301 },
]

test('the request form suggests real places, keeps the picked position, and checks the mobile number as you type', async ({ page }) => {
  let asked = 0
  await page.route('**/api/places/search*', (route) => { asked++; return route.fulfill({ json: PLACES }) })
  let sent: Record<string, unknown> | null = null
  await page.route('**/api/public/requests', (route) => { sent = route.request().postDataJSON(); return route.fulfill({ status: 201, json: { reference: 'REQ-9999', status_url: '' } }) })
  await page.goto('/request')

  // phone: a fixed +91, and the number is judged as it is typed
  const phone = page.getByLabel('Mobile number')
  await expect(page.getByText('+91', { exact: true })).toBeVisible()
  await phone.fill('5876543210')
  await expect(page.getByText('An Indian mobile number starts with 6, 7, 8 or 9.')).toBeVisible()
  await phone.fill('98765')
  await phone.blur()
  await expect(page.getByText('Enter all 10 digits.')).toBeVisible()
  await phone.fill('+91 98765 43210') // pasted the way people copy it
  await expect(phone).toHaveValue('9876543210')
  await expect(page.getByText('Enter all 10 digits.')).toHaveCount(0)

  // places: type, see suggestions, choose with the keyboard
  const from = page.getByRole('combobox', { name: 'Pickup location' })
  await from.fill('wal')
  const list = page.getByRole('listbox', { name: 'Pickup location' })
  await expect(list.getByRole('option')).toHaveCount(2)
  await shot(page, 'place-suggestions')
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('Enter')
  await expect(from).toHaveValue('Waluj Gaon, Chhatrapati Sambhajinagar, Maharashtra')
  await expect(page.getByText('Exact location saved.')).toBeVisible()
  await expect(page.getByRole('link', { name: 'View on map' }).first()).toHaveAttribute('href', /mlat=19\.8512&mlon=75\.2301/)
  await shot(page, 'place-picked')

  // typing again means the text no longer matches the saved position, so it is forgotten
  await from.fill('Waluj Gaon, Chhatrapati Sambhajinagar, Maharashtra x')
  await expect(page.getByText('Exact location saved.')).toHaveCount(0)
  await from.fill('Waluj MIDC')
  await list.getByRole('option', { name: /Waluj MIDC/ }).click()
  await expect(page.getByText('Exact location saved.')).toBeVisible()
  expect(asked).toBeGreaterThan(0)

  // the rest of the form, then what is sent includes the exact positions
  const to = page.getByRole('combobox', { name: 'Delivery location' })
  await to.fill('Pune') // typed, never picked: allowed, sent without a position
  await page.getByLabel('Company name').fill('Forms Test Co')
  await page.getByLabel('Your name').fill('Anil Mehta')
  await page.getByLabel('Material').fill('Steel coils')
  await page.getByLabel('Pickup date').fill(new Date(Date.now() + 5 * 86_400_000).toISOString().slice(0, 10))
  await page.getByLabel(/I agree that CargoOne may contact me/).check()
  await page.getByRole('button', { name: 'Send request' }).click()
  await expect(page.getByRole('heading', { name: 'Request received' })).toBeVisible()
  expect(sent).toMatchObject({ phone: '9876543210', origin: 'Waluj MIDC, Chhatrapati Sambhajinagar, Maharashtra', origin_lat: 19.8601, origin_lng: 75.2145, destination: 'Pune', destination_lat: null })
})

test('the form will not send a wrong mobile number, and works when suggestions are unavailable', async ({ page }) => {
  await page.route('**/api/places/search*', (route) => route.fulfill({ status: 503, json: { detail: 'Place search is not available right now. Type the place instead.' } }))
  let posts = 0
  await page.route('**/api/public/requests', (route) => { posts++; return route.fulfill({ status: 201, json: { reference: 'REQ-9998', status_url: '' } }) })
  await page.goto('/request')
  await page.getByLabel('Company name').fill('Forms Test Co')
  await page.getByLabel('Your name').fill('Anil Mehta')
  await page.getByLabel('Mobile number').fill('98765')
  const from = page.getByRole('combobox', { name: 'Pickup location' })
  await from.fill('Chhatrapati Sambhajinagar')
  await expect(page.getByText('Suggestions are not available right now. Type the place.').first()).toBeVisible() // told, not stuck
  await page.getByRole('combobox', { name: 'Delivery location' }).fill('Nagpur')
  await page.getByLabel('Material').fill('Steel coils')
  await page.getByLabel('Pickup date').fill(new Date(Date.now() + 5 * 86_400_000).toISOString().slice(0, 10))
  await page.getByLabel(/I agree that CargoOne may contact me/).check()
  await page.getByRole('button', { name: 'Send request' }).click()
  await page.waitForTimeout(400)
  expect(posts).toBe(0) // the browser stopped it: the number is not complete
  await expect(page.getByRole('heading', { name: 'Request received' })).toHaveCount(0)
  await page.getByLabel('Mobile number').fill('9876543210')
  await page.getByRole('button', { name: 'Send request' }).click()
  await expect(page.getByRole('heading', { name: 'Request received' })).toBeVisible()
  expect(posts).toBe(1)
})
