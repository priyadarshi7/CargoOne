/** Instant on-phone check of a POD photo, BEFORE it is compressed and uploaded. Catches the common bad shots (shaky, dark,
 *  glare-washed, lens covered) so the driver retakes at once instead of finding out after the truck has left the gate.
 *
 *  It is a cheap filter, not the AI: it only looks at pixel statistics on a small greyscale copy. The server-side AI still
 *  does the real verification, and the driver can always choose "use anyway", because a plain white form with light print can
 *  look "empty" to simple statistics. */
export type Problem = 'blurry' | 'dark' | 'glare' | 'empty'

export interface Pixels { data: ArrayLike<number>; width: number; height: number } // RGBA, like canvas ImageData

export interface Quality { ok: boolean; problems: Problem[]; metrics: { sharpness: number; brightness: number; contrast: number; blown: number; ink: number } }

// Tuned on synthetic and real-looking PODs (see quality.test.ts and the tuning notes in docs/03-decisions.md, ADR 59).
export const LIMITS = {
  sharpness: 150, // variance of the Laplacian: a crisp printed form scores in the thousands, a clearly soft one under ~100
  dark: 55, // average brightness (0-255) below this is a dim shot or a covered lens
  blown: 0.4, // share of pure-white pixels above which the page is washed out...
  ink: 0.01, // ...but only if almost no dark print survives (a white page with readable print is fine)
  flat: 6, // brightness spread below this = a blank frame
}

export const SIDE = 640 // analysis size (longest edge): big enough that print strokes survive, small enough to run in ~10 ms on a low-end phone

function grey(p: Pixels): Float32Array {
  const out = new Float32Array(p.width * p.height)
  for (let i = 0, j = 0; i < out.length; i++, j += 4) out[i] = 0.299 * p.data[j] + 0.587 * p.data[j + 1] + 0.114 * p.data[j + 2]
  return out
}

export function assess(p: Pixels): Quality {
  const g = grey(p)
  const n = g.length
  let sum = 0, blownCount = 0, inkCount = 0
  for (let i = 0; i < n; i++) { sum += g[i]; if (g[i] >= 250) blownCount++; if (g[i] < 120) inkCount++ }
  const brightness = sum / n
  let varSum = 0
  for (let i = 0; i < n; i++) varSum += (g[i] - brightness) ** 2
  const contrast = Math.sqrt(varSum / n)
  const blown = blownCount / n
  const ink = inkCount / n

  // Sharpness = variance of the Laplacian (second derivative). Blur flattens edges, so the variance collapses.
  const { width: w, height: h } = p
  let lsum = 0, lsq = 0, count = 0
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const i = y * w + x
      const lap = 4 * g[i] - g[i - 1] - g[i + 1] - g[i - w] - g[i + w]
      lsum += lap; lsq += lap * lap; count++
    }
  }
  const sharpness = count ? lsq / count - (lsum / count) ** 2 : 0

  const problems: Problem[] = []
  if (brightness < LIMITS.dark) problems.push('dark')
  else if (blown > LIMITS.blown && ink < LIMITS.ink) problems.push('glare')
  else if (contrast < LIMITS.flat) problems.push('empty')
  else if (sharpness < LIMITS.sharpness) problems.push('blurry')
  return { ok: problems.length === 0, problems, metrics: { sharpness, brightness, contrast, blown, ink } }
}

/** Decode the picked file at a small size and assess it. Returns null if the browser cannot decode it (then we just upload). */
export async function checkPhoto(file: Blob): Promise<Quality | null> {
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
    try {
      const scale = Math.min(1, SIDE / Math.max(bitmap.width, bitmap.height))
      const canvas = document.createElement('canvas')
      canvas.width = Math.max(8, Math.round(bitmap.width * scale))
      canvas.height = Math.max(8, Math.round(bitmap.height * scale))
      const ctx = canvas.getContext('2d', { willReadFrequently: true })
      if (!ctx) return null
      ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
      return assess(ctx.getImageData(0, 0, canvas.width, canvas.height))
    } finally {
      bitmap.close()
    }
  } catch {
    return null
  }
}
