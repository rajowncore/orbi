import { format, parseISO } from 'date-fns'
import clsx from 'clsx'

export { clsx }

export const fmt = {
  money:  (cents, currency = 'GBP') =>
    new Intl.NumberFormat('en-GB', { style: 'currency', currency }).format((cents || 0) / 100),
  date:   (d) => d ? format(typeof d === 'string' ? parseISO(d) : d, 'd MMM yyyy') : '—',
  datetime:(d) => d ? format(typeof d === 'string' ? parseISO(d) : d, 'd MMM yyyy HH:mm') : '—',
  num:    (n) => new Intl.NumberFormat('en-GB').format(n || 0),
}

export function statusBadge(status) {
  const map = {
    active:     'badge-success',
    paid:       'badge-success',
    processed:  'badge-success',
    rated:      'badge-success',
    finalised:  'badge-success',
    pending:    'badge-warning',
    draft:      'badge-info',
    sent:       'badge-warning',
    suspended:  'badge-warning',
    processing: 'badge-warning',
    reserved:   'badge-warning',
    cancelled:  'badge-danger',
    failed:     'badge-danger',
    void:       'badge-danger',
    closed:     'badge-danger',
    available:  'badge-success',
    assigned:   'badge-info',
    ported_out: 'badge-neutral',
    decommissioned: 'badge-neutral',
    paused:     'badge-neutral',
    archived:   'badge-neutral',
  }
  return map[status] || 'badge-neutral'
}

export function productTypeBadge(type) {
  const map = { base: 'chip', addon: 'bg-amber-50 border-amber-200 text-amber-700 text-xs px-2 py-0.5 rounded-full border inline-flex', roaming: 'bg-sky-50 border-sky-200 text-sky-700 text-xs px-2 py-0.5 rounded-full border inline-flex' }
  return map[type] || 'chip'
}
