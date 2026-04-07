// src/lib/auth.jsx
// Simple token-based auth — stores API key in localStorage
// Replace with proper JWT in Phase 2

import { createContext, useContext, useState, useEffect } from 'react'
import axios from 'axios'

const AuthContext = createContext(null)

const TOKEN_KEY = 'orbi_token'
const USER_KEY  = 'orbi_user'

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY))
  const [user,  setUser]  = useState(() => {
    try { return JSON.parse(localStorage.getItem(USER_KEY)) } catch { return null }
  })

  // Inject token into every axios request
  useEffect(() => {
    const id = axios.interceptors.request.use(cfg => {
      if (token) cfg.headers['X-API-Key'] = token
      return cfg
    })
    return () => axios.interceptors.request.eject(id)
  }, [token])

  const login = async (username, password) => {
    // MVP: match against env-configured credentials
    // In Phase 2 this hits POST /api/v1/auth/login
    const valid = username === (import.meta.env.VITE_ADMIN_USER || 'admin') &&
                  password === (import.meta.env.VITE_ADMIN_PASS || 'orbi2026')
    if (!valid) throw new Error('Invalid username or password')

    const tok  = `orbi-${btoa(username + ':' + Date.now())}`
    const usr  = { username, role: 'operator' }
    localStorage.setItem(TOKEN_KEY, tok)
    localStorage.setItem(USER_KEY, JSON.stringify(usr))
    setToken(tok)
    setUser(usr)
    return usr
  }

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    setToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ token, user, login, logout, isAuthenticated: !!token }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
