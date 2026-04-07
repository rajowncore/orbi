import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { Modal, ErrorBanner } from '../ui'
import { products } from '../../lib/api'

export function CreateProductModal({ onClose }) {
  const qc = useQueryClient()
  const { register, handleSubmit, watch, formState: { errors } } = useForm({
    defaultValues: { billing_model: 'recurring', product_type: 'base', currency: 'GBP', requires_inventory: true }
  })
  const billingModel = watch('billing_model')

  const mut = useMutation({
    mutationFn: (data) => {
      // Build price_config and allowances from form fields
      let price_config = {}
      if (data.billing_model === 'recurring') price_config = { amount: Math.round(parseFloat(data.price_amount || 0) * 100), interval: 'month', interval_count: 1 }
      else if (data.billing_model === 'one_time') price_config = { amount: Math.round(parseFloat(data.price_amount || 0) * 100) }
      else if (data.billing_model === 'metered') price_config = { unit_price: Math.round(parseFloat(data.price_amount || 0) * 100), aggregation: 'sum' }

      const allowances = {}
      if (data.data_mb)    allowances.data_mb    = parseInt(data.data_mb)
      if (data.voice_mins) allowances.voice_mins = parseInt(data.voice_mins)
      if (data.sms)        allowances.sms        = parseInt(data.sms)

      return products.create({ ...data, price_config, allowances: Object.keys(allowances).length ? allowances : null })
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['products'] }); onClose() }
  })

  return (
    <Modal title="New Product" onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSubmit(d => mut.mutate(d))} disabled={mut.isPending}>
            {mut.isPending ? 'Creating…' : 'Create Product'}
          </button>
        </>
      }>
      <ErrorBanner message={mut.error}/>
      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2">
          <label className="form-label">Product Name *</label>
          <input className="form-input" {...register('name', { required: 'Required' })} placeholder="e.g. Home Mobile"/>
          {errors.name && <p className="form-error">{errors.name.message}</p>}
        </div>
        <div className="col-span-2">
          <label className="form-label">Description</label>
          <textarea className="form-input" rows={2} {...register('description')} placeholder="Brief description"/>
        </div>
        <div>
          <label className="form-label">Product Type</label>
          <select className="form-select" {...register('product_type')}>
            <option value="base">Base package</option>
            <option value="addon">Add-on / bolt-on</option>
            <option value="roaming">Roaming</option>
          </select>
        </div>
        <div>
          <label className="form-label">Billing Model</label>
          <select className="form-select" {...register('billing_model')}>
            <option value="recurring">Recurring (monthly)</option>
            <option value="one_time">One-time charge</option>
            <option value="metered">Metered / usage-based</option>
          </select>
        </div>
        <div>
          <label className="form-label">Price ({billingModel === 'recurring' ? '/month' : billingModel === 'metered' ? 'per unit' : 'one-time'})</label>
          <input className="form-input" type="number" step="0.01" min="0" {...register('price_amount')} placeholder="19.99"/>
        </div>
        <div>
          <label className="form-label">Currency</label>
          <select className="form-select" {...register('currency')}>
            <option value="GBP">GBP £</option>
            <option value="EUR">EUR €</option>
            <option value="USD">USD $</option>
          </select>
        </div>

        <div className="col-span-2 pt-2 border-t border-slate-100">
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">Bundle Allowances (optional)</div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="form-label">Data (MB)</label>
              <input className="form-input" type="number" {...register('data_mb')} placeholder="1024"/>
            </div>
            <div>
              <label className="form-label">Voice (mins)</label>
              <input className="form-input" type="number" {...register('voice_mins')} placeholder="100"/>
            </div>
            <div>
              <label className="form-label">SMS</label>
              <input className="form-input" type="number" {...register('sms')} placeholder="100"/>
            </div>
          </div>
        </div>

        <div className="col-span-2 flex items-center gap-2">
          <input type="checkbox" id="req-inv" className="rounded" {...register('requires_inventory')}/>
          <label htmlFor="req-inv" className="text-sm text-slate-600">Requires MSISDN/SIM assignment at activation</label>
        </div>
        {watch('requires_inventory') && (
          <div>
            <label className="form-label">Inventory Type</label>
            <select className="form-select" {...register('inventory_type')}>
              <option value="msisdn">MSISDN</option>
              <option value="sim">SIM card</option>
            </select>
          </div>
        )}
      </div>
    </Modal>
  )
}
