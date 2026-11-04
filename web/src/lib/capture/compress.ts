import { fitToBudget } from './fit'

/** Browser compression: decode with EXIF orientation applied, redraw (which strips EXIF/GPS metadata),
 *  and encode as WebP, falling back to JPEG where WebP encoding is unsupported. */
export async function compressPhoto(file: Blob): Promise<Blob> {
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  try {
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('Canvas not available')

    const toBlob = (type: string, q: number) =>
      new Promise<Blob | null>((res) => canvas.toBlob(res, type, q))

    const encode = async (edge: number, quality: number) => {
      const scale = Math.min(1, edge / Math.max(bitmap.width, bitmap.height))
      canvas.width = Math.round(bitmap.width * scale)
      canvas.height = Math.round(bitmap.height * scale)
      ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
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
