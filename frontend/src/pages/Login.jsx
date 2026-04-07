// src/pages/Login.jsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'

export default function Login() {
  const { login } = useAuth()
  const nav = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error,    setError]    = useState('')
  const [loading,  setLoading]  = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      nav('/', { replace: true })
    } catch (err) {
      setError(err.message || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">

        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-brand-500 mb-4">
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none"
              stroke="white" strokeWidth="2.5" strokeLinecap="round">
              <circle cx="12" cy="12" r="3"/>
              <path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>
              <path d="M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>
            </svg>
          </div>
          <div className="text-2xl font-semibold text-slate-900">Orbi Billing</div>
          <div className="text-sm text-slate-400 mt-1">Customer Management</div>
        </div>

        {/* Card */}
        <div className="card">
          <div className="card-body">
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="form-label">Username</label>
                <input className="form-input" type="text" autoFocus
                  value={username} onChange={e => setUsername(e.target.value)}
                  placeholder="admin" required/>
              </div>
              <div>
                <label className="form-label">Password</label>
                <input className="form-input" type="password"
                  value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••" required/>
              </div>

              {error && (
                <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2 rounded-lg">
                  {error}
                </div>
              )}

              <button type="submit" className="btn btn-primary w-full justify-center py-2.5"
                disabled={loading}>
                {loading ? 'Signing in…' : 'Sign in'}
              </button>
            </form>
          </div>
        </div>

        <div className="text-center mt-6 text-xs text-slate-400">
          Default credentials: <span className="font-mono">admin / orbi2026</span>
        </div>
      </div>
    </div>
  )
}
