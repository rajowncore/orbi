import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { Modal, ErrorBanner, Spinner } from '../ui'
import { orders, products, inventory, subscriptions as subsApi } from '../../lib/api'
import { fmt } from '../../lib/utils'

export function CreateOrderModal({ onClose, preselectedCustomerId }) {
  const qc = useQueryClient()
  const { register, handleSubmit, watch, formState: { errors } } = useForm({
    defaultValues: { customer_id: preselectedCustomerId || '' }
  })

  const selectedProductId = watch('product_id')
  const customerId = preselectedCustomerId || watch('customer_id')

  const { data: productList = [], isLoading: loadingProducts } = useQuery({
    queryKey: ['products'],
    queryFn: () => products.list()
  })

  const chosenProduct = productList.find(p => p.id === selectedProductId)
  const isAddon = chosenProduct?.product_type === 'addon' || chosenProduct?.product_type === 'roaming'

  // Fetch customer's active subscriptions when add-on is selected
  const { data: activeSubs = [], isLoading: loadingSubs } = useQuery({
    queryKey: ['subscriptions', customerId, 'base'],
    queryFn: () => subsApi.list(customerId, 'base'),
    enabled: !!customerId && isAddon,
  })

  // Fetch all products to show subscription names
  const activeBaseSubs = activeSubs.filter(s => s.status === 'active')

  // For each subscription, find the product name from productList
  const subsWithNames = activeBaseSubs.map(s => ({
    ...s,
    productName: productList.find(p => p.id === s.product_id)?.name || 'Unknown package',
  }))

  const { data: availableInv = [] } = useQuery({
    queryKey: ['inventory-available', chosenProduct?.inventory_type],
    queryFn: () => inventory.available(chosenProduct?.inventory_type),
    enabled: !!chosenProduct?.requires_inventory,
  })

  const mut = useMutation({
    mutationFn: orders.create,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['orders'] })
      qc.invalidateQueries({ queryKey: ['subscriptions', customerId] })
      qc.invalidateQueries({ queryKey: ['customer-orders', customerId] })
      onClose()
    }
  })

  const onSubmit = (data) => {
    // Find the order_id from the selected subscription
    const selectedSub = activeBaseSubs.find(s => s.id === data.subscription_id)

    mut.mutate({
      customer_id:        customerId,
      product_id:         data.product_id,
      inventory_item_id:  data.inventory_item_id  || undefined,
      parent_order_id:    selectedSub?.order_id   || undefined,
    })
  }

  return (
    <Modal title="New Order" onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSubmit(onSubmit)} disabled={mut.isPending}>
            {mut.isPending ? 'Creating…' : 'Create Order'}
          </button>
        </>
      }>
      <ErrorBanner message={mut.error}/>
      <div className="grid gap-4">

        {!preselectedCustomerId && (
          <div>
            <label className="form-label">Customer ID *</label>
            <input className="form-input"
              {...register('customer_id', { required: 'Required' })}
              placeholder="Paste customer UUID"/>
            {errors.customer_id && <p className="form-error">{errors.customer_id.message}</p>}
          </div>
        )}

        <div>
          <label className="form-label">Package *</label>
          {loadingProducts ? <Spinner/> : (
            <select className="form-select"
              {...register('product_id', { required: 'Required' })}>
              <option value="">Select a package…</option>
              <optgroup label="Base packages">
                {productList.filter(p => p.status === 'active' && p.product_type === 'base').map(p => (
                  <option key={p.id} value={p.id}>
                    {p.name} — {fmt.money(p.price_config?.amount, p.currency)}
                  </option>
                ))}
              </optgroup>
              <optgroup label="Add-ons">
                {productList.filter(p => p.status === 'active' && p.product_type === 'addon').map(p => (
                  <option key={p.id} value={p.id}>
                    {p.name} — {fmt.money(p.price_config?.amount, p.currency)}
                  </option>
                ))}
              </optgroup>
              <optgroup label="Roaming">
                {productList.filter(p => p.status === 'active' && p.product_type === 'roaming').map(p => (
                  <option key={p.id} value={p.id}>
                    {p.name} — {fmt.money(p.price_config?.amount, p.currency)}
                  </option>
                ))}
              </optgroup>
            </select>
          )}
          {errors.product_id && <p className="form-error">{errors.product_id.message}</p>}
        </div>

        {/* Base subscription selector — shown for add-ons and roaming */}
        {isAddon && (
          <div>
            <label className="form-label">Attach to subscription *</label>
            {loadingSubs ? <Spinner/> :
             subsWithNames.length === 0 ? (
              <div className="text-sm text-amber-600 bg-amber-50 border border-amber-200 px-3 py-2 rounded-lg">
                No active subscriptions found. Activate a base package first.
              </div>
            ) : (
              <select className="form-select"
                {...register('subscription_id', { required: isAddon ? 'Required' : false })}>
                <option value="">Select active subscription…</option>
                {subsWithNames.map(s => (
                  <option key={s.id} value={s.id}>
                    {s.productName}
                    {s.start_date ? ` — since ${new Date(s.start_date).toLocaleDateString('en-GB')}` : ''}
                  </option>
                ))}
              </select>
            )}
            {errors.subscription_id && <p className="form-error">{errors.subscription_id.message}</p>}
            <p className="text-xs text-slate-400 mt-1">
              Add-on will be stacked on top of this subscription
            </p>
          </div>
        )}

        {/* Inventory */}
        {chosenProduct?.requires_inventory && (
          <div>
            <label className="form-label">
              Assign {chosenProduct.inventory_type?.toUpperCase()} *
            </label>
            {availableInv.length === 0 ? (
              <p className="text-sm text-amber-600 bg-amber-50 border border-amber-200 px-3 py-2 rounded-lg">
                No available {chosenProduct.inventory_type} items. Import inventory first.
              </p>
            ) : (
              <select className="form-select"
                {...register('inventory_item_id',
                  { required: chosenProduct.requires_inventory ? 'Required' : false })}>
                <option value="">Select {chosenProduct.inventory_type}…</option>
                {availableInv.map(i => (
                  <option key={i.id} value={i.id}>{i.value}</option>
                ))}
              </select>
            )}
            {errors.inventory_item_id && <p className="form-error">{errors.inventory_item_id.message}</p>}
          </div>
        )}

        {/* Product summary card */}
        {chosenProduct && (
          <div className="bg-brand-50 border border-brand-100 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm font-medium text-brand-700">{chosenProduct.name}</span>
              {isAddon && (
                <span className="text-xs bg-amber-100 text-amber-700 border border-amber-200 px-2 py-0.5 rounded-full capitalize">
                  {chosenProduct.product_type}
                </span>
              )}
            </div>
            {chosenProduct.allowances && (
              <div className="text-xs text-slate-600 flex gap-3 flex-wrap">
                {chosenProduct.allowances.data_mb    && <span>📶 {chosenProduct.allowances.data_mb}MB</span>}
                {chosenProduct.allowances.voice_mins && <span>📞 {chosenProduct.allowances.voice_mins} mins</span>}
                {chosenProduct.allowances.sms        && <span>💬 {chosenProduct.allowances.sms} SMS</span>}
              </div>
            )}
            <div className="text-xs text-slate-500 mt-1">
              {fmt.money(chosenProduct.price_config?.amount, chosenProduct.currency)}
              {chosenProduct.billing_model === 'recurring' ? '/month' :
               chosenProduct.billing_model === 'one_time'  ? ' one-time' : ''}
            </div>
          </div>
        )}

      </div>
    </Modal>
  )
}
