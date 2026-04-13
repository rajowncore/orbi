// src/components/ui/Toast.jsx
// Lightweight toast system — no external dependency.
// Usage:
//   import { useToast } from './Toast'
//   const toast = useToast()
//   toast.success('Customer saved')
//   toast.error('Insufficient balance: £19.99 required, £0.00 available')
//   toast.warn('CGRateS unreachable — using native rater')

import { createContext, useContext, useState, useCallback, useEffect } from 'react'

const ToastContext = createContext(null)

let _nextId = 1

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const add = useCallback((message, type = 'info', duration = 4000) => {
    const id = _nextId++
    setToasts(t => [...t, { id, message, type }])
    if (duration > 0) {
      setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), duration)
    }
    return id
  }, [])

  const remove = useCallback((id) => setToasts(t => t.filter(x => x.id !== id)), [])

  const api = {
    success: (msg, dur)  => add(msg, 'success', dur),
    error:   (msg, dur)  => add(msg, 'error',   dur ?? 6000),
    warn:    (msg, dur)  => add(msg, 'warn',     dur ?? 5000),
    info:    (msg, dur)  => add(msg, 'info',     dur),
    remove,
  }

  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastContainer toasts={toasts} onRemove={remove}/>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be inside ToastProvider')
  return ctx
}

const ICONS = {
  success: <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="20 6 9 17 4 12"/></svg>,
  error:   <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>,
  warn:    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>,
  info:    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>,
}

const STYLES = {
  success: 'bg-emerald-50 border-emerald-300 text-emerald-800',
  error:   'bg-red-50 border-red-300 text-red-800',
  warn:    'bg-amber-50 border-amber-300 text-amber-800',
  info:    'bg-brand-50 border-brand-200 text-brand-800',
}

function ToastContainer({ toasts, onRemove }) {
  if (!toasts.length) return null
  return (
    <div style={{ position:'fixed', bottom:24, right:24, zIndex:9999,
                  display:'flex', flexDirection:'column', gap:8, maxWidth:400 }}>
      {toasts.map(t => (
        <div key={t.id}
          className={`flex items-start gap-3 px-4 py-3 rounded-xl border shadow-lg text-sm slide-in ${STYLES[t.type]}`}>
          <span className="flex-shrink-0 mt-0.5">{ICONS[t.type]}</span>
          <span className="flex-1 leading-snug">{t.message}</span>
          <button onClick={() => onRemove(t.id)}
            className="flex-shrink-0 opacity-50 hover:opacity-100 transition-opacity ml-1">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
      ))}
    </div>
  )
}
