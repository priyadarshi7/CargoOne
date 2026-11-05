// Chrome announces "this app can be installed" ONCE, early (often on the sign-in screen). Listen from the first moment the
// page loads and keep the event, so the driver home screen can offer the install button whenever it appears.
export interface InstallEvent extends Event { prompt: () => Promise<void>; userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }> }

let saved: InstallEvent | null = null
const listeners = new Set<() => void>()
const notify = () => listeners.forEach((l) => l())

window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); saved = e as InstallEvent; notify() })
window.addEventListener('appinstalled', () => { saved = null; notify() })

export const installEvent = () => saved
export const clearInstallEvent = () => { saved = null; notify() }
export function subscribeInstall(fn: () => void) { listeners.add(fn); return () => { listeners.delete(fn) } }
