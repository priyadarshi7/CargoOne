import { expect, test } from '@playwright/test'
import { failOnBrowserErrors, login, shot } from './helpers'

/** The AI benchmark tab: the runs, the headline numbers, and every photographed sheet labelled with what was expected. */
test('ops opens the AI benchmark, compares the runs and looks at one sheet', async ({ page }) => {
  const noErrors = failOnBrowserErrors(page)
  await login(page, 'ops@cargoone.dev')
  await page.getByRole('link', { name: 'AI benchmark' }).click()
  await expect(page).toHaveURL(/\/office\/benchmark/)
  await expect(page.getByRole('heading', { name: 'AI benchmark' })).toBeVisible()

  await expect(page.getByRole('heading', { name: 'Runs' })).toBeVisible()
  await expect(page.getByText('Decision pass rate')).toBeVisible()
  await expect(page.getByText('Unsafe errors', { exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'How each field was read' })).toBeVisible()
  await shot(page, 'benchmark-top')

  // pick the first (oldest) run, then narrow the suite to the unsafe sheets
  const runButtons = page.getByRole('button', { name: /run 1/ })
  await runButtons.first().click()
  await expect(runButtons.first()).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: /^Unsafe/ }).click()
  await expect(page.getByRole('heading', { name: /S03/ })).toBeVisible()
  await page.getByText('Expected against what the AI read').first().click()
  await expect(page.getByRole('cell', { name: 'Receiver signature' }).first()).toBeVisible()
  await expect(page.locator('img[alt^="S03"]')).toBeVisible()
  await shot(page, 'benchmark-suite')

  await page.getByRole('button', { name: 'S03 Receiver part' }).or(page.locator('img[alt^="S03"]')).first().click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.keyboard.press('Escape').catch(() => undefined)
  await noErrors()
})
