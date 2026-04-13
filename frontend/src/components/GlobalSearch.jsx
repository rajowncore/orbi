// src/components/GlobalSearch.jsx
// Press Cmd/Ctrl+K or click the search icon to open.
// Searches across customers, orders, products, and inventory in real time.

import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { customers, orders, products, inventory } from '../lib/api'
import { statusBadge } from '../lib/utils'

function highlight(text, query) {
  if (!query || !text) return text
  const idx = String(text).toLowerCase().indexOf(query.toLowerCase())
  if (idx === -1) return text
  const s = String(text)
  return <>{s.slice(0, idx)}<mark className="bg-brand-100 text-brand-800 rounded">{s.slice(idx, idx + query.length)}</mark>{s.slice(idx + query.length)}</>
}

export function GlobalSearch() {
  const [open,  setOpen]  = useState(false)
  const [query, setQuery] = useState('')
  const [sel,   setSel]   = useState(0)
  const inputRef = useRef(null)
  const nav = useNavigate()

  // Keyboard shortcut Cmd/Ctrl+K
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen(o => !o)
      }
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // Focus input when opened
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50)
    } else {
      setQuery('')
      setSel(0)
    }
  }, [open])

  // Load all data (cached by TanStack Query)
  const { data: custList = [] }  = useQuery({ queryKey: ['customers'], queryFn: () => customers.list(),  enabled: open })
  const { data: orderList = [] } = useQuery({ queryKey: ['orders'],    queryFn: () => orders.list(),    enabled: open })
  const { data: prodList = [] }  = useQuery({ queryKey: ['products'],  queryFn: () => products.list(),  enabled: open })
  const { data: invList = [] }   = useQuery({ queryKey: ['inventory'], queryFn: () => inventory.list(), enabled: open })

  const results = useMemo(() => {
    if (!query.trim()) return []
    const q = query.toLowerCase()
    const hits = []

    custList.forEach(c => {
      if (c.name?.toLowerCase().includes(q) || c.email?.toLowerCase().includes(q) || c.phone?.includes(q)) {
        hits.push({ type:'Customer', label: c.name, sub: c.email, status: c.status, path: `/customers/${c.id}`, match: q })
      }
    })
    orderList.forEach(o => {
      if (o.order_number?.toLowerCase().includes(q) || o.id?.includes(q)) {
        hits.push({ type:'Order', label: o.order_number, sub: o.customer_id?.slice(0,8)+'…', status: o.status, path: `/orders`, match: q })
      }
    })
    prodList.forEach(p => {
      if (p.name?.toLowerCase().includes(q) || p.description?.toLowerCase().includes(q)) {
        hits.push({ type:'Product', label: p.name, sub: p.product_type, status: p.status, path: `/products/${p.id}`, match: q })
      }
    })
    invList.forEach(i => {
      if (i.value?.toLowerCase().includes(q)) {
        hits.push({ type:'MSISDN/SIM', label: i.value, sub: i.type, status: i.status, path: `/inventory/${i.id}`, match: q })
      }
    })

    return hits.slice(0, 12)
  }, [query, custList, orderList, prodList, invList])

  const go = (path) => {
    nav(path)
    setOpen(false)
  }

  // Keyboard nav
  const onKey = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel(s => Math.min(s + 1, results.length - 1)) }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setSel(s => Math.max(s - 1, 0)) }
    if (e.key === 'Enter' && results[sel]) go(results[sel].path)
  }

  const typeColors = {
    'Customer':  'bg-brand-50 text-brand-700',
    'Order':     'bg-amber-50 text-amber-700',
    'Product':   'bg-emerald-50 text-emerald-700',
    'MSISDN/SIM':'bg-sky-50 text-sky-700',
  }

  return (
    <>
      {/* Trigger button in sidebar / topbar */}
      <button onClick={() => setOpen(true)}
        className="flex items-center gap-2 text-white/40 hover:text-white/70 transition-colors text-xs px-2 py-1.5 rounded-md hover:bg-white/10 w-full">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <span>Search</span>
        <span className="ml-auto text-white/20 font-mono text-[10px] border border-white/10 px-1 rounded">⌘K</span>
      </button>

      {/* Modal */}
      {open && (
        <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && setOpen(false)}>
          <div className="modal slide-in" style={{maxWidth: 560}}>
            {/* Search input */}
            <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-200">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="text-slate-400 flex-shrink-0">
                <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
              <input ref={inputRef}
                className="flex-1 text-sm outline-none bg-transparent text-slate-900 placeholder-slate-400"
                placeholder="Search customers, orders, products, MSISDNs…"
                value={query}
                onChange={e => { setQuery(e.target.value); setSel(0) }}
                onKeyDown={onKey}/>
              <kbd className="text-xs text-slate-400 border border-slate-200 px-1.5 py-0.5 rounded">Esc</kbd>
            </div>

            {/* Results */}
            <div style={{maxHeight: 400, overflowY: 'auto'}}>
              {query.trim() === '' ? (
                <div className="px-4 py-8 text-center text-sm text-slate-400">
                  Type to search across all entities
                </div>
              ) : results.length === 0 ? (
                <div className="px-4 py-8 text-center text-sm text-slate-400">
                  No results for "{query}"
                </div>
              ) : results.map((r, i) => (
                <div key={i}
                  className={`flex items-center gap-3 px-4 py-3 cursor-pointer transition-colors border-b border-slate-50 ${i === sel ? 'bg-brand-50' : 'hover:bg-slate-50'}`}
                  onClick={() => go(r.path)}
                  onMouseEnter={() => setSel(i)}>
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded-full flex-shrink-0 ${typeColors[r.type] || 'bg-slate-100 text-slate-600'}`}>
                    {r.type}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-slate-900 truncate">
                      {highlight(r.label, query)}
                    </div>
                    {r.sub && (
                      <div className="text-xs text-slate-400 truncate">
                        {highlight(r.sub, query)}
                      </div>
                    )}
                  </div>
                  {r.status && (
                    <span className={`badge ${statusBadge(r.status)} flex-shrink-0`}>{r.status}</span>
                  )}
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-slate-300 flex-shrink-0">
                    <polyline points="9 18 15 12 9 6"/>
                  </svg>
                </div>
              ))}
            </div>

            {results.length > 0 && (
              <div className="px-4 py-2 border-t border-slate-100 flex items-center gap-3 text-xs text-slate-400">
                <span>↑↓ navigate</span>
                <span>↵ open</span>
                <span>Esc close</span>
                <span className="ml-auto">{results.length} result{results.length !== 1 ? 's' : ''}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  )
}
