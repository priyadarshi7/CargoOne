/** Indian mobile numbers, the same rules the server applies (api/app/phones.py): 10 digits, first digit 6 to 9.
 *  People paste "+91 98765 43210", "098765 43210" or "9876543210"; all become the plain 10 digits. */
export const MOBILE = /^[6-9]\d{9}$/

export function digitsOf(text: string): string {
  let d = text.replace(/\D/g, '')
  if (d.length === 12 && d.startsWith('91')) d = d.slice(2) // +91 pasted in front
  else if (d.length === 11 && d.startsWith('0')) d = d.slice(1) // trunk 0 pasted in front
  return d.slice(0, 10)
}

export type PhoneProblem = 'start' | 'short' | null

/** What is wrong with the digits typed so far. An empty box is not a problem here (the form's own "required" handles it). */
export function phoneProblem(digits: string): PhoneProblem {
  if (!digits) return null
  if (!/^[6-9]/.test(digits)) return 'start'
  return digits.length < 10 ? 'short' : null
}

/** "98765 43210", for showing a stored number. */
export const showPhone = (digits: string): string => (digits.length === 10 ? `${digits.slice(0, 5)} ${digits.slice(5)}` : digits)
