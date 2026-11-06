import { expect, test, type Page } from '@playwright/test'
import { shot } from './helpers'

// Google's map and Google's answers are replaced here (a real map needs a real key), so this checks OUR screen: suggestions, the pin picker,
// the address that follows the pin, confirm, and what happens when the map cannot load. api/tests/test_places.py covers the server side.

const FAKE_MAPS_JS = `
class FakeMap {
  constructor(el, o) { this.o = o; this.center = o.center; this.zoom = o.zoom; this.l = {}; window.__fakeMap = this; setTimeout(() => this.fire('idle'), 30) }
  getCenter() { const c = this.center; return { lat: () => c.lat, lng: () => c.lng } }
  setCenter(p) { this.center = p }
  panTo(p) { this.center = p; setTimeout(() => this.fire('idle'), 30) }
  setZoom(z) { this.zoom = z }
  addListener(ev, fn) { (this.l[ev] ||= []).push(fn); return { remove() {} } }
  fire(ev) { (this.l[ev] || []).forEach((f) => f()) }
}
window.google = { maps: { importLibrary: async () => ({ Map: FakeMap }) } };`

const SUGGESTIONS = [
  { id: 'ChIJwaluj0000001', label: 'Waluj MIDC, Chhatrapati Sambhajinagar, Maharashtra', name: 'Waluj MIDC', detail: 'Chhatrapati Sambhajinagar, Maharashtra', lat: null, lng: null },
  { id: 'ChIJwaluj0000002', label: 'Waluj Gaon, Maharashtra', name: 'Waluj Gaon', detail: 'Maharashtra', lat: null, lng: null },
]

async function google(page: Page) {
  const seen = { details: [] as URL[], reverse: [] as URL[], search: [] as URL[] }
  await page.route('**/api/places/config', (r) => r.fulfill({ json: { provider: 'google', maps_key: 'fake-browser-key' } }))
  await page.route('**/maps.googleapis.com/maps/api/js*', (r) => r.fulfill({ contentType: 'application/javascript', body: FAKE_MAPS_JS }))
  await page.route('**/api/places/search*', (r) => { seen.search.push(new URL(r.request().url())); return r.fulfill({ json: SUGGESTIONS }) })
  await page.route('**/api/places/details*', (r) => {
    seen.details.push(new URL(r.request().url()))
    return r.fulfill({ json: { id: 'ChIJwaluj0000001', label: 'Waluj MIDC, Chhatrapati Sambhajinagar, Maharashtra', name: 'Waluj MIDC', detail: 'Chhatrapati Sambhajinagar, Maharashtra', lat: 19.8601, lng: 75.2145 } })
  })
  await page.route('**/api/places/reverse*', (r) => {
    const u = new URL(r.request().url()); seen.reverse.push(u)
    const lat = Number(u.searchParams.get('lat')), lng = Number(u.searchParams.get('lng'))
    const pune = lat < 19
    return r.fulfill({ json: { label: pune ? 'Shivaji Nagar, Pune, Maharashtra' : 'MIDC Waluj, Chhatrapati Sambhajinagar, Maharashtra', name: pune ? 'Shivaji Nagar' : 'MIDC Waluj', detail: pune ? 'Pune, Maharashtra' : 'Chhatrapati Sambhajinagar, Maharashtra', lat, lng } })
  })
  return seen
}

test('with Google set up: pick a suggestion, then place the pin on a map, and the saved position is exactly where the pin was', async ({ page }) => {
  const seen = await google(page)
  await page.goto('/request')

  // 1. a Google suggestion has no position yet; picking it fetches the position, in the same session as the search
  const from = page.getByRole('combobox', { name: 'Pickup location' })
  await from.fill('wal')
  const list = page.getByRole('listbox', { name: 'Pickup location' })
  await expect(list.getByRole('option')).toHaveCount(2)
  await expect(list.getByText('Powered by Google')).toBeVisible() // credit, as Google asks when its suggestions are shown without a Google map
  await list.getByRole('option', { name: /Waluj MIDC/ }).click()
  await expect(from).toHaveValue('Waluj MIDC, Chhatrapati Sambhajinagar, Maharashtra')
  await expect(page.getByText('Exact location saved.')).toBeVisible()
  expect(seen.details).toHaveLength(1)
  expect(seen.details[0].searchParams.get('id')).toBe('ChIJwaluj0000001')
  expect(seen.details[0].searchParams.get('session')).toBe(seen.search[0].searchParams.get('session')) // one session: search and pick

  // 2. the map picker for the delivery place: opens on the depot, the address follows the pin
  await page.getByRole('button', { name: 'Pick on map' }).nth(1).click()
  const picker = page.getByRole('dialog', { name: 'Select location' })
  await expect(picker).toBeVisible()
  await expect(picker.getByText('MIDC Waluj')).toBeVisible() // the address under the pin when it opened
  await shot(page, 'map-picker')
  await expect(picker.getByRole('button', { name: 'Confirm location' })).toBeEnabled()

  // moving the map moves the pin's spot: the address updates
  await page.evaluate(() => { const m = (window as unknown as { __fakeMap: { center: unknown; fire: (e: string) => void } }).__fakeMap; m.center = { lat: 18.5314, lng: 73.8446 }; m.fire('dragstart'); m.fire('idle') })
  await expect(picker.getByText('Shivaji Nagar')).toBeVisible()
  await expect(picker.getByRole('button', { name: 'Confirm location' })).toBeEnabled()
  await picker.getByRole('button', { name: 'Confirm location' }).click()
  await expect(picker).toHaveCount(0)
  const to = page.getByRole('combobox', { name: 'Delivery location' })
  await expect(to).toHaveValue('Shivaji Nagar, Pune, Maharashtra')
  await expect(page.getByRole('link', { name: 'View on map' }).nth(1)).toHaveAttribute('href', /mlat=18\.5314&mlon=73\.8446/) // exactly where the pin was
})

test('in the map picker, searching jumps the map and keeps the searched place; the pin is only moved by the person', async ({ page }) => {
  const seen = await google(page)
  await page.goto('/request')
  await page.getByRole('button', { name: 'Pick on map' }).first().click()
  const picker = page.getByRole('dialog', { name: 'Select location' })
  await expect(picker.getByText('MIDC Waluj')).toBeVisible()

  await picker.getByRole('combobox', { name: 'Search for an area, street or landmark' }).fill('waluj')
  await picker.getByRole('option', { name: /Waluj MIDC/ }).click()
  const zoom = await page.evaluate(() => (window as unknown as { __fakeMap: { zoom: number; center: { lat: number } } }).__fakeMap)
  expect(zoom.zoom).toBe(17) // zoomed in on the place
  expect(zoom.center.lat).toBe(19.8601) // the map is on the place
  const reverseCalls = seen.reverse.length
  await expect(picker.getByText('Waluj MIDC', { exact: true })).toBeVisible()
  await page.waitForTimeout(500) // the map settles on the place: the address of the pin is NOT looked up again over the searched place's name
  expect(seen.reverse.length).toBe(reverseCalls)
  await picker.getByRole('button', { name: 'Confirm location' }).click()
  await expect(page.getByRole('combobox', { name: 'Pickup location' })).toHaveValue('Waluj MIDC, Chhatrapati Sambhajinagar, Maharashtra')
  await expect(page.getByRole('link', { name: 'View on map' })).toHaveAttribute('href', /mlat=19\.8601&mlon=75\.2145/)
})

test('when the map cannot load, the person is told and search still works', async ({ page }) => {
  await page.route('**/api/places/config', (r) => r.fulfill({ json: { provider: 'google', maps_key: 'bad-key' } }))
  await page.route('**/maps.googleapis.com/maps/api/js*', (r) => r.abort())
  await page.route('**/api/places/search*', (r) => r.fulfill({ json: SUGGESTIONS }))
  await page.route('**/api/places/details*', (r) => r.fulfill({ json: { ...SUGGESTIONS[0], lat: 19.8601, lng: 75.2145 } }))
  await page.goto('/request')
  await page.getByRole('button', { name: 'Pick on map' }).first().click()
  const picker = page.getByRole('dialog', { name: 'Select location' })
  await expect(picker.getByRole('alert')).toContainText('The map could not load')
  await expect(picker.getByRole('button', { name: 'Confirm location' })).toBeDisabled() // nothing chosen yet
  await picker.getByRole('combobox', { name: 'Search for an area, street or landmark' }).fill('waluj')
  await picker.getByRole('option', { name: /Waluj MIDC/ }).click()
  await expect(picker.getByRole('button', { name: 'Confirm location' })).toBeEnabled() // a searched place can still be confirmed
  await picker.getByRole('button', { name: 'Confirm location' }).click()
  await expect(page.getByText('Exact location saved.')).toBeVisible()
})

test('without a map key there is no map button, only the suggestions', async ({ page }) => {
  await page.route('**/api/places/config', (r) => r.fulfill({ json: { provider: 'photon', maps_key: null } }))
  await page.goto('/request')
  await expect(page.getByRole('combobox', { name: 'Pickup location' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Pick on map' })).toHaveCount(0)
})
