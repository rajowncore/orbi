import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { customers, orders, invoices, inventory } from '../lib/api'
import { fmt, statusBadge } from '../lib/utils'
import { StatCard, LoadingRows } from '../components/ui'

export default function Dashboard() {
  const nav = useNavigate()
  const { data: customerList = [] } = useQuery({ queryKey: ['customers'], queryFn: customers.list })
  const { data: orderList = [] }    = useQuery({ queryKey: ['orders'],    queryFn: orders.list })
  const { data: invoiceList = [] }  = useQuery({ queryKey: ['invoices'],  queryFn: () => invoices.list() })
  const { data: inventoryList = [] }= useQuery({ queryKey: ['inventory'], queryFn: inventory.list })

  const activeOrders  = orderList.filter(o => o.status === 'active')
  const openInvoices  = invoiceList.filter(i => ['draft','sent','finalised'].includes(i.status))
  const recentOrders  = [...orderList].slice(0, 6)
  const availableMSISDN = inventoryList.filter(i => i.type === 'msisdn' && i.status === 'available').length
  const totalMSISDN     = inventoryList.filter(i => i.type === 'msisdn').length

  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">
      {/* KPI row */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatCard label="Total Customers" value={fmt.num(customerList.length)} delta={`${customerList.filter(c=>c.status==='active').length} active`} deltaUp/>
        <StatCard label="Active Orders"   value={fmt.num(activeOrders.length)} delta="this billing period" deltaUp/>
        <StatCard label="Open Invoices"   value={fmt.num(openInvoices.length)} delta={fmt.money(openInvoices.reduce((s,i)=>s+i.total,0))} deltaUp={false}/>
        <StatCard label="MSISDN Available" value={fmt.num(availableMSISDN)} delta={`of ${fmt.num(totalMSISDN)} total`} deltaUp={availableMSISDN > totalMSISDN * 0.2}/>
      </div>

      <div className="grid grid-cols-3 gap-5">
        {/* Recent orders */}
        <div className="col-span-2 card">
          <div className="card-header">
            <span className="card-title">Recent Orders</span>
            <button className="btn btn-ghost btn-sm" onClick={() => nav('/orders')}>View all</button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead><tr>
                <th className="table-th">Order</th>
                <th className="table-th">Customer</th>
                <th className="table-th">Status</th>
                <th className="table-th">Created</th>
              </tr></thead>
              <tbody>
                {recentOrders.length === 0 ? (
                  <tr><td colSpan={4} className="table-td text-center text-slate-400 py-8">No orders yet</td></tr>
                ) : recentOrders.map(o => (
                  <tr key={o.id} className="table-row" onClick={() => nav('/orders')}>
                    <td className="table-td font-mono text-xs text-slate-500">{o.order_number}</td>
                    <td className="table-td">{o.customer_id.slice(0,8)}…</td>
                    <td className="table-td"><span className={`badge ${statusBadge(o.status)}`}>{o.status}</span></td>
                    <td className="table-td text-slate-500">{fmt.date(o.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Quick actions */}
        <div className="flex flex-col gap-4">
          <div className="card">
            <div className="card-header"><span className="card-title">Quick Actions</span></div>
            <div className="card-body grid grid-cols-2 gap-2">
              {[
                { label: 'New Customer',    to: '/customers' },
                { label: 'New Order',       to: '/orders' },
                { label: 'Run Billing',     to: '/invoices' },
                { label: 'Upload Usage',    to: '/usage' },
                { label: 'Add MSISDN',      to: '/inventory' },
                { label: 'Record Payment',  to: '/payments' },
              ].map(a => (
                <button key={a.label} onClick={() => nav(a.to)}
                  className="flex items-center justify-center text-xs font-medium text-slate-600 bg-slate-50 border border-slate-200 rounded-lg p-3 hover:border-brand-500 hover:bg-brand-50 hover:text-brand-600 transition-all cursor-pointer">
                  {a.label}
                </button>
              ))}
            </div>
          </div>

          {/* Inventory snapshot */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">Inventory</span>
              <button className="btn btn-ghost btn-sm" onClick={() => nav('/inventory')}>Manage</button>
            </div>
            <div className="card-body space-y-3">
              {['msisdn','sim'].map(type => {
                const items = inventoryList.filter(i => i.type === type)
                const avail = items.filter(i => i.status === 'available').length
                const pct   = items.length ? (1 - avail/items.length) * 100 : 0
                return (
                  <div key={type}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="font-medium text-slate-600 uppercase">{type}</span>
                      <span className="text-slate-400">{avail} available / {items.length} total</span>
                    </div>
                    <div className="usage-track">
                      <div className="usage-fill" style={{ width:`${pct}%`, background: pct > 85 ? '#D97706' : '#1B4FD8' }}/>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
