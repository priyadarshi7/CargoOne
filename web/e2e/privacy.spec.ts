import { expect, test } from '@playwright/test'
import { failOnBrowserErrors, login, shot } from './helpers'

/** DPDP: anyone can read the notice and ask about their data; the privacy officer sees it in a register, looks up what is held, erases it and closes it. */
test('a person asks for their data to be erased and the officer answers', async ({ page, browser }) => {
  const noErrors = failOnBrowserErrors(page)
  await page.goto('/privacy')
  await expect(page.getByRole('heading', { name: 'Privacy notice' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'How long we keep it' })).toBeVisible()
  await expect(page.getByText(/8 years after the trip is closed/)).toBeVisible()
  await shot(page, 'privacy-notice')

  const form = page.getByRole('region', { name: 'Ask us' })
  await form.getByLabel('What do you want?').selectOption('erasure')
  await form.getByLabel('Mobile number').fill('9811200345')
  await form.getByLabel('Your name (optional)').fill('Ramesh Receiver')
  await form.getByRole('button', { name: 'Send request' }).click()
  await expect(form.getByRole('status')).toContainText(/PRV-\d{6}/)
  await shot(page, 'privacy-sent')
  const ref = (await form.getByRole('status').textContent())!.match(/PRV-\d{6}/)![0]

  // the privacy officer (the admin) sees it, is shown what is held, and closes it
  const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } })
  const office = await ctx.newPage()
  const officeErrors = failOnBrowserErrors(office)
  await login(office, 'admin@cargoone.dev')
  await office.getByRole('link', { name: 'Privacy requests' }).click()
  await expect(office.getByRole('heading', { name: 'Privacy requests' })).toBeVisible()
  const row = office.getByRole('listitem').filter({ hasText: ref })
  await expect(row).toContainText('Erase my details')
  await expect(row).toContainText('9811200345')
  await shot(office, 'privacy-register')
  await row.getByRole('button', { name: 'What we hold' }).click()
  const dialog = office.getByRole('dialog', { name: new RegExp(ref) })
  await expect(dialog.getByText('Nothing is held under this number.')).toBeVisible()
  await dialog.getByLabel('What was done, or why not').fill('Nothing was held under this number')
  await dialog.getByRole('button', { name: 'Close request' }).click()
  await expect(office.getByRole('dialog')).toHaveCount(0)
  await expect(row).toHaveCount(0)
  await office.getByRole('tab', { name: 'Closed' }).click()
  const closed = office.getByRole('listitem').filter({ hasText: ref })
  await expect(closed).toContainText('******0345') // the number is cut once it is closed
  await expect(closed).not.toContainText('9811200345')
  await ctx.close()

  // ops cannot open the officer's desk
  const ops = await browser.newPage()
  await login(ops, 'ops@cargoone.dev')
  await expect(ops.getByRole('link', { name: 'Privacy requests' })).toHaveCount(0)
  await ops.close()
  await noErrors()
  await officeErrors()
})
