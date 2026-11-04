import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, tokenStore, type User } from './api'

interface AuthState {
  user: User | null
  loading: boolean
  login: (identifier: string, secret: string) => Promise<User>
  logout: () => void
  adopt: (token: string, user: User) => void // use a fresh session (after a PIN/password change)
}

const Ctx = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(() => tokenStore.get() !== null)

  useEffect(() => {
    if (!tokenStore.get()) return
    api<User>('/auth/me')
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (identifier: string, secret: string) => {
    const res = await api<{ access_token: string; user: User }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ identifier, secret }),
    })
    tokenStore.set(res.access_token)
    setUser(res.user)
    return res.user
  }, [])

  const adopt = useCallback((token: string, u: User) => {
    tokenStore.set(token)
    setUser(u)
  }, [])

  const logout = useCallback(() => {
    tokenStore.clear()
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

export const homeFor = (role: User['role']) => (role === 'driver' ? '/driver' : '/office')
