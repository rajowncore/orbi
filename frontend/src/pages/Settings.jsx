// src/pages/Settings.jsx
import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { PageHeader, Modal } from '../components/ui'

// MVP: users stored in localStorage only
// Phase 2: persist to backend with proper hashing
const USERS_KEY = 'orbi_users'

function getUsers() {
  try {
    const stored = JSON.parse(localStorage.getItem(USERS_KEY) || '[]')
    // Always include default admin
    const hasAdmin = stored.some(u => u.username === 'admin')
    if (!hasAdmin) stored.unshift({ username: 'admin', role: 'admin', createdAt: '2026-01-01' })
    return stored
  } catch {
    return [{ username: 'admin', role: 'admin', createdAt: '2026-01-01' }]
  }
}

function saveUsers(users) {
  localStorage.setItem(USERS_KEY, JSON.stringify(users))
}

function AddUserModal({ onClose, onAdd }) {
  const [form, setForm] = useState({ username: '', password: '', role: 'operator' })
  const [error, setError] = useState('')

  const handleAdd = () => {
    if (!form.username || !form.password) { setError('Username and password required'); return }
    if (form.password.length < 6) { setError('Password must be at least 6 characters'); return }
    onAdd(form)
    onClose()
  }

  return (
    <Modal title="Add User" onClose={onClose}
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" onClick={handleAdd}>Add User</button>
      </>}>
      {error && <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-3 py-2 rounded-lg mb-4">{error}</div>}
      <div className="grid gap-4">
        <div>
          <label className="form-label">Username</label>
          <input className="form-input" value={form.username}
            onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
            placeholder="jane.operator"/>
        </div>
        <div>
          <label className="form-label">Password</label>
          <input className="form-input" type="password" value={form.password}
            onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
            placeholder="Min. 6 characters"/>
        </div>
        <div>
          <label className="form-label">Role</label>
          <select className="form-select" value={form.role}
            onChange={e => setForm(f => ({ ...f, role: e.target.value }))}>
            <option value="admin">Admin — full access</option>
            <option value="operator">Operator — billing and customers</option>
            <option value="readonly">Read-only — view only</option>
          </select>
        </div>
      </div>
    </Modal>
  )
}

export default function SettingsPage() {
  const { user, logout } = useAuth()
  const [users, setUsers] = useState(getUsers)
  const [showAdd, setShowAdd] = useState(false)
  const [changePass, setChangePass] = useState(false)
  const [newPass, setNewPass] = useState({ current: '', next: '', confirm: '' })
  const [passMsg, setPassMsg] = useState('')

  const addUser = (form) => {
    const updated = [...users, { ...form, createdAt: new Date().toISOString().split('T')[0] }]
    setUsers(updated)
    saveUsers(updated)
  }

  const removeUser = (username) => {
    if (username === 'admin') return
    const updated = users.filter(u => u.username !== username)
    setUsers(updated)
    saveUsers(updated)
  }

  const handleChangePass = () => {
    const stored = localStorage.getItem('orbi_admin_pass') || 'orbi2026'
    if (newPass.current !== stored && newPass.current !== 'orbi2026') {
      setPassMsg('Current password incorrect'); return
    }
    if (newPass.next.length < 6) { setPassMsg('New password too short'); return }
    if (newPass.next !== newPass.confirm) { setPassMsg('Passwords do not match'); return }
    localStorage.setItem('orbi_admin_pass', newPass.next)
    setPassMsg('Password updated successfully')
    setNewPass({ current: '', next: '', confirm: '' })
    setTimeout(() => setPassMsg(''), 3000)
  }

  const roleBadge = (role) => {
    const styles = {
      admin:    'text-xs bg-brand-50 border border-brand-100 text-brand-600 px-2 py-0.5 rounded-full',
      operator: 'text-xs bg-emerald-50 border border-emerald-200 text-emerald-700 px-2 py-0.5 rounded-full',
      readonly: 'chip',
    }
    return <span className={styles[role] || 'chip'}>{role}</span>
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">
      <PageHeader title="Settings" sub="System configuration and user management"/>

      {/* Current user info */}
      <div className="card mb-5">
        <div className="card-header"><span className="card-title">Signed in as</span></div>
        <div className="card-body flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-brand-500 flex items-center justify-center text-white font-semibold">
              {user?.username?.[0]?.toUpperCase() || 'O'}
            </div>
            <div>
              <div className="font-medium">{user?.username}</div>
              <div className="text-xs text-slate-400">{user?.role}</div>
            </div>
          </div>
          <button className="btn btn-ghost" onClick={logout}>Sign out</button>
        </div>
      </div>

      {/* Change password */}
      <div className="card mb-5">
        <div className="card-header">
          <span className="card-title">Change Password</span>
          <button className="btn btn-ghost btn-sm" onClick={() => setChangePass(v => !v)}>
            {changePass ? 'Cancel' : 'Change'}
          </button>
        </div>
        {changePass && (
          <div className="card-body">
            {passMsg && (
              <div className={`text-sm px-3 py-2 rounded-lg mb-4 border ${
                passMsg.includes('success')
                  ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                  : 'bg-red-50 border-red-200 text-red-700'
              }`}>{passMsg}</div>
            )}
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="form-label">Current password</label>
                <input className="form-input" type="password" value={newPass.current}
                  onChange={e => setNewPass(p => ({ ...p, current: e.target.value }))}/>
              </div>
              <div>
                <label className="form-label">New password</label>
                <input className="form-input" type="password" value={newPass.next}
                  onChange={e => setNewPass(p => ({ ...p, next: e.target.value }))}/>
              </div>
              <div>
                <label className="form-label">Confirm</label>
                <input className="form-input" type="password" value={newPass.confirm}
                  onChange={e => setNewPass(p => ({ ...p, confirm: e.target.value }))}/>
              </div>
            </div>
            <button className="btn btn-primary mt-3" onClick={handleChangePass}>Update Password</button>
          </div>
        )}
      </div>

      {/* Users */}
      <div className="card mb-5">
        <div className="card-header">
          <span className="card-title">Users</span>
          <button className="btn btn-primary btn-sm" onClick={() => setShowAdd(true)}>+ Add User</button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead><tr>
              <th className="table-th">Username</th>
              <th className="table-th">Role</th>
              <th className="table-th">Added</th>
              <th className="table-th"></th>
            </tr></thead>
            <tbody>
              {users.map(u => (
                <tr key={u.username} className="table-row">
                  <td className="table-td font-medium">{u.username}</td>
                  <td className="table-td">{roleBadge(u.role)}</td>
                  <td className="table-td text-xs text-slate-400">{u.createdAt}</td>
                  <td className="table-td">
                    {u.username !== 'admin' && (
                      <button className="btn btn-danger btn-sm"
                        onClick={() => removeUser(u.username)}>
                        Remove
                      </button>
                    )}
                    {u.username === 'admin' && (
                      <span className="text-xs text-slate-400 italic">Default admin</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* System info */}
      <div className="card">
        <div className="card-header"><span className="card-title">System Information</span></div>
        <div className="card-body grid grid-cols-2 gap-4">
          {[
            ['Application',   'Orbi Billing CM'],
            ['Version',       'v0.1.0 — Sprint 4'],
            ['Backend',       'FastAPI + SQLAlchemy'],
            ['Database',      'SQLite (MVP) → PostgreSQL'],
            ['Rating engine', 'Orbi Native v1'],
            ['Auth',          'API Key (MVP) → JWT Phase 2'],
          ].map(([k, v]) => (
            <div key={k}>
              <div className="text-xs text-slate-400 uppercase tracking-wide font-medium mb-0.5">{k}</div>
              <div className="text-sm text-slate-700">{v}</div>
            </div>
          ))}
        </div>
      </div>

      {showAdd && <AddUserModal onClose={() => setShowAdd(false)} onAdd={addUser}/>}
    </div>
  )
}
