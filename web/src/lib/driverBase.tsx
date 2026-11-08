import { createContext, useContext, type ReactNode } from 'react'

/** The driver screens are the same for a signed-in driver (under /driver) and for a hired driver on a private link (under /u/<token>).
 *  Everything that points at another driver screen goes through `path`, so both live in one set of pages. */
interface Base { base: string; link: string | null }
const Ctx = createContext<Base>({ base: '/driver', link: null })

export function DriverBaseProvider({ link, children }: { link: string; children: ReactNode }) {
  return <Ctx.Provider value={{ base: `/u/${link}`, link }}>{children}</Ctx.Provider>
}

export function useDriverBase(): Base & { path: (p: string) => string } {
  const v = useContext(Ctx)
  // '/driver' and '/driver/...' and '/driver?x=1' move to the base; anything else (an office link) is left alone
  const path = (p: string) => (/^\/driver(?=$|[/?#])/.test(p) ? v.base + p.slice('/driver'.length) : p)
  return { ...v, path }
}
