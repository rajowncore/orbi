import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { Modal, ErrorBanner } from '../ui'
import { inventory } from '../../lib/api'

export function AddInventoryModal({ onClose }) {
  const qc = useQueryClient()
  const { register, handleSubmit, watch, formState: { errors } } = useForm({ defaultValues: { type: 'msisdn', mode: 'single' } })
  const mode = watch('mode')

  const mut = useMutation({
    mutationFn: (data) => {
      if (data.mode === 'bulk') {
        const values = data.bulk_values.split('\n').map(v => v.trim()).filter(Boolean)
        return inventory.bulk({ type: data.type, values })
      }
      return inventory.create({ type: data.type, value: data.value })
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['inventory'] }); onClose() }
  })

  return (
    <Modal title="Add Inventory" onClose={onClose}
      footer={
        <>
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSubmit(d => mut.mutate(d))} disabled={mut.isPending}>
            {mut.isPending ? 'Saving…' : 'Add to Pool'}
          </button>
        </>
      }>
      <ErrorBanner message={mut.error}/>
      <div className="grid gap-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="form-label">Type</label>
            <select className="form-select" {...register('type')}>
              <option value="msisdn">MSISDN</option>
              <option value="sim">SIM Card (ICCID)</option>
              <option value="other">Other</option>
            </select>
          </div>
          <div>
            <label className="form-label">Mode</label>
            <select className="form-select" {...register('mode')}>
              <option value="single">Single item</option>
              <option value="bulk">Bulk import</option>
            </select>
          </div>
        </div>

        {mode === 'single' ? (
          <div>
            <label className="form-label">Value *</label>
            <input className="form-input" {...register('value', { required: 'Required' })} placeholder="+447700900001 or ICCID"/>
            {errors.value && <p className="form-error">{errors.value.message}</p>}
          </div>
        ) : (
          <div>
            <label className="form-label">Values (one per line) *</label>
            <textarea className="form-input font-mono text-xs" rows={8}
              {...register('bulk_values', { required: 'Required' })}
              placeholder={"+447700900001\n+447700900002\n+447700900003"}/>
          </div>
        )}
      </div>
    </Modal>
  )
}
