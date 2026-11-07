import { expect, test } from '@playwright/test'
import { login, shot } from './helpers'

/** A driver in a dead zone: what they do is kept on the phone and sent when the network returns, without doing it twice. */
test('an expense added with no network is saved on the phone, then sent once when the network returns', async ({ page, context, request }) => {
  await login(page, '9000000066', '4821')
  await page.getByRole('button', { name: 'English' }).click()
  await expect(page.getByRole('region', { name: 'Hingoli' })).toBeVisible() // trips loaded and saved on the phone

  await page.getByRole('link', { name: 'Expenses' }).click()
  await expect(page.getByRole('heading', { name: 'Add expense' })).toBeVisible()
  await context.setOffline(true)
  await expect(page.getByText('No network')).toBeVisible()

  await page.getByRole('radio', { name: 'Food' }).click()
  await page.getByLabel('Amount (₹)').fill('77')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByText('Saved on your phone')).toBeVisible()
  await expect(page.getByText(/1 waiting to send/)).toBeVisible()
  await shot(page, 'driver-offline-saved')

  await context.setOffline(false) // the browser says "online": the saved expense goes by itself
  await expect(page.getByText(/waiting to send/)).toHaveCount(0, { timeout: 20_000 })
  await page.getByRole('button', { name: 'Add another' }).click()
  await expect(page.getByText('Food · ₹77')).toHaveCount(1) // sent once, not twice

  // leave the office queue as it was: the office rejects this test entry so other tests see no stray pending expense
  const auth = await request.post('/api/auth/login', { data: { identifier: 'ops@cargoone.dev', secret: 'cargoone-dev' } })
  const headers = { Authorization: `Bearer ${(await auth.json()).access_token}` }
  const all = (await (await request.get('/api/expenses', { headers })).json()) as { id: string; amount: number; category: string; status: string }[]
  for (const e of all.filter((x) => x.status === 'pending' && x.category === 'food' && x.amount === 77)) {
    await request.post(`/api/expenses/${e.id}/decision`, { headers, data: { action: 'reject', note: 'e2e' } })
  }
})

test('the trip list stays on screen when the network drops after it was loaded', async ({ page, context }) => {
  await login(page, '9000000001', '1234')
  await page.getByRole('button', { name: 'English' }).click()
  await expect(page.getByText(/TRP-/).first()).toBeVisible()
  await context.setOffline(true)
  await page.getByRole('link', { name: 'Help' }).click()
  await expect(page.getByRole('heading', { name: 'Help' })).toBeVisible()
  await page.getByRole('link', { name: 'Trips' }).click()
  await expect(page.getByText(/TRP-/).first()).toBeVisible() // the phone's saved copy of the trips
  await expect(page.getByText('No network. Showing what is saved on your phone.')).toBeVisible()
  await shot(page, 'driver-home-offline')
})
