import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { products as productsApi, orders as ordersApi, inventory as inventoryApi, invoices as invoicesApi, usage as usageApi, payments as paymentsApi, billingRuns } from '../lib/api'
import { fmt, statusBadge } from '../lib/utils'
import { LoadingRows, Empty, ErrorBanner, PageHeader, Confirm, Modal } from '../components/ui'
import { ProvisioningMonitor } from '../components/ProvisioningPanel'																	 
import { CreateProductModal } from '../components/modals/CreateProductModal'
import { CreateOrderModal } from '../components/modals/CreateOrderModal'
import { AddInventoryModal } from '../components/modals/AddInventoryModal'
import { RecordPaymentModal } from '../components/modals/RecordPaymentModal'

// ── Edit Product Modal ────────────────────────────────────────────────────
function EditProductModal({ product, onClose }) {
  const qc = useQueryClient()
  const [form, setForm] = useState({
    name:        product.name,
    description: product.description || '',
    status:      product.status,
    price_amount: product.price_config?.amount ? (product.price_config.amount / 100).toFixed(2) : '',
    data_mb:     product.allowances?.data_mb    || '',
    voice_mins:  product.allowances?.voice_mins || '',
    sms:         product.allowances?.sms        || '',
  })

  const mut = useMutation({
    mutationFn: (data) => productsApi.update(product.id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['products'] })
      onClose()
    }
  })

  const handleSave = () => {
    const price_config = {
      ...product.price_config,
      amount: form.price_amount ? Math.round(parseFloat(form.price_amount) * 100) : product.price_config?.amount,
    }
    const allowances = {}
    if (form.data_mb)    allowances.data_mb    = parseInt(form.data_mb)
    if (form.voice_mins) allowances.voice_mins = parseInt(form.voice_mins)
    if (form.sms)        allowances.sms        = parseInt(form.sms)

    mut.mutate({
      name:        form.name,
      description: form.description,
      status:      form.status,
      price_config,
      allowances:  Object.keys(allowances).length ? allowances : null,
    })
  }

  return (
    <Modal title={`Edit — ${product.name}`} onClose={onClose}
      footer={<>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-primary" disabled={mut.isPending} onClick={handleSave}>
          {mut.isPending ? 'Saving…' : 'Save Changes'}
        </button>
      </>}>
      <ErrorBanner message={mut.error}/>
      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2">
          <label className="form-label">Name</label>
          <input className="form-input" value={form.name}
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))}/>
        </div>
        <div className="col-span-2">
          <label className="form-label">Description</label>
          <textarea className="form-input" rows={2} value={form.description}
            onChange={e => setForm(f => ({ ...f, description: e.target.value }))}/>
        </div>
        <div>
          <label className="form-label">Price (£)</label>
          <input className="form-input" type="number" step="0.01" min="0"
            value={form.price_amount}
            onChange={e => setForm(f => ({ ...f, price_amount: e.target.value }))}/>
        </div>
        <div>
          <label className="form-label">Status</label>
          <select className="form-select" value={form.status}
            onChange={e => setForm(f => ({ ...f, status: e.target.value }))}>
            <option value="active">Active</option>
            <option value="archived">Archived</option>
          </select>
        </div>
        <div className="col-span-2 pt-2 border-t border-slate-100">
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">Bundle Allowances</div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="form-label">Data (MB)</label>
              <input className="form-input" type="number" value={form.data_mb}
                onChange={e => setForm(f => ({ ...f, data_mb: e.target.value }))}/>
            </div>
            <div>
              <label className="form-label">Voice (mins)</label>
              <input className="form-input" type="number" value={form.voice_mins}
                onChange={e => setForm(f => ({ ...f, voice_mins: e.target.value }))}/>
            </div>
            <div>
              <label className="form-label">SMS</label>
              <input className="form-input" type="number" value={form.sms}
                onChange={e => setForm(f => ({ ...f, sms: e.target.value }))}/>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  )
}

// ── PRODUCTS ──────────────────────────────────────────────────────────────
export function ProductsPage() {
  const [showCreate, setShowCreate] = useState(false)
  const [editProduct, setEditProduct] = useState(null)
  const { data = [], isLoading } = useQuery({ queryKey: ['products'], queryFn: () => productsApi.list() })

  const typePill = (type) => {
    const styles = { base: 'chip', addon: 'text-xs bg-amber-50 border border-amber-200 text-amber-700 px-2 py-0.5 rounded-full', roaming: 'text-xs bg-sky-50 border border-sky-200 text-sky-700 px-2 py-0.5 rounded-full' }
    return <span className={styles[type] || 'chip'}>{type}</span>
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">
      <PageHeader title="Product Catalog" sub={`${data.length} products`}>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>+ New Product</button>
      </PageHeader>
      <div className="card">
        <div className="card-header"><span className="card-title">All Products</span></div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead><tr>
              <th className="table-th">Product</th>
              <th className="table-th">Type</th>
              <th className="table-th">Billing</th>
              <th className="table-th">Price</th>
              <th className="table-th">Allowances</th>
              <th className="table-th">Status</th>
              <th className="table-th"></th>
            </tr></thead>
            <tbody>
              {isLoading ? <LoadingRows cols={6}/> : data.length === 0 ? (
                <tr><td colSpan={6}><Empty title="No products yet" sub="Create your first package"/></td></tr>
              ) : data.map(p => (
                <tr key={p.id} className="table-row">
                  <td className="table-td">
                    <div className="font-medium">{p.name}</div>
                    {p.description && <div className="text-xs text-slate-400">{p.description}</div>}
                  </td>
                  <td className="table-td">{typePill(p.product_type)}</td>
                  <td className="table-td"><span className="chip">{p.billing_model}</span></td>
                  <td className="table-td font-mono">{fmt.money(p.price_config?.amount, p.currency)}</td>
                  <td className="table-td text-xs text-slate-500">
                    {p.allowances ? [
                      p.allowances.data_mb    && `${p.allowances.data_mb}MB`,
                      p.allowances.voice_mins && `${p.allowances.voice_mins}min`,
                      p.allowances.sms        && `${p.allowances.sms}SMS`,
                    ].filter(Boolean).join(' · ') : '—'}
                  </td>
                  <td className="table-td"><span className={`badge ${statusBadge(p.status)}`}>{p.status}</span></td>
                  <td className="table-td">
                    <button className="btn btn-ghost btn-sm" onClick={e => { e.stopPropagation(); setEditProduct(p) }}>Edit</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {showCreate && <CreateProductModal onClose={() => setShowCreate(false)}/>}
      {editProduct && <EditProductModal product={editProduct} onClose={() => setEditProduct(null)}/>}
    </div>
  )
}

// ── ORDERS ────────────────────────────────────────────────────────────────
export function OrdersPage() {
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [statusFilter, setStatusFilter] = useState('')
  const [confirm, setConfirm] = useState(null)

  const { data = [], isLoading } = useQuery({ queryKey: ['orders'], queryFn: ordersApi.list })

  const actionMut = useMutation({
    mutationFn: ({ id, action }) => ordersApi.action(id, action),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['orders'] }); setConfirm(null) }
  })

  const filtered = statusFilter ? data.filter(o => o.status === statusFilter) : data

  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">
      <PageHeader title="Orders" sub={`${data.length} total`}>
        <select className="form-select" style={{width:140}} value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>+ New Order</button>
      </PageHeader>

      <div className="card">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead><tr>
              <th className="table-th">Order</th>
              <th className="table-th">Customer</th>
              <th className="table-th">Status</th>
              <th className="table-th">Created</th>
              <th className="table-th">Activated</th>
              <th className="table-th">Actions</th>
            </tr></thead>
            <tbody>
              {isLoading ? <LoadingRows cols={6}/> : filtered.length === 0 ? (
                <tr><td colSpan={6}><Empty title="No orders found"/></td></tr>
              ) : filtered.map(o => (
                <tr key={o.id} className="table-row">
                  <td className="table-td font-mono text-xs text-slate-500">{o.order_number}</td>
                  <td className="table-td text-xs text-slate-400">{o.customer_id?.slice(0,8)}…</td>
                  <td className="table-td"><span className={`badge ${statusBadge(o.status)}`}>{o.status}</span></td>
                  <td className="table-td text-xs text-slate-400">{fmt.date(o.created_at)}</td>
                  <td className="table-td text-xs text-slate-400">{fmt.date(o.activated_at)}</td>
                  <td className="table-td">
                    <div className="flex gap-1">
                      {o.status === 'pending' && (
                        <button className="btn btn-primary btn-sm" onClick={() => setConfirm({ id: o.id, action: 'activate', label: 'Activate', message: 'Activate this order? This will assign inventory and start the subscription.' })}>Activate</button>
                      )}
                      {o.status === 'active' && (
                        <span className="text-xs text-slate-400 italic">Manage via customer</span>
                      )}
                      {o.status === 'suspended' && (
                        <span className="text-xs text-slate-400 italic">Manage via customer</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {showCreate && <CreateOrderModal onClose={() => setShowCreate(false)}/>}
      {confirm && (
        <Confirm title={`${confirm.label} Order`}
          message={confirm.message || `Are you sure you want to ${confirm.action} this order?`}
          danger={confirm.danger}
          onConfirm={() => actionMut.mutate({ id: confirm.id, action: confirm.action })}
          onCancel={() => setConfirm(null)}/>
      )}
    </div>
  )
}

// ── INVENTORY ─────────────────────────────────────────────────────────────
export function InventoryPage() {
  const [showAdd, setShowAdd] = useState(false)
  const [typeFilter, setTypeFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const { data = [], isLoading } = useQuery({ queryKey: ['inventory'], queryFn: inventoryApi.list })

  const filtered = data.filter(i => {
    return (!typeFilter || i.type === typeFilter) && (!statusFilter || i.status === statusFilter)
  })

  const stats = {
    msisdn:    data.filter(i => i.type === 'msisdn'),
    sim:       data.filter(i => i.type === 'sim'),
    available: data.filter(i => i.status === 'available').length,
    assigned:  data.filter(i => i.status === 'assigned').length,
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">
      <PageHeader title="Inventory" sub="MSISDN & SIM pool">
        <button className="btn btn-primary" onClick={() => setShowAdd(true)}>+ Add Items</button>
      </PageHeader>

      <div className="grid grid-cols-4 gap-4 mb-5">
        {[
          { label:'Total MSISDN', value: stats.msisdn.length },
          { label:'Available MSISDN', value: stats.msisdn.filter(i=>i.status==='available').length },
          { label:'Total SIM', value: stats.sim.length },
          { label:'Available SIM', value: stats.sim.filter(i=>i.status==='available').length },
        ].map(s => (
          <div key={s.label} className="card p-4">
            <div className="stat-label">{s.label}</div>
            <div className="stat-value">{fmt.num(s.value)}</div>
          </div>
        ))}
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">Inventory Pool</span>
          <div className="flex gap-2">
            <select className="form-select" style={{width:120}} value={typeFilter} onChange={e=>setTypeFilter(e.target.value)}>
              <option value="">All types</option>
              <option value="msisdn">MSISDN</option>
              <option value="sim">SIM</option>
            </select>
            <select className="form-select" style={{width:130}} value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}>
              <option value="">All statuses</option>
              <option value="available">Available</option>
              <option value="assigned">Assigned</option>
              <option value="reserved">Reserved</option>
            </select>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead><tr>
              <th className="table-th">Type</th>
              <th className="table-th">Value</th>
              <th className="table-th">Status</th>
              <th className="table-th">Assigned To</th>
              <th className="table-th">Assigned At</th>
            </tr></thead>
            <tbody>
              {isLoading ? <LoadingRows cols={5}/> : filtered.length === 0 ? (
                <tr><td colSpan={5}><Empty title="No inventory items" sub="Import MSISDNs or SIM cards to get started"/></td></tr>
              ) : filtered.map(i => (
                <tr key={i.id} className="table-row">
                  <td className="table-td"><span className="chip">{i.type}</span></td>
                  <td className="table-td font-mono text-sm">{i.value}</td>
                  <td className="table-td"><span className={`badge ${statusBadge(i.status)}`}>{i.status}</span></td>
                  <td className="table-td text-xs text-slate-400">{i.assigned_to_order_id ? `${i.assigned_to_order_id.slice(0,8)}…` : '—'}</td>
                  <td className="table-td text-xs text-slate-400">{fmt.date(i.assigned_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {showAdd && <AddInventoryModal onClose={() => setShowAdd(false)}/>}
    </div>
  )
}

// ── INVOICES ──────────────────────────────────────────────────────────────
export function InvoicesPage() {
  const qc = useQueryClient()
  const [statusFilter, setStatusFilter] = useState('')
  const [showRun, setShowRun] = useState(false)

  const { data = [], isLoading } = useQuery({ queryKey: ['invoices'], queryFn: () => invoicesApi.list()})

  const finaliseMut = useMutation({
    mutationFn: invoicesApi.finalise,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['invoices'] })
  })

  const runMut = useMutation({
    mutationFn: billingRuns.trigger,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['invoices'] }); setShowRun(false) }
  })

  const filtered = statusFilter ? data.filter(i => i.status === statusFilter) : data

  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">
      <PageHeader title="Invoices" sub={`${data.length} total`}>
        <select className="form-select" style={{width:140}} value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}>
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="finalised">Finalised</option>
          <option value="sent">Sent</option>
          <option value="paid">Paid</option>
        </select>
        <button className="btn btn-primary" onClick={() => setShowRun(true)}>▶ Run Billing</button>
      </PageHeader>

      <div className="card">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead><tr>
              <th className="table-th">Invoice</th>
              <th className="table-th">Customer</th>
              <th className="table-th">Period</th>
              <th className="table-th">Total</th>
              <th className="table-th">Status</th>
              <th className="table-th">Actions</th>
            </tr></thead>
            <tbody>
              {isLoading ? <LoadingRows cols={6}/> : filtered.length === 0 ? (
                <tr><td colSpan={6}><Empty title="No invoices yet" sub="Run a billing cycle to generate invoices"/></td></tr>
              ) : filtered.map(inv => (
                <tr key={inv.id} className="table-row">
                  <td className="table-td font-mono text-xs text-slate-500">{inv.invoice_number}</td>
                  <td className="table-td text-xs text-slate-400">{inv.customer_id?.slice(0,8)}…</td>
                  <td className="table-td text-xs text-slate-400">{fmt.date(inv.period_start)} – {fmt.date(inv.period_end)}</td>
                  <td className="table-td font-mono">{fmt.money(inv.total, inv.currency)}</td>
                  <td className="table-td"><span className={`badge ${statusBadge(inv.status)}`}>{inv.status}</span></td>
                  <td className="table-td">
                    <div className="flex gap-1.5 items-center">
                      {inv.status === 'draft' && (
                        <button className="btn btn-primary btn-sm" onClick={() => finaliseMut.mutate(inv.id)}>Finalise</button>
                      )}
                      <a
                        href={invoicesApi.pdfUrl(inv.id)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn btn-ghost btn-sm flex items-center gap-1"
                        title="Open invoice PDF">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                        PDF
                      </a>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {showRun && (
        <BillingRunModal onClose={() => setShowRun(false)} onRun={(d) => runMut.mutate(d)} loading={runMut.isPending}/>
      )}
    </div>
  )
}

function BillingRunModal({ onClose, onRun, loading }) {
  const [start, setStart] = useState('')
  const [end, setEnd]     = useState('')
  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal slide-in">
        <div className="modal-header"><span className="modal-title">Run Billing Cycle</span></div>
        <div className="modal-body space-y-4">
          <p className="text-sm text-slate-500">Generate invoices for all active subscriptions in the selected period.</p>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="form-label">Period Start</label><input className="form-input" type="date" value={start} onChange={e=>setStart(e.target.value)}/></div>
            <div><label className="form-label">Period End</label><input className="form-input" type="date" value={end} onChange={e=>setEnd(e.target.value)}/></div>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={!start || !end || loading} onClick={() => onRun({ period_start: start, period_end: end })}>
            {loading ? 'Running…' : '▶ Run Billing'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── USAGE ─────────────────────────────────────────────────────────────────
export function UsagePage() {
  const [msisdnFilter, setMsisdnFilter] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const qc = useQueryClient()

  const { data: events = [], isLoading } = useQuery({
    queryKey: ['usage-events', msisdnFilter],
    queryFn: () => usageApi.list(msisdnFilter ? { msisdn: msisdnFilter } : {})
  })

  const { data: rejected = [] } = useQuery({ queryKey: ['rejected'], queryFn: usageApi.rejected })

  const uploadMut = useMutation({
    mutationFn: usageApi.upload,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['usage-events'] })
  })

  const handleDrop = (e) => {
    e.preventDefault(); setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) uploadMut.mutate(file)
  }

  const typeBadge = (type) => {
    const map = { data: 'badge-info', voice: 'badge-neutral', sms: 'badge-neutral' }
    return <span className={`badge ${map[type] || 'badge-neutral'}`}>{type}</span>
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">
      <PageHeader title="Usage Events" sub="Mediation & rating"/>

      <div className="grid grid-cols-2 gap-4 mb-4">
        {/* Upload */}
        <div className="card">
          <div className="card-header"><span className="card-title">Upload CDR File</span></div>
          <div className="card-body">
            <div
              className={`border-2 border-dashed rounded-xl p-8 text-center transition-colors ${dragOver ? 'border-brand-500 bg-brand-50' : 'border-slate-200 hover:border-slate-300'}`}
              onDragOver={e=>{e.preventDefault();setDragOver(true)}}
              onDragLeave={()=>setDragOver(false)}
              onDrop={handleDrop}>
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="mx-auto mb-3 text-slate-300"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
              <p className="text-sm font-medium text-slate-500 mb-1">Drop CSV file here or</p>
              <label className="btn btn-primary cursor-pointer">
                Choose File
                <input type="file" accept=".csv" className="hidden" onChange={e => e.target.files[0] && uploadMut.mutate(e.target.files[0])}/>
              </label>
              <p className="text-xs text-slate-400 mt-2">Standard CDR CSV format · Max 50MB</p>
              {uploadMut.isPending && <p className="text-xs text-brand-600 mt-2">Processing…</p>}
              {uploadMut.isSuccess && <p className="text-xs text-emerald-600 mt-2">File accepted for processing</p>}
            </div>
          </div>
        </div>

        {/* Rejected */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Rejected Records</span>
            {rejected.length > 0 && <span className="badge badge-danger">{rejected.length}</span>}
          </div>
          <div className="overflow-x-auto" style={{maxHeight:220,overflowY:'auto'}}>
            {rejected.length === 0 ? (
              <div className="p-6 text-center text-sm text-slate-400">No rejected records</div>
            ) : rejected.map(r => (
              <div key={r.id} className="px-4 py-3 border-b border-slate-100 flex items-start gap-3">
                <span className="badge badge-danger mt-0.5 flex-shrink-0">{r.rejection_code}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-slate-500 truncate">{r.reason}</div>
                  <div className="text-xs text-slate-400">{fmt.datetime(r.created_at)}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Events table */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Usage Events</span>
          <input className="form-input" style={{width:200}} value={msisdnFilter}
            onChange={e=>setMsisdnFilter(e.target.value)} placeholder="Filter by MSISDN…"/>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead><tr>
              <th className="table-th">MSISDN</th>
              <th className="table-th">Type</th>
              <th className="table-th">Quantity</th>
              <th className="table-th">Timestamp</th>
              <th className="table-th">Source</th>
              <th className="table-th">Status</th>
            </tr></thead>
            <tbody>
              {isLoading ? <LoadingRows cols={6}/> : events.length === 0 ? (
                <tr><td colSpan={6}><Empty title="No usage events" sub="Upload a CDR file or send events via API"/></td></tr>
              ) : events.map(e => (
                <tr key={e.id} className="table-row">
                  <td className="table-td font-mono text-xs">{e.msisdn}</td>
                  <td className="table-td">{typeBadge(e.event_type)}</td>
                  <td className="table-td font-mono text-xs">{e.quantity} {e.unit}</td>
                  <td className="table-td text-xs text-slate-400">{fmt.datetime(e.event_timestamp)}</td>
                  <td className="table-td text-xs text-slate-400">{e.source_system}</td>
                  <td className="table-td"><span className={`badge ${statusBadge(e.status)}`}>{e.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ── PAYMENTS ──────────────────────────────────────────────────────────────
export function PaymentsPage() {
  const [showCreate, setShowCreate] = useState(false)
  const { data = [], isLoading } = useQuery({ queryKey: ['payments'], queryFn: () => paymentsApi.list() })

  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">
      <PageHeader title="Payments" sub={`${data.length} recorded`}>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>+ Record Payment</button>
      </PageHeader>
      <div className="card">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead><tr>
              <th className="table-th">Customer</th>
              <th className="table-th">Amount</th>
              <th className="table-th">Method</th>
              <th className="table-th">Reference</th>
              <th className="table-th">Date</th>
              <th className="table-th">Invoice</th>
            </tr></thead>
            <tbody>
              {isLoading ? <LoadingRows cols={6}/> : data.length === 0 ? (
                <tr><td colSpan={6}><Empty title="No payments recorded" sub="Record a payment against an invoice or as a top-up"/></td></tr>
              ) : data.map(p => (
                <tr key={p.id} className="table-row">
                  <td className="table-td text-xs text-slate-400">{p.customer_id?.slice(0,8)}…</td>
                  <td className="table-td font-mono">{fmt.money(p.amount, p.currency)}</td>
                  <td className="table-td"><span className="chip">{p.method}</span></td>
                  <td className="table-td font-mono text-xs text-slate-400">{p.reference || '—'}</td>
                  <td className="table-td text-xs text-slate-400">{fmt.date(p.payment_date)}</td>
                  <td className="table-td font-mono text-xs text-slate-400">{p.invoice_id ? `${p.invoice_id.slice(0,8)}…` : 'Top-up'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {showCreate && <RecordPaymentModal onClose={() => setShowCreate(false)}/>}
    </div>
  )
}

// ── PROVISIONING MONITOR ──────────────────────────────────────────────────
export function ProvisioningPage() {
  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">
      <PageHeader title="Provisioning" sub="OmniHSS · CGRateS workflow monitor"/>
      <div className="grid grid-cols-4 gap-4 mb-5">
        {[
          { label: 'Total workflows',  key: 'total' },
          { label: 'Running',          key: 'running' },
          { label: 'Completed',        key: 'completed' },
          { label: 'Failed / Rolled back', key: 'failed' },
        ].map(s => (
          <div key={s.label} className="card p-4">
            <div className="stat-label">{s.label}</div>
            <div className="stat-value text-xl mt-1">—</div>
          </div>
        ))}
      </div>
      <ProvisioningMonitor/>
    </div>
  )
}
