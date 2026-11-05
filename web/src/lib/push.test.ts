import { describe, expect, it } from 'vitest'
import { keyBytes } from './push'

describe('keyBytes', () => {
  it('turns the server public key (url-safe base64, no padding) into the raw bytes the browser wants', () => {
    // 65 bytes: the length of an uncompressed P-256 point, which is what a VAPID public key is
    const raw = Uint8Array.from({ length: 65 }, (_, i) => (i * 7 + 4) % 256)
    const b64 = btoa(String.fromCharCode(...raw)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
    expect(Array.from(keyBytes(b64))).toEqual(Array.from(raw))
  })
})
