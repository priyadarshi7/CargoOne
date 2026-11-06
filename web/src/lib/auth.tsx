import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, ApiError, tokenStore, type User } from './api'

interface AuthState {
  user: User | null
  loading: boolean
  login: (identifier: string, secret: string) => Promise<User>
  logout: () => void
  adopt: (token: string, user: User) => void // use a fresh session (after a PIN/password change)
}

const USER_KEY = 'cargoone.user'
function cacheUser(u: User | null) { try { if (u) localStorage.setItem(USER_KEY, JSON.stringify(u)); else localStorage.removeItem(USER_KEY) } catch { /* storage blocked: offline start just shows sign-in */ } }
function cachedUser(): User | null { try { return JSON.parse(localStorage.getItem(USER_KEY) ?? 'null') as User | null } catch { return null } }

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(() => tokenStore.get() !== null)

  useEffect(() => {
    if (!tokenStore.get()) return
    api<User>('/auth/me')
      .then((u) => { cacheUser(u); setUser(u) })
      .catch((e) => {
        if (e instanceof ApiError) { tokenStore.clear(); cacheUser(null) } // the server answered: the session is really over
        else { const u = cachedUser(); if (u) setUser(u) } // no network (a driver in a dead zone): keep them signed in with the last known profile
      })
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (identifier: string, secret: string) => {
    const res = await api<{ access_token: string; user: User }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ identifier, secret }),
    })
    tokenStore.set(res.access_token)
    cacheUser(res.user)
    setUser(res.user)
    return res.user
  }, [])

  const adopt = useCallback((token: string, u: User) => {
    tokenStore.set(token)
    cacheUser(u)
    setUser(u)
  }, [])

  const logout = useCallback(() => {
    tokenStore.clear()
    cacheUser(null)
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, loading, login, logout, adopt }), [user, loading, login, logout, adopt])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth outside AuthProvider')
  return v
}

export const homeFor = (role: User['role']) => (role === 'driver' ? '/driver' : role === 'client' ? '/portal' : '/office')
