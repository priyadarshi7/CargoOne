import { beforeEach, describe, expect, it, vi } from 'vitest'
import { acknowledge, enqueue, flush, getItem, listAll, pendingCount, PermanentUploadError, type UploadResult } from './queue'

const ok = (id: string): UploadResult => ({
  submission_id: id, decision: 'verified', reasons: [], voice: 'ok', attempt: 1, retakes_left: 2, duplicate: false,
})
const photo = (tripId = 't1') => enqueue({ tripId, blob: new Blob(['x']), capturedAt: '2026-11-04T10:00:00Z', lat: 19.8, lng: 75.3 })

beforeEach(async () => {
  for (const i of await listAll()) await acknowledge(i.id)
})

describe('offline queue', () => {
  it('persists a photo as queued with an idempotency id', async () => {
    const a = await photo()
    expect(a.id).toMatch(/^[0-9a-f]{32}$/)
    expect((await getItem(a.id))?.status).toBe('queued')
    expect(await pendingCount()).toBe(1)
  })

  it('stays queued and counts the attempt when offline, then succeeds later with the SAME id', async () => {
    const a = await photo()
    const seen: string[] = []
    const offline = vi.fn(async () => { throw new TypeError('Failed to fetch') })
    await flush(offline)
    expect(await getItem(a.id)).toMatchObject({ status: 'queued', attempts: 1 })

    await flush(async (i) => (seen.push(i.id), ok('s1')))
    expect(seen).toEqual([a.id]) // retry reuses the idempotency key: no duplicate server-side
    expect(await getItem(a.id)).toMatchObject({ status: 'done', attempts: 2, result: { decision: 'verified' } })
    expect(await pendingCount()).toBe(0)
  })

  it('uploads oldest first and stops at the first network failure (keeps order)', async () => {
    const a = await photo('t1'), b = await photo('t2'), c = await photo('t3')
    const order: string[] = []
    await flush(async (i) => {
      order.push(i.id)
      if (i.id === b.id) throw new TypeError('offline')
      return ok(i.id)
    })
    expect(order).toEqual([a.id, b.id]) // c never attempted
    expect((await getItem(a.id))?.status).toBe('done')
    expect((await getItem(b.id))?.status).toBe('queued')
    expect((await getItem(c.id))?.status).toBe('queued')
  })

  it('marks permanent rejections failed and keeps draining the rest', async () => {
    const a = await photo('t1'), b = await photo('t2')
    await flush(async (i) => {
      if (i.id === a.id) throw new PermanentUploadError('POD already verified')
      return ok(i.id)
    })
    expect(await getItem(a.id)).toMatchObject({ status: 'failed', error: 'POD already verified' })
    expect((await getItem(b.id))?.status).toBe('done')
  })

  it('concurrent flushes share one run (no double upload)', async () => {
    await photo()
    let calls = 0
    const slow = async () => { calls++; await new Promise((r) => setTimeout(r, 20)); return ok('s') }
    await Promise.all([flush(slow), flush(slow), flush(slow)])
    expect(calls).toBe(1)
  })
})
