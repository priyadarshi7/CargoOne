import { beforeEach, describe, expect, it } from 'vitest'
import { readCache, writeCache } from './cache'
import { db } from './db'
import { enqueueAction, flushOutbox, listOutbox, PermanentSendError } from './outbox'

beforeEach(async () => { await (await db()).clear('outbox'); await (await db()).clear('kv') })

describe('outbox', () => {
  it('sends saved actions oldest first and removes them', async () => {
    await enqueueAction('start', { trip_id: 'a' })
    await enqueueAction('expense', { trip_id: 'a', amount: '10' })
    const sent: string[] = []
    await flushOutbox(async (i) => { sent.push(i.kind) })
    expect(sent).toEqual(['start', 'expense'])
    expect(await listOutbox()).toHaveLength(0)
  })

  it('keeps everything and the order when the network fails', async () => {
    await enqueueAction('start', { trip_id: 'a' })
    await enqueueAction('expense', { trip_id: 'a', amount: '10' })
    let calls = 0
    await flushOutbox(async () => { calls++; throw new Error('offline') })
    expect(calls).toBe(1) // stopped at the first failure
    const left = await listOutbox()
    expect(left.map((i) => i.kind)).toEqual(['start', 'expense'])
    expect(left[0].attempts).toBe(1)
  })

  it('marks an answer that will never change as failed and carries on', async () => {
    await enqueueAction('start', { trip_id: 'a' })
    await enqueueAction('expense', { trip_id: 'a', amount: '10' })
    await flushOutbox(async (i) => { if (i.kind === 'start') throw new PermanentSendError('This trip is delivered') })
    const left = await listOutbox()
    expect(left).toHaveLength(1)
    expect(left[0]).toMatchObject({ kind: 'start', status: 'failed', error: 'This trip is delivered' })
  })

  it('keeps the same id across retries, because it is the idempotency key', async () => {
    const item = await enqueueAction('expense', { amount: '5' })
    await flushOutbox(async () => { throw new Error('offline') })
    expect((await listOutbox())[0].id).toBe(item.id)
  })
})

describe('cache', () => {
  it('round-trips a saved answer and never mixes two people', async () => {
    await writeCache('u1:/trips/mine', [{ id: 1 }])
    expect((await readCache('u1:/trips/mine'))?.value).toEqual([{ id: 1 }])
    expect(await readCache('u2:/trips/mine')).toBeNull()
  })
})
