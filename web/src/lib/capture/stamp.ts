import type { Position } from './geo'

/** The line printed under a delivery photo: when and where it was taken, in Indian time, by the server's clock (the phone's own clock, marked as such, only when the server cannot be reached). It travels with the picture when it is forwarded or printed.
 *  It is added by the app at the moment of capture, below the photo (never over the paper). */
export function stampText(at: Date, pos: Position | null, fromServer = true): string {
  const when = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).format(at)
  const where = pos ? `${Math.abs(pos.lat).toFixed(5)}${pos.lat >= 0 ? 'N' : 'S'} ${Math.abs(pos.lng).toFixed(5)}${pos.lng >= 0 ? 'E' : 'W'}` : 'location not available'
  return `CargoOne · ${when.replace(',', '')} IST${fromServer ? '' : ' (phone clock)'} · ${where}`
}

/** The font size that makes the line fit the picture's width (no smaller than a legible 11 px), and the height of the strip around it. */
export function stampSize(width: number, textWidthAt100: number): { font: number; band: number } {
  const font = Math.max(11, Math.min(Math.round(width * 0.03), Math.floor((width * 0.96 * 100) / textWidthAt100)))
  return { font, band: Math.round(font * 2) }
}
