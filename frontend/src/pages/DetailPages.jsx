// src/pages/DetailPages.jsx
// Detail pages for: Product, InventoryItem, Invoice, UsageEvent, Payment, ProvisioningWorkflow

import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  products as productsApi, inventory as inventoryApi,
  invoices as invoicesApi, usage as usageApi,
  payments as paymentsApi, provisioning as provApi,
  orders as ordersApi, customers as customersApi,
  products as productsApiDetail,											 
} from '../lib/api'
import { fmt, statusBadge } from '../lib/utils'
import { Spinner, Empty, ErrorBanner, Modal, Confirm } from '../components/ui'
import { CustomFieldsDisplay } from '../components/CustomFields'
import { StepCard } from '../components/ProvisioningStepCard'

// ── Back button ────────────────────────────────────────────────────────────
function BackBtn({ to, label }) {
  const nav = useNavigate()
  return (
    <button className="btn btn-ghost btn-sm" onClick={() => nav(to)}>
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth="2.5"><polyline points="15 18 9 12 15 6"/></svg>
      {label}
    </button>
  )
}

// ── Detail header ──────────────────────────────────────────────────────────
function DetailHeader({ title, subtitle, badge, status, children }) {
  return (
    <div className="flex items-start justify-between mb-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
        {subtitle && <div className="text-xs text-slate-400 mt-0.5">{subtitle}</div>}
        {status && (
          <span className={`badge ${statusBadge(status)} mt-1 inline-flex`}>{status}</span>
        )}
      </div>
      {children && <div className="flex gap-2">{children}</div>}
    </div>
  )
}

// ── Info grid ──────────────────────────────────────────────────────────────
function InfoGrid({ rows, cols = 2 }) {
  return (
    <div className={`grid grid-cols-${cols} gap-x-6 gap-y-4`}>
      {rows.map(([label, value]) => (
        <div key={label}>
          <div className="text-xs text-slate-400 uppercase tracking-wide font-medium mb-0.5">{label}</div>
          <div className="text-sm text-slate-800">{value ?? '—'}</div>
        </div>
      ))}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════
// PRODUCT DETAIL
// ══════════════════════════════════════════════════════════════════════════
export function ProductDetailPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const qc  = useQueryClient()

  const { data: product, isLoading } = useQuery({
    queryKey: ['product', id],
    queryFn:  () => productsApi.get(id),
  })

  const archiveMut = useMutation({
    mutationFn: () => productsApi.update(id, { status: 'archived' }),
    onSuccess:  () => { qc.invalidateQueries({ queryKey: ['products'] }); nav('/products') },
  })

  if (isLoading) return <div className="flex-1 flex items-center justify-center"><Spinner size={32}/></div>
  if (!product) return <div className="flex-1 p-6 text-slate-400">Product not found</div>

  const allowances = product.allowances || {}
  const oob        = product.out_of_bundle_rates || {}
  const price      = product.price_config || {}

  const typePill = (t) => {
    const s = { base:'chip', addon:'text-xs bg-amber-50 border border-amber-200 text-amber-700 px-2 py-0.5 rounded-full', roaming:'text-xs bg-sky-50 border border-sky-200 text-sky-700 px-2 py-0.5 rounded-full' }
    return <span className={s[t]||'chip'}>{t}</span>
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">
      <div className="flex items-center gap-3 mb-5">
        <BackBtn to="/products" label="Products"/>
        <h1 className="text-xl font-semibold flex items-center gap-3">
          {product.name}
          {typePill(product.product_type)}
          <span className={`badge ${statusBadge(product.status)}`}>{product.status}</span>
        </h1>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        {/* Core details */}
        <div className="card">
          <div className="card-header"><span className="card-title">Product details</span></div>
          <div className="card-body">
            <InfoGrid rows={[
              ['Name',           product.name],
              ['Type',           product.product_type],
              ['Billing model',  product.billing_model],
              ['Currency',       product.currency],
              ['Requires inventory', product.requires_inventory ? `Yes — ${product.inventory_type}` : 'No'],
              ['Created',        fmt.date(product.created_at)],
            ]}/>
            {product.description && (
              <div className="mt-4 pt-4 border-t border-slate-100">
                <div className="text-xs text-slate-400 uppercase tracking-wide font-medium mb-1">Description</div>
                <div className="text-sm text-slate-600">{product.description}</div>
              </div>
            )}
          </div>
        </div>

        {/* Pricing */}
        <div className="card">
          <div className="card-header"><span className="card-title">Pricing</span></div>
          <div className="card-body">
            <div className="text-3xl font-semibold font-mono text-brand-600 mb-1">
              {fmt.money(price.amount ?? price.unit_price, product.currency)}
              <span className="text-sm text-slate-400 font-sans ml-1">
                {product.billing_model === 'recurring' ? '/month' :
                 product.billing_model === 'one_time'  ? ' one-time' :
                 product.billing_model === 'metered'   ? ' /unit' : ''}
              </span>
            </div>
            <div className="text-xs text-slate-400 mt-3 mb-2 uppercase tracking-wide font-medium">Full price config</div>
            <pre className="text-xs bg-slate-50 border border-slate-200 rounded-lg p-3 overflow-x-auto text-slate-600">
              {JSON.stringify(price, null, 2)}
            </pre>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        {/* Allowances */}
        <div className="card">
          <div className="card-header"><span className="card-title">Bundle allowances</span></div>
          <div className="card-body">
            {Object.keys(allowances).length === 0 ? (
              <div className="text-sm text-slate-400">No bundle allowances — usage billed at OOB rate</div>
            ) : (
              <div className="space-y-4">
                {allowances.data_mb && (
                  <div>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="font-medium">📶 Data</span>
                      <span className="font-mono">{fmt.num(allowances.data_mb)} MB</span>
                    </div>
                    {oob.data_mb && <div className="text-xs text-slate-400">OOB rate: {oob.data_mb}p/MB</div>}
                  </div>
                )}
                {allowances.voice_mins && (
                  <div>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="font-medium">📞 Voice</span>
                      <span className="font-mono">{fmt.num(allowances.voice_mins)} mins</span>
                    </div>
                    {oob.voice_mins && <div className="text-xs text-slate-400">OOB rate: {oob.voice_mins}p/min</div>}
                  </div>
                )}
                {allowances.sms && (
                  <div>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="font-medium">💬 SMS</span>
                      <span className="font-mono">{fmt.num(allowances.sms)} messages</span>
                    </div>
                    {oob.sms && <div className="text-xs text-slate-400">OOB rate: {oob.sms}p/SMS</div>}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* OOB rates */}
        <div className="card">
          <div className="card-header"><span className="card-title">Out-of-bundle rates</span></div>
          <div className="card-body">
            {Object.keys(oob).length === 0 ? (
              <div className="text-sm text-slate-400">No OOB rates configured</div>
            ) : (
              <InfoGrid rows={[
                oob.data_mb    && ['Data OOB',  `${oob.data_mb}p per MB`],
                oob.voice_mins && ['Voice OOB', `${oob.voice_mins}p per minute`],
                oob.sms        && ['SMS OOB',   `${oob.sms}p per message`],
              ].filter(Boolean)}/>
            )}
          </div>
        </div>
      </div>

      {/* Actions */}
      {product.status === 'active' && (
        <div className="flex justify-end">
          <button className="btn btn-danger"
            onClick={() => archiveMut.mutate()}
            disabled={archiveMut.isPending}>
            Archive product
          </button>
        </div>
      )}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════
// ORDER DETAIL
// ══════════════════════════════════════════════════════════════════════════
export function OrderDetailPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const qc  = useQueryClient()
  const [confirm, setConfirm] = useState(null)
  const [actionError, setActionError] = useState('')

  const { data: order, isLoading } = useQuery({
    queryKey: ['order', id],
    queryFn:  () => ordersApi.get(id),
  })

  const { data: productList = [] } = useQuery({
    queryKey: ['products'],
    queryFn:  () => productsApiDetail.list(),
    enabled: !!order,
  })

  const actionMut = useMutation({
    mutationFn: ({ action }) => ordersApi.action(id, action),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['order', id] })
      qc.invalidateQueries({ queryKey: ['orders'] })
      setConfirm(null)
      setActionError('')
    },
    onError: (err) => {
      setActionError(typeof err === 'string' ? err : JSON.stringify(err))
      setConfirm(null)
    },
  })

  if (isLoading) return <div className="flex-1 flex items-center justify-center"><Spinner size={32}/></div>
  if (!order) return <div className="flex-1 p-6 text-slate-400">Order not found</div>

  const product = productList.find(p => p.id === order.product_id)

  const actionButtons = () => {
    if (order.status === 'pending') return (
      <>
      <button className="btn btn-primary"
        onClick={() => setConfirm({ action: 'activate', label: 'Activate Order',
          message: 'Activate this order? This will assign inventory and start the subscription.' })}>
        Activate
      </button>
      <button className="btn btn-ghost btn-sm"
    onClick={() => setShowEdit(true)}>
    Edit order
  </button>
  </>
    )
    // if (order.status === 'active') return (
    //   <button className="btn btn-ghost"
    //     onClick={() => setConfirm({ action: 'suspend', label: 'Suspend Order',
    //       message: 'Suspend this order? Service will be paused.' })}>
    //     Suspend
    //   </button>
    // )
    // if (order.status === 'suspended') return (
    //   <button className="btn btn-primary"
    //     onClick={() => setConfirm({ action: 'activate', label: 'Reactivate Order',
    //       message: 'Reactivate this order? Service will resume.' })}>
    //     Reactivate
    //   </button>
    // )
    return null
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">
      <div className="flex items-center gap-3 mb-5">
        <BackBtn to="/orders" label="Orders"/>
        <h1 className="text-xl font-semibold font-mono">{order.order_number}</h1>
        <span className={`badge ${statusBadge(order.status)}`}>{order.status}</span>
      </div>

      {/* Action error banner */}
      {actionError && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-5 py-4 mb-4 flex items-start gap-3">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#DC2626" strokeWidth="2.5" strokeLinecap="round" className="flex-shrink-0 mt-0.5">
            <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
          </svg>
          <div>
            <div className="text-sm font-semibold text-red-800">Action failed</div>
            <div className="text-sm text-red-700 mt-0.5">{actionError}</div>
          </div>
          <button onClick={() => setActionError('')} className="ml-auto text-red-400 hover:text-red-600">×</button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div className="card">
          <div className="card-header">
            <span className="card-title">Order details</span>
            <div className="flex gap-2">
              {actionButtons()}
              {/* {order.status !== 'cancelled' && (
                <button className="btn btn-danger btn-sm"
                  onClick={() => setConfirm({ action: 'cancel', label: 'Cancel Order', danger: true,
                    message: 'Cancel this order? This will release inventory and end the subscription.' })}>
                  Cancel
                </button>
              )} */}
            </div>
          </div>
          <div className="card-body">
            <InfoGrid rows={[
              ['Order number', order.order_number],
              ['Status',       order.status],
              ['Customer',     order.customer_id?.slice(0,8)+'…'],
              ['Product',      product?.name || order.product_id?.slice(0,8)+'…'],
              ['Parent order', order.parent_order_id?.slice(0,8)+'…' || '—'],
              ['Created',      fmt.date(order.created_at)],
              ['Activated',    fmt.date(order.activated_at)],
              ['Suspended',    fmt.date(order.suspended_at)],
              ['Cancelled',    fmt.date(order.cancelled_at)],
            ].filter(([,v]) => v)}/>
          </div>
        </div>

        {product && (
          <div className="card">
            <div className="card-header">
              <span className="card-title">Package</span>
              <button className="btn btn-ghost btn-sm" onClick={() => nav(`/products/${product.id}`)}>
                View product →
              </button>
            </div>
            <div className="card-body">
              <div className="text-lg font-semibold mb-2">{product.name}</div>
              <div className="text-2xl font-mono text-brand-600 mb-3">
                {fmt.money(product.price_config?.amount, product.currency)}
                <span className="text-sm text-slate-400 font-sans ml-1">/month</span>
              </div>
              {product.allowances && (
                <div className="flex gap-4 text-sm">
                  {product.allowances.data_mb    && <span>📶 {product.allowances.data_mb}MB</span>}
                  {product.allowances.voice_mins && <span>📞 {product.allowances.voice_mins}min</span>}
                  {product.allowances.sms        && <span>💬 {product.allowances.sms}SMS</span>}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Quick links */}
      <div className="flex gap-3">
        <button className="btn btn-ghost" onClick={() => nav(`/customers/${order.customer_id}`)}>
          View customer →
        </button>
        <button className="btn btn-ghost" onClick={() => nav(`/provisioning/${order.id}`)}>
          Provisioning workflow →
        </button>
      </div>

      {confirm && (
        <Confirm
          title={confirm.label}
          message={confirm.message}
          danger={confirm.danger}
          onConfirm={() => actionMut.mutate({ action: confirm.action })}
          onCancel={() => setConfirm(null)}/>
      )}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════
// INVENTORY DETAIL
// ══════════════════════════════════════════════════════════════════════════
export function InventoryDetailPage() {
  const { id } = useParams()
  const nav = useNavigate()

  const { data: item, isLoading } = useQuery({
    queryKey: ['inventory-item', id],
    queryFn:  () => inventoryApi.get ? inventoryApi.get(id) :
                    inventoryApi.list().then(l => l.find(i => i.id === id)),
  })

  if (isLoading) return <div className="flex-1 flex items-center justify-center"><Spinner size={32}/></div>
  if (!item) return <div className="flex-1 p-6 text-slate-400">Item not found</div>

  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">
      <div className="flex items-center gap-3 mb-5">
        <BackBtn to="/inventory" label="Inventory"/>
        <h1 className="text-xl font-semibold font-mono">{item.value}</h1>
        <span className="chip">{item.type}</span>
        <span className={`badge ${statusBadge(item.status)}`}>{item.status}</span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="card">
          <div className="card-header"><span className="card-title">Item details</span></div>
          <div className="card-body">
            <InfoGrid rows={[
              ['ID',         item.id],
              ['Type',       item.type],
              ['Value',      item.value],
              ['Status',     item.status],
              ['Assigned to order', item.assigned_to_order_id || '—'],
              ['Assigned at', fmt.datetime(item.assigned_at)],
              ['Created',    fmt.date(item.created_at)],
            ]}/>
          </div>
        </div>

        {item.extra && Object.keys(item.extra).length > 0 && (
          <div className="card">
            <div className="card-header"><span className="card-title">Network metadata</span></div>
            <div className="card-body">
              <InfoGrid rows={Object.entries(item.extra).map(([k, v]) => [k, String(v)])}/>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════
// INVOICE DETAIL
// ══════════════════════════════════════════════════════════════════════════
export function InvoiceDetailPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const qc  = useQueryClient()

  const { data: inv, isLoading } = useQuery({
    queryKey: ['invoice', id],
    queryFn:  () => invoicesApi.get(id),
  })

  const finaliseMut = useMutation({
    mutationFn: () => invoicesApi.finalise(id),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['invoice', id] }),
  })

  if (isLoading) return <div className="flex-1 flex items-center justify-center"><Spinner size={32}/></div>
  if (!inv) return <div className="flex-1 p-6 text-slate-400">Invoice not found</div>

  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">
      <div className="flex items-center gap-3 mb-5">
        <BackBtn to="/invoices" label="Invoices"/>
        <h1 className="text-xl font-semibold font-mono">{inv.invoice_number}</h1>
        <span className={`badge ${statusBadge(inv.status)}`}>{inv.status}</span>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-4">
        <div className="card col-span-2">
          <div className="card-header">
            <span className="card-title">Invoice details</span>
            <div className="flex gap-2">
              {inv.status === 'draft' && (
                <button className="btn btn-primary btn-sm"
                  onClick={() => finaliseMut.mutate()}
                  disabled={finaliseMut.isPending}>Finalise</button>
              )}
              <a href={invoicesApi.pdfUrl(inv.id)} target="_blank" rel="noopener noreferrer"
                className="btn btn-ghost btn-sm flex items-center gap-1">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                PDF
              </a>
            </div>
          </div>
          <div className="card-body">
            <InfoGrid rows={[
              ['Customer',    inv.customer_id?.slice(0,8)+'…'],
              ['Period',      `${fmt.date(inv.period_start)} – ${fmt.date(inv.period_end)}`],
              ['Due date',    fmt.date(inv.due_date)],
              ['Created',     fmt.date(inv.created_at)],
            ]}/>
          </div>

          {/* Line items */}
          <div className="border-t border-slate-100">
            <div className="px-5 py-3 text-xs font-semibold text-slate-400 uppercase tracking-wide">Line items</div>
            <table className="w-full">
              <thead><tr>
                <th className="table-th">Description</th>
                <th className="table-th text-right">Qty</th>
                <th className="table-th text-right">Unit price</th>
                <th className="table-th text-right">Amount</th>
              </tr></thead>
              <tbody>
                {(inv.line_items || []).length === 0 ? (
                  <tr><td colSpan={4} className="table-td text-center text-slate-400 py-4">No line items</td></tr>
                ) : (inv.line_items || []).map(li => (
                  <tr key={li.id} className="table-row">
                    <td className="table-td">{li.description}</td>
                    <td className="table-td text-right font-mono">{li.quantity}</td>
                    <td className="table-td text-right font-mono">{fmt.money(li.unit_price, inv.currency)}</td>
                    <td className="table-td text-right font-mono">{fmt.money(li.amount, inv.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Totals */}
        <div className="card">
          <div className="card-header"><span className="card-title">Summary</span></div>
          <div className="card-body space-y-3">
            <div className="flex justify-between text-sm border-b border-slate-100 pb-3">
              <span className="text-slate-500">Subtotal</span>
              <span className="font-mono">{fmt.money(inv.subtotal, inv.currency)}</span>
            </div>
            <div className="flex justify-between text-sm border-b border-slate-100 pb-3">
              <span className="text-slate-500">Tax</span>
              <span className="font-mono">{fmt.money(0, inv.currency)}</span>
            </div>
            <div className="flex justify-between text-lg font-semibold">
              <span>Total due</span>
              <span className="font-mono text-brand-600">{fmt.money(inv.total, inv.currency)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════
// USAGE EVENT DETAIL
// ══════════════════════════════════════════════════════════════════════════
export function UsageDetailPage() {
  const { id } = useParams()
  const nav = useNavigate()

  const { data: events = [], isLoading } = useQuery({
    queryKey: ['usage-events'],
    queryFn:  () => usageApi.list({}),
  })

  const event = events.find(e => e.id === id)

  if (isLoading) return <div className="flex-1 flex items-center justify-center"><Spinner size={32}/></div>
  if (!event) return <div className="flex-1 p-6 text-slate-400">Usage event not found</div>

  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">
      <div className="flex items-center gap-3 mb-5">
        <BackBtn to="/usage" label="Usage events"/>
        <h1 className="text-xl font-semibold font-mono">{event.event_id?.slice(0,16)}…</h1>
        <span className={`badge ${statusBadge(event.status)}`}>{event.status}</span>
      </div>

      <div className="card max-w-2xl">
        <div className="card-header"><span className="card-title">Event details</span></div>
        <div className="card-body">
          <InfoGrid rows={[
            ['Event ID',      event.event_id],
            ['MSISDN',        event.msisdn],
            ['Event type',    event.event_type],
            ['Quantity',      `${event.quantity} ${event.unit}`],
            ['Timestamp',     fmt.datetime(event.event_timestamp)],
            ['Ingested at',   fmt.datetime(event.ingested_at)],
            ['Source',        event.source_system],
            ['Subscription',  event.subscription_id || '—'],
            ['Customer',      event.customer_id || '—'],
            ['Status',        event.status],
          ]}/>
          {event.extra && Object.keys(event.extra).length > 0 && (
            <div className="mt-4 pt-4 border-t border-slate-100">
              <div className="text-xs text-slate-400 uppercase tracking-wide font-medium mb-2">Extra metadata</div>
              <pre className="text-xs bg-slate-50 border border-slate-200 rounded-lg p-3 overflow-x-auto">
                {JSON.stringify(event.extra, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════
// PAYMENT DETAIL
// ══════════════════════════════════════════════════════════════════════════
export function PaymentDetailPage() {
  const { id } = useParams()
  const nav = useNavigate()

  const { data: payments = [], isLoading } = useQuery({
    queryKey: ['payments'],
    queryFn:  () => paymentsApi.list(),
  })

  const payment = payments.find(p => p.id === id)

  if (isLoading) return <div className="flex-1 flex items-center justify-center"><Spinner size={32}/></div>
  if (!payment) return <div className="flex-1 p-6 text-slate-400">Payment not found</div>

  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">
      <div className="flex items-center gap-3 mb-5">
        <BackBtn to="/payments" label="Payments"/>
        <h1 className="text-xl font-semibold font-mono">
          {fmt.money(payment.amount, payment.currency)}
        </h1>
        <span className="chip">{payment.method?.replace('_',' ')}</span>
      </div>

      <div className="card max-w-2xl">
        <div className="card-header"><span className="card-title">Payment details</span></div>
        <div className="card-body">
          <InfoGrid rows={[
            ['Amount',      fmt.money(payment.amount, payment.currency)],
            ['Method',      payment.method?.replace('_',' ')],
            ['Reference',   payment.reference || '—'],
            ['Payment date',fmt.date(payment.payment_date)],
            ['Recorded at', fmt.datetime(payment.recorded_at)],
            ['Recorded by', payment.recorded_by || '—'],
            ['Customer',    payment.customer_id || '—'],
            ['Invoice',     payment.invoice_id  || 'Top-up / unallocated'],
          ]}/>
        </div>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════
// PROVISIONING WORKFLOW DETAIL
// ══════════════════════════════════════════════════════════════════════════

/* const STEP_STATUS_COLOR = {
  completed:   { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200', icon: '✓' },
  failed:      { bg: 'bg-red-50',     text: 'text-red-700',     border: 'border-red-200',     icon: '✗' },
  running:     { bg: 'bg-brand-50',   text: 'text-brand-700',   border: 'border-brand-200',   icon: '◌' },
  rolled_back: { bg: 'bg-orange-50',  text: 'text-orange-700',  border: 'border-orange-200',  icon: '↩' },
  pending:     { bg: 'bg-slate-50',   text: 'text-slate-500',   border: 'border-slate-200',   icon: '○' },
  skipped:     { bg: 'bg-slate-50',   text: 'text-slate-400',   border: 'border-slate-100',   icon: '–' },
} */

const WF_STATUS_COLOR = {
  completed:    'badge-success',
  failed:       'badge-danger',
  rolled_back:  'badge-warning',
  rolling_back: 'badge-warning',
  running:      'badge-info',
  pending:      'badge-neutral',
}

/*function StepCard({ step, index }) {
  const [open, setOpen] = useState(step.status === 'failed')
  const cfg = STEP_STATUS_COLOR[step.status] || STEP_STATUS_COLOR.pending

  const durationMs = step.started_at && step.completed_at
    ? new Date(step.completed_at) - new Date(step.started_at) : null

  const isRollback = step.step_description?.startsWith('ROLLBACK')

  return (
    <div className={`border rounded-xl overflow-hidden mb-2 ${cfg.border} ${isRollback ? 'opacity-80' : ''}`}>
      <div className={`px-4 py-3 flex items-center gap-3 cursor-pointer ${cfg.bg}`}
        onClick={() => setOpen(o => !o)}>

        { Step number / icon }
        <div className={`w-7 h-7 rounded-full flex items-center justify-center text-sm font-semibold flex-shrink-0 border ${cfg.border} ${cfg.bg} ${cfg.text}`}>
          {cfg.icon}
        </div>

        <div className="flex-1 min-w-0">
          <div className={`text-sm font-medium ${cfg.text}`}>
            {isRollback && <span className="text-xs bg-orange-100 text-orange-600 border border-orange-200 px-1.5 py-0.5 rounded mr-2">ROLLBACK</span>}
            {step.step_name.replace(/_/g, ' ')}
          </div>
          <div className="text-xs text-slate-500 mt-0.5">{step.step_description?.replace('ROLLBACK: ','')}</div>
        </div>

        <div className="flex items-center gap-3 flex-shrink-0 text-xs text-slate-400">
          {durationMs !== null && (
            <span className="font-mono">
              {durationMs < 1000 ? `${durationMs}ms` : `${(durationMs/1000).toFixed(1)}s`}
            </span>
          )}
          {step.started_at && (
            <span>{new Date(step.started_at).toLocaleTimeString()}</span>
          )}
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            style={{transform: open ? 'rotate(180deg)' : 'none', transition:'transform .15s'}}>
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
      </div>

      {open && (
        <div className="px-4 py-3 border-t border-slate-100 bg-white space-y-2">
          {step.error_message && (
            <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-xs text-red-700 font-mono">
              {step.error_message}
            </div>
          )}
          {step.result && Object.keys(step.result).length > 0 && (
            <div>
              <div className="text-xs text-slate-400 mb-1">Step output</div>
              <pre className="text-xs bg-slate-50 border border-slate-200 rounded-lg p-2 overflow-x-auto text-slate-600">
                {JSON.stringify(step.result, null, 2)}
              </pre>
            </div>
          )}
          <div className="grid grid-cols-3 gap-3 text-xs text-slate-400">
            <div><span className="font-medium">Attempt:</span> {step.attempt}</div>
            {step.started_at   && <div><span className="font-medium">Started:</span> {fmt.datetime(step.started_at)}</div>}
            {step.completed_at && <div><span className="font-medium">Completed:</span> {fmt.datetime(step.completed_at)}</div>}
          </div>
        </div>
      )}
    </div>
  )
} */

export function ProvisioningDetailPage() {
  const { id } = useParams()  // order_id
  const nav = useNavigate()
  const qc  = useQueryClient()

  const { data: wf, isLoading } = useQuery({
    queryKey: ['provisioning-workflow-detail', id],
    queryFn:  () => provApi.getWorkflow(id),
    refetchInterval: (data) =>
      data?.status === 'running' || data?.status === 'rolling_back' ? 3000 : false,
  })

  const retryMut = useMutation({
    mutationFn: () => provApi.provision(id),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['provisioning-workflow-detail', id] }),
  })

  const deprovMut = useMutation({
    mutationFn: () => provApi.deprovision(id),
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['provisioning-workflow-detail', id] }),
  })

  const [confirmDeprov, setConfirmDeprov] = useState(false)

  if (isLoading) return <div className="flex-1 flex items-center justify-center"><Spinner size={32}/></div>
  if (!wf) return <div className="flex-1 p-6 text-slate-400">No provisioning workflow found for this order</div>

  const steps         = wf.steps || []
  const provSteps     = steps.filter(s => !s.step_description?.startsWith('ROLLBACK'))
  const rollbackSteps = steps.filter(s =>  s.step_description?.startsWith('ROLLBACK'))
  const completed     = provSteps.filter(s => s.status === 'completed').length
  const pct           = provSteps.length > 0 ? Math.round(completed / provSteps.length * 100) : 0

  const ctx = wf.context || {}

  return (
    <div className="flex-1 overflow-y-auto p-6 fade-in">
      {/* Header */}
      <div className="flex items-start gap-3 mb-5">
        <BackBtn to="/provisioning" label="Provisioning"/>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-semibold">
              {wf.workflow_type?.replace(/_/g,' ')}
            </h1>
            <span className={`badge ${WF_STATUS_COLOR[wf.status] || 'badge-neutral'}`}>
              {wf.status?.replace(/_/g,' ')}
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-1">
            Order {wf.order_id?.slice(0,8)}… · Started {fmt.datetime(wf.created_at)}
            {wf.completed_at && ` · Completed ${fmt.datetime(wf.completed_at)}`}
          </div>
        </div>

        <div className="flex gap-2">
          {(wf.status === 'failed' || wf.status === 'rolled_back') && (
            <button className="btn btn-primary" onClick={() => retryMut.mutate()}
              disabled={retryMut.isPending}>
              ↺ Retry provisioning
            </button>
          )}
          {wf.status === 'completed' && (
            <button className="btn btn-danger" onClick={() => setConfirmDeprov(true)}>
              Deprovision
            </button>
          )}
        </div>
      </div>

      {/* Error banner */}
      {wf.error_message && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-5 py-4 mb-4">
          <div className="text-sm font-semibold text-red-800 mb-1">
            Failed at: {wf.error_step?.replace(/_/g,' ')}
          </div>
          <div className="text-xs text-red-700 font-mono">{wf.error_message}</div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-4 mb-5">
        {/* Progress */}
        <div className="card col-span-2">
          <div className="card-header">
            <span className="card-title">Progress</span>
            <span className="text-sm font-mono text-slate-500">{completed}/{provSteps.length} steps</span>
          </div>
          <div className="card-body">
            <div className="mb-3">
              <div className="flex justify-between text-xs text-slate-500 mb-1">
                <span>Provisioning progress</span>
                <span>{pct}%</span>
              </div>
              <div className="h-2 bg-slate-200 rounded-full overflow-hidden">
                <div className="h-full rounded-full transition-all duration-500"
                  style={{
                    width: `${pct}%`,
                    background: wf.status === 'completed' ? '#059669' :
                                wf.status === 'failed'    ? '#DC2626' : '#1B4FD8'
                  }}/>
              </div>
            </div>

            {/* Duration */}
            {wf.created_at && wf.completed_at && (
              <div className="text-xs text-slate-400">
                Duration: {((new Date(wf.completed_at) - new Date(wf.created_at)) / 1000).toFixed(1)}s
              </div>
            )}
          </div>
        </div>

        {/* Context summary */}
        <div className="card">
          <div className="card-header"><span className="card-title">Context</span></div>
          <div className="card-body space-y-2">
            {[
              ['Service UUID',  ctx.service_uuid],
              ['MSISDN',        ctx.msisdn],
              ['ICCID',         ctx.iccid],
              ['HSS sub ID',    ctx.hss_subscriber_id],
              ['HSS MSISDN ID', ctx.hss_msisdn_id],
              ['CGRateS tenant',ctx.cgrates_tenant],
              ['Prepaid',       ctx.is_prepaid !== undefined ? String(ctx.is_prepaid) : undefined],
            ].filter(([, v]) => v).map(([k, v]) => (
              <div key={k}>
                <div className="text-xs text-slate-400">{k}</div>
                <div className="text-xs font-mono text-slate-700 break-all">{v}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Provision steps */}
      {provSteps.length > 0 && (
        <div className="mb-4">
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">
            Provisioning steps ({provSteps.length})
          </div>
          {/* {provSteps.map((s, i) => <StepCard key={s.step_name + i} step={s} index={i}/>)} */}
          {provSteps.map((s, i) => <StepCard key={s.step_name + i} step={s} index={i} ctx={ctx}/>)}
        </div>
      )}

      {/* Rollback steps */}
      {rollbackSteps.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-orange-600 uppercase tracking-wide mb-3">
            ↩ Rollback steps ({rollbackSteps.length})
          </div>
          {/* {rollbackSteps.map((s, i) => <StepCard key={s.step_name + 'rb' + i} step={s} index={i}/>)} */}
          {rollbackSteps.map((s, i) => <StepCard key={s.step_name + 'rb' + i} step={s} index={i} ctx={ctx}/>)}
        </div>
      )}

      {confirmDeprov && (
        <Confirm
          title="Deprovision"
          message="Remove this subscriber from OmniHSS and CGRateS? The MSISDN will revert to dormant state."
          danger
          onConfirm={() => { deprovMut.mutate(); setConfirmDeprov(false) }}
          onCancel={() => setConfirmDeprov(false)}/>
      )}
    </div>
  )
}
