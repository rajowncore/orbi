import { clsx } from '../../lib/utils'

// ── Spinner ────────────────────────────────────────────────────────────────
export function Spinner({ size = 16 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      className="animate-spin text-brand-500" stroke="currentColor" strokeWidth="2.5">
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" strokeLinecap="round"/>
    </svg>
  )
}

// ── Empty state ────────────────────────────────────────────────────────────
export function Empty({ icon, title, sub, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-slate-400">
      {icon && <div className="opacity-30">{icon}</div>}
      <div className="text-sm font-medium text-slate-500">{title}</div>
      {sub && <div className="text-xs">{sub}</div>}
      {action}
    </div>
  )
}

// ── Error banner ───────────────────────────────────────────────────────────
export function ErrorBanner({ message }) {
  if (!message) return null
  return (
    <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-lg mb-4">
      {message}
    </div>
  )
}

// ── Loading rows ───────────────────────────────────────────────────────────
export function LoadingRows({ cols = 4, rows = 5 }) {
  return Array.from({ length: rows }).map((_, i) => (
    <tr key={i}>
      {Array.from({ length: cols }).map((_, j) => (
        <td key={j} className="table-td">
          <div className="h-3.5 bg-slate-100 rounded animate-pulse" style={{ width: `${60 + (j * 15) % 40}%` }}/>
        </td>
      ))}
    </tr>
  ))
}

// ── Modal wrapper ──────────────────────────────────────────────────────────
export function Modal({ title, onClose, children, footer }) {
  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal slide-in">
        <div className="modal-header">
          <span className="modal-title">{title}</span>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-footer">{footer}</div>}
      </div>
    </div>
  )
}

// ── Page header ────────────────────────────────────────────────────────────
export function PageHeader({ title, sub, children }) {
  return (
    <div className="flex items-center justify-between mb-5">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">{title}</h1>
        {sub && <p className="text-xs text-slate-400 mt-0.5">{sub}</p>}
      </div>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </div>
  )
}

// ── Stat card ──────────────────────────────────────────────────────────────
export function StatCard({ label, value, delta, deltaUp, accent }) {
  return (
    <div className="card p-5 relative overflow-hidden">
      <div className="stat-label">{label}</div>
      <div className="stat-value mt-1">{value}</div>
      {delta && (
        <div className={clsx('flex items-center gap-1 text-xs mt-1', deltaUp ? 'text-emerald-600' : 'text-red-500')}>
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <polyline points={deltaUp ? '18 15 12 9 6 15' : '6 9 12 15 18 9'}/>
          </svg>
          {delta}
        </div>
      )}
      {accent && (
        <div className="absolute right-4 top-4 w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: accent.bg }}>
          <span style={{ color: accent.color }}>{accent.icon}</span>
        </div>
      )}
    </div>
  )
}

// ── Usage bar ──────────────────────────────────────────────────────────────
export function UsageBar({ used, total, unit }) {
  const pct = total > 0 ? Math.min(100, (used / total) * 100) : 0
  const color = pct >= 90 ? '#DC2626' : pct >= 70 ? '#D97706' : '#1B4FD8'
  return (
    <div className="flex items-center gap-2 min-w-[110px]">
      <div className="usage-track">
        <div className="usage-fill" style={{ width: `${pct}%`, background: color }}/>
      </div>
      <span className="text-xs text-slate-400 whitespace-nowrap">{used}/{total} {unit}</span>
    </div>
  )
}

// ── Confirm dialog ─────────────────────────────────────────────────────────
export function Confirm({ title, message, onConfirm, onCancel, danger }) {
  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onCancel()}>
      <div className="modal slide-in max-w-sm">
        <div className="modal-header">
          <span className="modal-title">{title}</span>
        </div>
        <div className="modal-body">
          <p className="text-sm text-slate-600">{message}</p>
        </div>
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onCancel}>Cancel</button>
          <button className={clsx('btn', danger ? 'btn-danger' : 'btn-primary')} onClick={onConfirm}>Confirm</button>
        </div>
      </div>
    </div>
  )
}
