import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { Modal, ErrorBanner } from '../ui'
import { payments } from '../../lib/api'
import { format } from 'date-fns'

export function RecordPaymentModal({ onClose, preselectedCustomerId }) {
  const qc = useQueryClient()
  const { register, handleSubmit, formState: { errors } } = useForm({
    defaultValues: {
      customer_id: preselectedCustomerId || '',
      payment_date: format(new Date(), 'yyyy-MM-dd'),
      method: 'manual',
      currency: 'GBP',
    }
  })

  const mut = useMutation({
    mutationFn: (data) => payments.create({
      ...data,
      amount: Math.round(parseFloat(data.amount_pounds) * 100),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['payments'] })
      qc.invalidateQueries({ queryKey: ['balance'] })
      onClose()
    }
  })

  return (
    <Modal title="Record Payment" onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSubmit(d => mut.mutate(d))} disabled={mut.isPending}>
            {mut.isPending ? 'Recording…' : 'Record Payment'}
          </button>
        </>
      }>
      <ErrorBanner message={mut.error}/>
      <div className="grid grid-cols-2 gap-4">
        {!preselectedCustomerId && (
          <div className="col-span-2">
            <label className="form-label">Customer ID *</label>
            <input className="form-input" {...register('customer_id', { required: 'Required' })} placeholder="Paste customer UUID"/>
          </div>
        )}
        <div>
          <label className="form-label">Amount *</label>
          <input className="form-input" type="number" step="0.01" min="0"
            {...register('amount_pounds', { required: 'Required', min: 0.01 })} placeholder="49.99"/>
          {errors.amount_pounds && <p className="form-error">{errors.amount_pounds.message}</p>}
        </div>
        <div>
          <label className="form-label">Currency</label>
          <select className="form-select" {...register('currency')}>
            <option value="GBP">GBP £</option>
            <option value="EUR">EUR €</option>
            <option value="USD">USD $</option>
          </select>
        </div>
        <div>
          <label className="form-label">Method</label>
          <select className="form-select" {...register('method')}>
            <option value="manual">Manual</option>
            <option value="bank_transfer">Bank Transfer</option>
            <option value="cash">Cash</option>
          </select>
        </div>
        <div>
          <label className="form-label">Payment Date *</label>
          <input className="form-input" type="date" {...register('payment_date', { required: 'Required' })}/>
        </div>
        <div className="col-span-2">
          <label className="form-label">Reference</label>
          <input className="form-input" {...register('reference')} placeholder="Bank ref, receipt number…"/>
        </div>
        <div className="col-span-2">
          <label className="form-label">Invoice ID (optional)</label>
          <input className="form-input" {...register('invoice_id')} placeholder="Leave blank for prepaid top-up"/>
        </div>
      </div>
    </Modal>
  )
}
