import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import {
  customers as customersApi,
  subscriptions as subsApi,
  products as productsApi,
  orders as ordersApi,
  payments as paymentsApi,
  billingRuns,
  invoices as invoicesApi,						  
} from '../lib/api'
import { fmt, statusBadge } from '../lib/utils'
import {
  LoadingRows, Empty, Spinner, ErrorBanner,
  PageHeader, Modal, Confirm,
} from '../components/ui'
import { CreateCustomerModal } from '../components/modals/CreateCustomerModal'
import { CreateOrderModal } from '../components/modals/CreateOrderModal'
import { useToast } from '../components/ui/Toast'												 
import { ProvisioningPanel } from '../components/ProvisioningPanel'
import { RecordPaymentModal } from '../components/modals/RecordPaymentModal'

// ── Edit Customer Modal ────────────────────────────────────────────────────
function EditCustomerModal({ customer, onClose }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    name:              customer.name,
    phone:             customer.phone || '',
    address:           customer.address || '',
    billing_cycle_day: customer.billing_cycle_day,
    status:            customer.status,
  })

  const mut = useMutation({
    mutationFn: (data) => customersApi.update(customer.id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['customer', customer.id] })
      qc.invalidateQueries({ queryKey: ['customers'] })
      onClose()
    }
  })

  const F = ({ label, name, type = 'text', opts }) => (
    <div>
      <label className="form-label">{label}</label>
      {name === 'status' ? (
        <select className="form-select" value={form[name]}
          onChange={e => setForm(f => ({ ...f, [name]: e.target.value }))}>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
          <option value="closed">Closed</option>
        </select>
      ) : name === 'address' ? (
        <textarea className="form-input" rows={2} value={form[name]}
          onChange={e => setForm(f => ({ ...f, [name]: e.target.value }))}/>
      ) : (
        <input className="form-input" type={type} value={form[name]}
          onChange={e => setForm(f => ({ ...f, [name]: e.target.value }))} {...opts}/>
      )}
    </div>
  )

  return (
    <Modal title="Edit Customer" onClose={onClose}
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" disabled={mut.isPending}
          onClick={() => mut.mutate(form)}>
          {mut.isPending ? 'Saving…' : 'Save Changes'}
        </button>
      </>}>
      <ErrorBanner message={mut.error}/>
      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2"><F label="Full Name" name="name"/></div>
        <F label="Phone" name="phone"/>
        <F label="Billing Cycle Day" name="billing_cycle_day" type="number" opts={{ min:1, max:28 }}/>
        <div className="col-span-2"><F label="Address" name="address"/></div>
        <F label="Status" name="status"/>
      </div>
    </Modal>
  )
}

// ── Customer List ──────────────────────────────────────────────────────────
export function CustomersPage() {
  const nav = useNavigate()
  const [showCreate, setShowCreate] = useState(false)
  const [search, setSearch]         = useState('')
  const [typeFilter, setTypeFilter] = useState('')

  const { data = [], isLoading } = useQuery({ queryKey: ['customers'], queryFn: () => customersApi.list() })

  const filtered = data.filter(c => {
    const ms = !search || c.name.toLowerCase().includes(search.toLowerCase()) || c.email.toLowerCase().includes(search.toLowerCase())
    return ms && (!typeFilter || c.credit_type === typeFilter)
  })

  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">
      <PageHeader title="Customers" sub={`${data.length} total`}>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>+ New Customer</button>
      </PageHeader>
      <div className="card">
        <div className="card-header">
          <span className="card-title">All Customers</span>
          <div className="flex gap-2">
            <input className="form-input" style={{width:220}} value={search}
              onChange={e=>setSearch(e.target.value)} placeholder="Search name, email…"/>
            <select className="form-select" style={{width:130}} value={typeFilter} onChange={e=>setTypeFilter(e.target.value)}>
              <option value="">All types</option>
              <option value="postpaid">Postpaid</option>
              <option value="prepaid">Prepaid</option>
            </select>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead><tr>
              <th className="table-th">Customer</th><th className="table-th">Email</th>
              <th className="table-th">Type</th><th className="table-th">Status</th>
              <th className="table-th">Since</th>
            </tr></thead>
            <tbody>
              {isLoading ? <LoadingRows cols={5}/> : filtered.length === 0 ? (
                <tr><td colSpan={5}><Empty title="No customers found" sub={search?'Try a different search':'Create your first customer'}/></td></tr>
              ) : filtered.map(c => (
                <tr key={c.id} className="table-row" onClick={()=>nav(`/customers/${c.id}`)}>
                  <td className="table-td">
                    <div className="font-medium">{c.name}</div>
                    {c.phone&&<div className="text-xs text-slate-400">{c.phone}</div>}
                  </td>
                  <td className="table-td text-slate-500">{c.email}</td>
                  <td className="table-td">
                    <span className={c.credit_type==='prepaid'?'text-xs bg-brand-50 border border-brand-100 text-brand-600 px-2 py-0.5 rounded-full':'chip'}>{c.credit_type}</span>
                  </td>
                  <td className="table-td"><span className={`badge ${statusBadge(c.status)}`}>{c.status}</span></td>
                  <td className="table-td text-slate-400 text-xs">{fmt.date(c.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {showCreate && <CreateCustomerModal onClose={()=>setShowCreate(false)}/>}
    </div>
  )
}


// ── Billing Run Modal (per-customer) ──────────────────────────────────────
function BillingRunModal({ customerId, onClose, onRun, loading }) {
  const [start, setStart] = useState('')
  const [end,   setEnd]   = useState('')
  const [result, setResult] = useState(null)

  const today = new Date()
  const firstOfMonth = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-01`
  const lastOfMonth  = new Date(today.getFullYear(), today.getMonth()+1, 0).toISOString().split('T')[0]

  const handleRun = async () => {
    const s = start || firstOfMonth
    const e = end   || lastOfMonth
    onRun({ period_start: s, period_end: e })
    onClose()
  }

  return (
    <Modal title="Generate Invoice" onClose={onClose}
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" disabled={loading} onClick={handleRun}>
          {loading ? 'Running…' : '▶ Generate'}
        </button>
      </>}>
      <p className="text-sm text-slate-500 mb-4">
        Generate an invoice for this customer covering the selected billing period.
        All unbilled charges and usage events will be included.
      </p>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="form-label">Period Start</label>
          <input className="form-input" type="date"
            value={start || firstOfMonth}
            onChange={e => setStart(e.target.value)}/>
        </div>
        <div>
          <label className="form-label">Period End</label>
          <input className="form-input" type="date"
            value={end || lastOfMonth}
            onChange={e => setEnd(e.target.value)}/>
        </div>
      </div>
      <div className="mt-3 bg-brand-50 border border-brand-100 rounded-lg px-3 py-2 text-xs text-brand-700">
        Defaults to current month. Change the dates to re-bill a previous period.
      </div>
    </Modal>
  )
}

// ── Customer 360 Detail ────────────────────────────────────────────────────
export function CustomerDetailPage() {
  const { id } = useParams()
  const nav    = useNavigate()
  const qc     = useQueryClient()
  const toast  = useToast()
  const [showOrder, setShowOrder] = useState(false)
  const [showEdit,  setShowEdit]  = useState(false)
  const [confirm,   setConfirm]   = useState(null)

  const [showPayment, setShowPayment] = useState(false)
  const [showBillingRun, setShowBillingRun] = useState(false)
  const [billingResult, setBillingResult] = useState(null)
  const [actionError, setActionError] = useState(null)
  
  const { data: customer, isLoading } = useQuery({ queryKey: ['customer', id], queryFn: () => customersApi.get(id) })
  const { data: custOrders   = [] }   = useQuery({ queryKey: ['customer-orders', id],   queryFn: () => customersApi.orders(id) })
  const { data: custInvoices = [] }   = useQuery({ queryKey: ['customer-invoices', id], queryFn: () => customersApi.invoices(id) })
  const { data: balance }             = useQuery({ queryKey: ['balance', id],            queryFn: () => customersApi.balance(id) })
  const { data: subscriptions = [] }  = useQuery({ queryKey: ['subscriptions', id],     queryFn: () => subsApi.list(id) })
  const { data: custPayments = [] }    = useQuery({ queryKey: ['customer-payments', id],  queryFn: () => paymentsApi.list(id) })
  const { data: productList = [] }    = useQuery({ queryKey: ['products'],               queryFn: () => productsApi.list() })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['customer-orders', id] })
    qc.invalidateQueries({ queryKey: ['subscriptions', id] })
    qc.invalidateQueries({ queryKey: ['inventory'] })
  }

  const billingMut = useMutation({
    mutationFn: (data) => billingRuns.trigger(data),
    onSuccess: (result) => {
      setBillingResult(result)
      qc.invalidateQueries({ queryKey: ['customer-invoices', id] })
      qc.invalidateQueries({ queryKey: ['balance', id] })
    }
  })

  // Activate a pending order
  const activateOrderMut = useMutation({
    mutationFn: (orderId) => ordersApi.action(orderId, 'activate'),
    onSuccess: () => { invalidate(); setActionError(''); toast.success('Order activated successfully') },
    onError: (err) => {
      const msg = typeof err === 'string' ? err : (err?.message || 'Activation failed')
      setActionError(msg)
      toast.error(`Activation failed: ${msg}`)
    },
  })

  // Subscription actions — routed through the order (backend couples them for now)
  const subActionMut = useMutation({
    mutationFn: async ({ subId, action }) => {
      const sub = subscriptions.find(s => s.id === subId)
      if (!sub?.order_id) throw new Error('No order found for subscription')
      return ordersApi.action(sub.order_id, action)
    },
    onSuccess: (_, vars) => {
      invalidate(); setConfirm(null); setActionError('')
      const labels = { activate: 'reactivated', suspend: 'suspended', cancel: 'cancelled' }
      toast.success(`Subscription ${labels[vars.action] || vars.action}`)
    },
    onError: (err) => {
      const msg = typeof err === 'string' ? err : (err?.message || 'Action failed')
      setConfirm(null)
      setActionError(msg)
      toast.error(msg)
    },
  })

  if (isLoading) return <div className="flex-1 flex items-center justify-center"><Spinner size={32}/></div>
  if (!customer) return <div className="flex-1 p-6 text-slate-400">Customer not found</div>

  const enrichedSubs = subscriptions.map(s => ({
    ...s,
    product: productList.find(p => p.id === s.product_id),
    order:   custOrders.find(o => o.id === s.order_id),
  }))
  const activeSubs    = enrichedSubs.filter(s => s.status === 'active')
  const inactiveSubs  = enrichedSubs.filter(s => s.status !== 'active')
  const pendingOrders = custOrders.filter(o => o.status === 'pending')

  const typePill = (type) => {
    const s = { base:'chip', addon:'text-xs bg-amber-50 border border-amber-200 text-amber-700 px-2 py-0.5 rounded-full', roaming:'text-xs bg-sky-50 border border-sky-200 text-sky-700 px-2 py-0.5 rounded-full' }
    return <span className={s[type]||'chip'}>{type||'—'}</span>
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">

      {/* Header */}
      <div className="flex items-start gap-3 mb-5">
        <button className="btn btn-ghost btn-sm mt-0.5" onClick={()=>nav('/customers')}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="15 18 9 12 15 6"/></svg>
          Back
        </button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold">{customer.name}</h1>
            <span className={`badge ${statusBadge(customer.status)}`}>{customer.status}</span>
            <span className={customer.credit_type==='prepaid'?'text-xs bg-brand-50 border border-brand-100 text-brand-600 px-2 py-0.5 rounded-full':'chip'}>{customer.credit_type}</span>
          </div>
          <div className="text-xs text-slate-400 mt-1">{customer.email} · Customer since {fmt.date(customer.created_at)}</div>
        </div>
        <div className="flex gap-2">
          <button className="btn btn-ghost" onClick={()=>setShowPayment(true)}>+ Payment</button>
          <button className="btn btn-ghost" onClick={()=>setShowBillingRun(true)}>Generate Invoice</button>
          <button className="btn btn-ghost" onClick={()=>setShowEdit(true)}>Edit</button>
          <button className="btn btn-primary" onClick={()=>setShowOrder(true)}>+ New Order</button>
        </div>
      </div>


		{/* Action error banner */}
      {actionError && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-5 py-4 mb-4 flex items-start gap-3">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#DC2626" strokeWidth="2.5" strokeLinecap="round" className="flex-shrink-0 mt-0.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
          <div className="flex-1">
            <div className="text-sm font-semibold text-red-800">Action failed</div>
            <div className="text-sm text-red-700 mt-0.5">{actionError}</div>
          </div>
          <button onClick={()=>setActionError('')} className="text-red-400 hover:text-red-600">×</button>
        </div>
      )}						 
      {/* Billing run result */}
      {billingResult && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-5 py-4 mb-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-emerald-800">
                Billing run complete — {billingResult.invoices_created} invoice{billingResult.invoices_created !== 1 ? 's' : ''} generated
              </div>
              <div className="text-xs text-emerald-600 mt-0.5">
                {billingResult.recurring_charges_generated} recurring charges · {billingResult.usage_events_rated} usage events rated · {billingResult.duration_seconds}s
              </div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => setBillingResult(null)}>Dismiss</button>
          </div>
        </div>
      )}

      {/* Pending orders banner */}
      {pendingOrders.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-4 mb-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-semibold text-amber-800">
                {pendingOrders.length} pending order{pendingOrders.length>1?'s':''} awaiting activation
              </div>
              <div className="text-xs text-amber-600 mt-0.5">Activate to assign inventory and start the subscription.</div>
            </div>
            <div className="flex flex-col gap-2">
              {pendingOrders.map(o => (
                <div key={o.id} className="flex items-center gap-3">
                  <span className="font-mono text-xs text-amber-700">{o.order_number}</span>
                  <span className="text-xs text-amber-600">{productList.find(p=>p.id===o.product_id)?.name||'—'}</span>
                  <button className="btn btn-primary btn-sm" disabled={activateOrderMut.isPending}
                    onClick={()=>activateOrderMut.mutate(o.id)}>
                    {activateOrderMut.isPending?'Activating…':'Activate'}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Profile + Balance */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div className="card">
          <div className="card-header">
            <span className="card-title">Profile</span>
            <button className="btn btn-ghost btn-sm" onClick={()=>setShowEdit(true)}>Edit</button>
          </div>
          <div className="card-body space-y-3">
            {[['Email',customer.email],['Phone',customer.phone||'—'],['Address',customer.address||'—'],['Currency',customer.currency],
              ['Billing day',`${customer.billing_cycle_day}${[,'st','nd','rd'][customer.billing_cycle_day]||'th'} of month`]
            ].map(([l,v])=>(
              <div key={l}>
                <div className="text-xs text-slate-400 uppercase tracking-wide font-medium mb-0.5">{l}</div>
                <div className="text-sm">{v}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="card">
          <div className="card-header"><span className="card-title">Balance & Billing</span></div>
          <div className="card-body space-y-4">
            <div>
              <div className="stat-label">Current Balance</div>
              <div className={`text-2xl font-semibold font-mono mt-1 ${(balance?.balance_cents||0)<0?'text-red-600':'text-slate-900'}`}>
                {fmt.money(balance?.balance_cents||0)}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div><div className="stat-label">Active Subscriptions</div><div className="text-xl font-semibold font-mono mt-1">{activeSubs.length}</div></div>
              <div><div className="stat-label">Open Invoices</div><div className="text-xl font-semibold font-mono mt-1">{custInvoices.filter(i=>['draft','sent','finalised'].includes(i.status)).length}</div></div>
            </div>
          </div>
        </div>
      </div>

      {/* Active Subscriptions */}
      <div className="card mb-4">
        <div className="card-header">
          <span className="card-title">Active Subscriptions</span>
          <button className="btn btn-primary btn-sm" onClick={()=>setShowOrder(true)}>+ Add-on</button>
        </div>
        {activeSubs.length===0 ? (
          <Empty title="No active subscriptions" sub="Create an order and activate it to start a subscription"/>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead><tr>
                <th className="table-th">Package</th><th className="table-th">Type</th>
                <th className="table-th">Allowances</th><th className="table-th">Since</th>
                <th className="table-th">Status</th><th className="table-th">Actions</th>
              </tr></thead>
              <tbody>
                {activeSubs.map(s=>(
                  <tr key={s.id} className="table-row">
                    <td className="table-td">
                      <div className="font-medium">{s.product?.name||'—'}</div>
                      <div className="font-mono text-xs text-slate-400">{s.order?.order_number||s.id.slice(0,8)+'…'}</div>
                    </td>
                    <td className="table-td">{typePill(s.product?.product_type)}</td>
                    <td className="table-td">
                      {s.product?.allowances ? (
                        <div className="text-xs text-slate-500 flex gap-2 flex-wrap">
                          {s.product.allowances.data_mb&&<span>📶 {s.product.allowances.data_mb}MB</span>}
                          {s.product.allowances.voice_mins&&<span>📞 {s.product.allowances.voice_mins}min</span>}
                          {s.product.allowances.sms&&<span>💬 {s.product.allowances.sms}SMS</span>}
                        </div>
                      ):<span className="text-slate-300 text-xs">—</span>}
                    </td>
                    <td className="table-td text-xs text-slate-400">{fmt.date(s.start_date)}</td>
                    <td className="table-td"><span className={`badge ${statusBadge(s.status)}`}>{s.status}</span></td>
                    <td className="table-td">
                      <div className="flex gap-1.5">
                        <button className="btn btn-ghost btn-sm" onClick={()=>setConfirm({
                          subId:s.id, action:'suspend', label:'Suspend subscription',
                          message:`Suspend ${s.product?.name}? Service will pause but the order record stays intact.`
                        })}>Suspend</button>
                        <button className="btn btn-danger btn-sm" onClick={()=>setConfirm({
                          subId:s.id, action:'cancel', label:'Cancel subscription', danger:true,
                          message:`Cancel ${s.product?.name}? This ends the service and releases any assigned MSISDN back to the pool.`
                        })}>Cancel</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Suspended / Cancelled */}
        {inactiveSubs.length>0&&(
          <div className="border-t border-slate-100">
            <div className="px-5 py-2 text-xs font-semibold text-slate-400 uppercase tracking-wide">Suspended / Cancelled</div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead><tr>
                  <th className="table-th">Package</th><th className="table-th">Period</th>
                  <th className="table-th">Status</th><th className="table-th">Actions</th>
                </tr></thead>
                <tbody>
                  {inactiveSubs.map(s=>(
                    <tr key={s.id} className="table-row opacity-70">
                      <td className="table-td">
                        <div className="font-medium text-slate-600">{s.product?.name||'—'}</div>
                        <div className="font-mono text-xs text-slate-400">{s.order?.order_number||'—'}</div>
                      </td>
                      <td className="table-td text-xs text-slate-400">
                        {fmt.date(s.start_date)}{s.end_date?` → ${fmt.date(s.end_date)}`:''}
                      </td>
                      <td className="table-td"><span className={`badge ${statusBadge(s.status)}`}>{s.status}</span></td>
                      <td className="table-td">
                        {s.status==='paused'&&(
                          <button className="btn btn-primary btn-sm" onClick={()=>setConfirm({
                            subId:s.id, action:'activate', label:'Reactivate subscription',
                            message:`Reactivate ${s.product?.name}? Service will resume from today.`
                          })}>Reactivate</button>
                        )}
                        {s.status==='cancelled'&&(
                          <span className="text-xs text-slate-400 italic">Permanently cancelled</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>


	{/* Provisioning */}
      <ProvisioningPanel orders={custOrders}/>					  
      {/* Payments */}
      <div className="card mb-4">
        <div className="card-header">
          <span className="card-title">Payments</span>
          <button className="btn btn-ghost btn-sm" onClick={() => setShowPayment(true)}>+ Record Payment</button>
        </div>
        {custPayments.length === 0 ? (
          <Empty title="No payments recorded" sub="Record a payment or prepaid top-up"/>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead><tr>
                <th className="table-th">Amount</th>
                <th className="table-th">Method</th>
                <th className="table-th">Reference</th>
                <th className="table-th">Date</th>
                <th className="table-th">Invoice</th>
              </tr></thead>
              <tbody>
                {custPayments.map(p => (
                  <tr key={p.id} className="table-row">
                    <td className="table-td font-mono font-medium">{fmt.money(p.amount, p.currency)}</td>
                    <td className="table-td"><span className="chip">{p.method?.replace('_',' ')}</span></td>
                    <td className="table-td font-mono text-xs text-slate-500">{p.reference || '—'}</td>
                    <td className="table-td text-xs text-slate-400">{fmt.date(p.payment_date)}</td>
                    <td className="table-td font-mono text-xs text-slate-400">
                      {p.invoice_id ? p.invoice_id.slice(0,8)+'…' : <span className="italic text-slate-300">Top-up</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Order History */}
      <div className="card mb-4">
        <div className="card-header"><span className="card-title">Order History</span></div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead><tr>
              <th className="table-th">Order</th><th className="table-th">Package</th>
              <th className="table-th">Status</th><th className="table-th">Created</th>
              <th className="table-th">Activated</th>
            </tr></thead>
            <tbody>
              {custOrders.length===0?(
                <tr><td colSpan={5} className="table-td text-center text-slate-400 py-8">No orders</td></tr>
              ):custOrders.map(o=>(
                <tr key={o.id} className="table-row">
                  <td className="table-td font-mono text-xs text-slate-500">{o.order_number}</td>
                  <td className="table-td text-sm">{productList.find(p=>p.id===o.product_id)?.name||<span className="text-slate-400 font-mono text-xs">{o.product_id?.slice(0,8)}…</span>}</td>
                  <td className="table-td"><span className={`badge ${statusBadge(o.status)}`}>{o.status}</span></td>
                  <td className="table-td text-xs text-slate-400">{fmt.date(o.created_at)}</td>
                  <td className="table-td text-xs text-slate-400">{fmt.date(o.activated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Invoices */}
      <div className="card">
        <div className="card-header"><span className="card-title">Invoices</span></div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead><tr>
              <th className="table-th">Invoice</th><th className="table-th">Period</th>
              <th className="table-th">Total</th><th className="table-th">Status</th>
			  <th className="table-th"></th>								
            </tr></thead>
            <tbody>
              {custInvoices.length===0?(
                <tr><td colSpan={4} className="table-td text-center text-slate-400 py-8">No invoices yet</td></tr>
              ):custInvoices.map(inv=>(
                <tr key={inv.id} className="table-row">
                  <td className="table-td font-mono text-xs text-slate-500">{inv.invoice_number}</td>
                  <td className="table-td text-xs text-slate-400">{fmt.date(inv.period_start)} – {fmt.date(inv.period_end)}</td>
                  <td className="table-td font-mono">{fmt.money(inv.total,inv.currency)}</td>
                  <td className="table-td"><span className={`badge ${statusBadge(inv.status)}`}>{inv.status}</span></td>
				  <td className="table-td">
                    <a href={invoicesApi.pdfUrl(inv.id)} target="_blank" rel="noopener noreferrer"
                      className="btn btn-ghost btn-sm flex items-center gap-1" title="Open PDF">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                      PDF
                    </a>
                  </td>						   
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modals */}
      {showOrder&&<CreateOrderModal onClose={()=>setShowOrder(false)} preselectedCustomerId={id}/>}
      {showEdit&&customer&&<EditCustomerModal customer={customer} onClose={()=>setShowEdit(false)}/>}
      {showPayment&&<RecordPaymentModal onClose={()=>{setShowPayment(false);qc.invalidateQueries({queryKey:['customer-payments',id]});qc.invalidateQueries({queryKey:['balance',id]})}} preselectedCustomerId={id}/>}
      {showBillingRun&&<BillingRunModal customerId={id} onClose={()=>setShowBillingRun(false)} onRun={(d)=>billingMut.mutate({...d,customer_id:id})} loading={billingMut.isPending}/>}
      {confirm&&(
        <Confirm title={confirm.label} message={confirm.message} danger={confirm.danger}
          onConfirm={()=>subActionMut.mutate({subId:confirm.subId,action:confirm.action})}
          onCancel={()=>setConfirm(null)}/>
      )}
    </div>
  )
}
