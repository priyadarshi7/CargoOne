import { describe, expect, it, vi } from 'vitest'
import code from '../../public/push-sw.js?raw'

/** Runs public/push-sw.js against a stand-in for the service worker global and checks what it shows and where a tap leads. */
function load() {
  const handlers: Record<string, (e: unknown) => void> = {}
  const shown: { title: string; opts: Record<string, unknown> }[] = []
  const opened: string[] = []
  const self = {
    addEventListener: (type: string, fn: (e: unknown) => void) => { handlers[type] = fn },
    registration: { showNotification: async (title: string, opts: Record<string, unknown>) => { shown.push({ title, opts }) } },
    clients: { matchAll: async () => [], openWindow: async (u: string) => { opened.push(u) } },
  }
  new Function('self', code)(self)
  return { handlers, shown, opened }
}

describe('push-sw.js', () => {
  it('shows the alert it receives, with the link to open', async () => {
    const { handlers, shown } = load()
    let work: Promise<unknown> = Promise.resolve()
    handlers.push({ data: { json: () => ({ title: 'New trip', body: 'TRP-1 Pune', url: '/driver?trip=1' }) }, waitUntil: (p: Promise<unknown>) => { work = p } })
    await work
    expect(shown[0].title).toBe('New trip')
    expect(shown[0].opts).toMatchObject({ body: 'TRP-1 Pune', data: { url: '/driver?trip=1' } })
  })

  it('still shows something when the message is not JSON, and opens the driver home by default', async () => {
    const { handlers, shown, opened } = load()
    let work: Promise<unknown> = Promise.resolve()
    handlers.push({ data: { json: () => { throw new Error('bad') }, text: () => 'plain' }, waitUntil: (p: Promise<unknown>) => { work = p } })
    await work
    expect(shown[0].title).toBe('CargoOne')
    const close = vi.fn()
    handlers.notificationclick({ notification: { close, data: undefined }, waitUntil: (p: Promise<unknown>) => { work = p } })
    await work
    expect(close).toHaveBeenCalled()
    expect(opened).toEqual(['/driver'])
  })
})
