import { expect, test } from '@playwright/test'
import { failOnBrowserErrors, login, shot } from './helpers'

const HEADER = 'Trip ID,Client,Vehicle,Destination,Freight,LR No,E-way Bill No\n'
const csv = (body: string) => ({ name: 'daily-trips.csv', mimeType: 'text/csv', buffer: Buffer.from(HEADER + body) })

test('billing executive checks a file, fixes nothing blindly, then imports; trips appear', async ({ page }) => {
  const noErrors = failOnBrowserErrors(page)
  await login(page, 'billing@cargoone.dev')
  await page.getByRole('link', { name: 'Import' }).click()
  await expect(page.getByRole('heading', { name: 'Import trips' })).toBeVisible()

  // two good rows (one hired vehicle), one broken row, one with an unknown client
  await page.getByLabel('Trip file').setInputFiles(csv(
    'IMP-001,Company B,MH20 EL 4521,Jalna,22000,LR-IMP001,341100000001\n' +
    'IMP-002,Company C (steel),MH17 BY 3092 (hired),Latur,18500,LR-IMP002,341100000002\n' +
    'IMP-003,Company B,not-a-truck,Beed,15000,LR-IMP003,12345\n' +
    'IMP-004,Totally New Client,MH20 GT 7718,Parbhani,9000,LR-IMP004,341100000004\n'))

  const result = page.getByRole('region', { name: 'Check result' })
  await expect(result.getByText('will be created')).toBeVisible()
  await expect(result).toContainText('Fix these rows in your sheet')
  await expect(result).toContainText('registration') // row 4: bad vehicle
  await expect(result).toContainText('12 digits') // ...and bad e-way bill, reported together
  await expect(result).toContainText("Unknown client 'Totally New Client'")
  await shot(page, 'import-check')

  // nothing has been written yet
  await page.getByRole('link', { name: 'Trips' }).click()
  await expect(page.getByRole('cell', { name: /IMP-001/ })).toHaveCount(0)
  await page.getByRole('link', { name: 'Import' }).click()

  // allow the unknown client, re-check, import
  await page.getByLabel('Trip file').setInputFiles(csv(
    'IMP-001,Company B,MH20 EL 4521,Jalna,22000,LR-IMP001,341100000001\n' +
    'IMP-002,Company C (steel),MH17 BY 3092 (hired),Latur,18500,LR-IMP002,341100000002\n' +
    'IMP-004,Totally New Client,MH20 GT 7718,Parbhani,9000,LR-IMP004,341100000004\n'))
  await page.getByLabel(/Create clients that do not exist yet/).check()
  await expect(page.getByText('Also new: 1 client(s) (Totally New Client)')).toBeVisible()
  await page.getByRole('button', { name: 'Import 3 trips' }).click()
  await expect(page.getByRole('status')).toContainText('Imported: 3 new')
  await shot(page, 'import-done')

  await page.getByRole('link', { name: 'View trips' }).click()
  await expect(page.getByRole('cell', { name: /IMP-001/ })).toBeVisible()
  const hired = page.locator('tr', { hasText: 'IMP-002' })
  await expect(hired).toContainText('hired')
  await expect(hired).toContainText('Awaiting POD')
  await noErrors()
})

test('uploading the same file again changes nothing', async ({ page }) => {
  await login(page, 'billing@cargoone.dev')
  await page.getByRole('link', { name: 'Import' }).click()
  await page.getByLabel('Trip file').setInputFiles(csv('IMP-001,Company B,MH20 EL 4521,Jalna,22000,LR-IMP001,341100000001\n'))
  await expect(page.getByRole('button', { name: 'Nothing to import' })).toBeDisabled()
  await expect(page.getByRole('region', { name: 'Check result' })).toContainText('already up to date')
})

test('a wrong file type gets a plain message, and the MD cannot see the import page', async ({ page }) => {
  await login(page, 'billing@cargoone.dev')
  await page.getByRole('link', { name: 'Import' }).click()
  await page.getByLabel('Trip file').setInputFiles({ name: 'notes.pdf', mimeType: 'application/pdf', buffer: Buffer.from('x') })
  await expect(page.getByRole('alert')).toContainText('.csv or .xlsx')
  await page.getByRole('button', { name: 'Sign out' }).click()

  await login(page, 'md@cargoone.dev')
  await expect(page.getByRole('link', { name: 'Import' })).toHaveCount(0)
})
