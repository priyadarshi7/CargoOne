import { fitToBudget } from './fit'
import { stampSize } from './stamp'

/** Browser compression: decode with EXIF orientation applied, redraw (which strips EXIF/GPS metadata),
 *  and encode as WebP, falling back to JPEG where WebP encoding is unsupported. */
/** `stamp` is printed on a dark strip added BELOW the photo (the paper itself is never covered). */
export async function compressPhoto(file: Blob, stamp?: string): Promise<Blob> {
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  try {
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('Canvas not available')

    const toBlob = (type: string, q: number) =>
      new Promise<Blob | null>((res) => canvas.toBlob(res, type, q))

    const encode = async (edge: number, quality: number) => {
      const scale = Math.min(1, edge / Math.max(bitmap.width, bitmap.height))
      const w = Math.round(bitmap.width * scale)
      const h = Math.round(bitmap.height * scale)
      let band = 0
      let font = 0
      if (stamp) {
        ctx.font = '100px sans-serif'
        ;({ font, band } = stampSize(w, ctx.measureText(stamp).width))
      }
      canvas.width = w // resizing the canvas clears it and resets its settings
      canvas.height = h + band
      ctx.drawImage(bitmap, 0, 0, w, h)
      if (stamp) {
        ctx.fillStyle = '#000'
        ctx.fillRect(0, h, w, band)
        ctx.fillStyle = '#fff'
        ctx.font = `${font}px sans-serif`
        ctx.textBaseline = 'middle'
        ctx.fillText(stamp, Math.round(font * 0.5), h + band / 2)
      }
      const webp = await toBlob('image/webp', quality)
      if (webp && webp.type === 'image/webp') return webp
      const jpeg = await toBlob('image/jpeg', quality)
      if (!jpeg) throw new Error('Encoding failed')
      return jpeg
    }
    return await fitToBudget(encode)
  } finally {
    bitmap.close()
  }
}
