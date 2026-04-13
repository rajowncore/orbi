import { Link, useLocation, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../../lib/auth'
import { GlobalSearch } from '../GlobalSearch'											  
import { clsx } from '../../lib/utils'

const nav = [
  { to: '/',           label: 'Dashboard',     icon: GridIcon },
  { to: '/customers',  label: 'Customers',     icon: UsersIcon,   badge: null },
  { to: '/products',   label: 'Products',      icon: BoxIcon },
  { to: '/orders',     label: 'Orders',        icon: CheckIcon },
  { to: '/inventory',  label: 'Inventory',     icon: SimIcon },
]
const navBilling = [
  { to: '/invoices',   label: 'Invoices',      icon: FileIcon },
  { to: '/usage',      label: 'Usage Events',  icon: ActivityIcon },
  { to: '/payments',   label: 'Payments',      icon: CardIcon },
  { to: '/provisioning', label: 'Provisioning',   icon: ServerIcon },
]
const navSystem = [
  { to: '/settings',   label: 'Settings',      icon: SettingsIcon },
]

export default function Layout() {
  const { pathname } = useLocation()
  const { user, logout } = useAuth()
  const isActive = (to) => to === '/' ? pathname === '/' : pathname.startsWith(to)

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <nav className="w-[228px] min-w-[228px] bg-sidebar flex flex-col h-screen overflow-y-auto">
        {/* Logo */}
        <div className="px-4 py-5 border-b border-white/5">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-brand-500 flex items-center justify-center flex-shrink-0">
              <OrbiIcon/>
            </div>
            <div>
              <div className="text-white font-semibold text-[15px] leading-none">Orbi</div>
              <div className="text-white/30 text-[10px] uppercase tracking-widest mt-0.5">Billing CM</div>
            </div>
          </div>
        </div>

        {/* Nav main */}
        <div className="px-3 pt-5 pb-2">
          <div className="text-white/25 text-[10px] uppercase tracking-widest font-semibold px-2 mb-2">Main</div>
          {nav.map(item => (
            <Link key={item.to} to={item.to}
              className={clsx('nav-item', isActive(item.to) && 'active')}>
              <item.icon/>
              <span>{item.label}</span>
            </Link>
          ))}
        </div>

        {/* Nav billing */}
        <div className="px-3 pt-3 pb-2">
          <div className="text-white/25 text-[10px] uppercase tracking-widest font-semibold px-2 mb-2">Billing</div>
          {navBilling.map(item => (
            <Link key={item.to} to={item.to}
              className={clsx('nav-item', isActive(item.to) && 'active')}>
              <item.icon/>
              <span>{item.label}</span>
            </Link>
          ))}
        </div>

        {/* System */}
        <div className="px-3 pt-3 pb-2">
          <div className="text-white/25 text-[10px] uppercase tracking-widest font-semibold px-2 mb-2">System</div>
          {navSystem.map(item => (
            <Link key={item.to} to={item.to}
              className={clsx('nav-item', isActive(item.to) && 'active')}>
              <item.icon/>
              <span>{item.label}</span>
            </Link>
          ))}
        </div>
		
		{/* Search */}
        <div className="px-3 pb-2">
          <GlobalSearch/>
        </div>
		
        {/* Footer */}
        <div className="mt-auto px-3 py-3 border-t border-white/5">
          <div className="flex items-center gap-2.5 px-2.5 py-2">
            <div className="w-7 h-7 rounded-full bg-brand-500 flex items-center justify-center text-white text-xs font-semibold flex-shrink-0">OP</div>
            <div className="text-white/50 text-[12.5px]">Operator</div>
          </div>
        </div>
      </nav>

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <Outlet/>
      </div>
    </div>
  )
}

// ── Icons ─────────────────────────────────────────────────────────────────
function OrbiIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/></svg>
}
function GridIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
}
function UsersIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
}
function BoxIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
}
function CheckIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
}
function SimIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 0 0-4 0v2M12 12v4M8 12v4"/></svg>
}
function FileIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
}
function ActivityIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
}
function CardIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>
}
function ServerIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
}
function SettingsIcon() {
  return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
}
