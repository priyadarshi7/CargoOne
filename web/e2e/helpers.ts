import { expect, type Page } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { join } from 'node:path'

export const PASSWORD = 'cargoone-dev'
export const FIXTURE = join(import.meta.dirname, 'fixtures', 'pod.png')
const SHOTS = join(import.meta.dirname, 'screenshots')

export async function login(page: Page, identifier: string, secret = PASSWORD) {
  await page.goto('/login')
  await page.getByLabel('Email or phone').fill(identifier)
  await page.getByLabel('Password or PIN').fill(secret)
  await page.getByRole('button', { name: 'Sign in' }).click()
}

/** Saves a screenshot to web/e2e/screenshots (git-ignored) so layouts can be inspected after a run. */
export async function shot(page: Page, name: string) {
  mkdirSync(SHOTS, { recursive: true })
  await page.screenshot({ path: join(SHOTS, `${name}.png`), fullPage: true })
}

/** Fails the test if the page throws an uncaught error or logs a console error. */
export function failOnBrowserErrors(page: Page) {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => {
    if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) errors.push(m.text())
  })
  return async () => expect(errors, 'browser errors').toEqual([])
}
