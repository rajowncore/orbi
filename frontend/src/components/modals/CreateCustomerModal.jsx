import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { Modal, ErrorBanner } from '../ui'
import { customers } from '../../lib/api'

export function CreateCustomerModal({ onClose }) {
  const qc = useQueryClient()
  const { register, handleSubmit, formState: { errors } } = useForm({
    defaultValues: { credit_type: 'postpaid', currency: 'GBP', billing_cycle_day: 1 }
  })

  const mut = useMutation({
    mutationFn: customers.create,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['customers'] }); onClose() }
  })

  return (
    <Modal title="New Customer" onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSubmit(d => mut.mutate(d))} disabled={mut.isPending}>
            {mut.isPending ? 'Creating…' : 'Create Customer'}
          </button>
        </>
      }>
      <ErrorBanner message={mut.error}/>
      <div className="grid grid-cols-2 gap-4">
        <div className="col-span-2">
          <label className="form-label">Full Name *</label>
          <input className="form-input" {...register('name', { required: 'Required' })} placeholder="Jane Smith"/>
          {errors.name && <p className="form-error">{errors.name.message}</p>}
        </div>
        <div className="col-span-2">
          <label className="form-label">Email *</label>
          <input className="form-input" type="email" {...register('email', { required: 'Required' })} placeholder="jane@example.com"/>
          {errors.email && <p className="form-error">{errors.email.message}</p>}
        </div>
        <div>
          <label className="form-label">Phone</label>
          <input className="form-input" {...register('phone')} placeholder="+44 7700 900000"/>
        </div>
        <div>
          <label className="form-label">Credit Type</label>
          <select className="form-select" {...register('credit_type')}>
            <option value="postpaid">Postpaid</option>
            <option value="prepaid">Prepaid</option>
          </select>
        </div>
        <div className="col-span-2">
          <label className="form-label">Address</label>
          <textarea className="form-input" rows={2} {...register('address')} placeholder="Street, City, Postcode"/>
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
          <label className="form-label">Billing Cycle Day</label>
          <input className="form-input" type="number" min={1} max={28} {...register('billing_cycle_day')}/>
        </div>
      </div>
    </Modal>
  )
}
