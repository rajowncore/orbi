// src/components/ProvisioningPanel.jsx
// Shows provisioning workflow status per order — step-by-step progress,
// errors, rollback status, and manual trigger/retry buttons.

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'											  
import { provisioning as provApi } from '../lib/api'
import { fmt, statusBadge } from '../lib/utils'
import { Spinner, Confirm } from './ui'

// ── Status helpers ─────────────────────────────────────────────────────────

const WF_COLORS = {
  pending:      { bg: 'bg-slate-100',    text: 'text-slate-600',   dot: '#94A3B8' },
  running:      { bg: 'bg-brand-50',     text: 'text-brand-600',   dot: '#1B4FD8' },
  completed:    { bg: 'bg-emerald-50',   text: 'text-emerald-700', dot: '#059669' },
  failed:       { bg: 'bg-red-50',       text: 'text-red-700',     dot: '#DC2626' },
  rolling_back: { bg: 'bg-amber-50',     text: 'text-amber-700',   dot: '#D97706' },
  rolled_back:  { bg: 'bg-orange-50',    text: 'text-orange-700',  dot: '#EA580C' },
}

const STEP_ICONS = {
  pending:     { icon: '○', color: '#94A3B8' },
  running:     { icon: '◌', color: '#1B4FD8', spin: true },
  completed:   { icon: '✓', color: '#059669' },
  failed:      { icon: '✗', color: '#DC2626' },
  skipped:     { icon: '–', color: '#CBD5E1' },
  rolled_back: { icon: '↩', color: '#EA580C' },
}

function StepIcon({ status }) {
  const cfg = STEP_ICONS[status] || STEP_ICONS.pending
  return (
    <span style={{ color: cfg.color, fontSize: 14, fontWeight: 600,
      display: 'inline-block',
      animation: cfg.spin ? 'spin 1s linear infinite' : 'none' }}>
      {cfg.icon}
    </span>
  )
}

function WFBadge({ status }) {
  const cfg = WF_COLORS[status] || WF_COLORS.pending
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2 py-0.5 rounded-full ${cfg.bg} ${cfg.text}`}>
      <span style={{ width: 6, height: 6, borderRadius: '50%',
        background: cfg.dot, display: 'inline-block',
        animation: status === 'running' ? 'pulse 1.5s infinite' : 'none'}}/>
      {status?.replace(/_/g, ' ')}
    </span>
  )
}

// ── Single workflow card ───────────────────────────────────────────────────

function WorkflowCard({ orderId, orderNumber }) {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState(false)
  const [confirm, setConfirm]   = useState(null)

  const { data: wf, isLoading, error } = useQuery({
    queryKey: ['provisioning-workflow', orderId],
    queryFn:  () => provApi.getWorkflow(orderId),
    refetchInterval: (data) => {
      // Poll every 2s while running or rolling back
      return data?.status === 'running' || data?.status === 'rolling_back' ? 2000 : false
    },
    retry: false,
  })

  const provisionMut = useMutation({
    mutationFn: () => provApi.provision(orderId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['provisioning-workflow', orderId] }),
  })

  const deprovisionMut = useMutation({
    mutationFn: () => provApi.deprovision(orderId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['provisioning-workflow', orderId] }),
  })

  // Not provisioned yet
  if (error || !wf) {
    return (
      <div className="border border-slate-200 rounded-xl p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium text-slate-700">{orderNumber}</div>
            <div className="text-xs text-slate-400 mt-0.5">Not provisioned — will trigger automatically on activation</div>
          </div>
          {/* <button
            className="btn btn-primary btn-sm"
            disabled={provisionMut.isPending}
            onClick={() => setConfirm({ type: 'provision' })}>
            {provisionMut.isPending ? <><Spinner size={12}/> Provisioning…</> : '▶ Provision'}
          </button> */}
        </div>
        {provisionMut.error && (
          <div className="mt-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {provisionMut.error}
          </div>
        )}
        {confirm && (
          <Confirm title="Provision Subscription"
            message={`Start provisioning ${orderNumber} on OmniHSS and CGRateS?`}
            onConfirm={() => { provisionMut.mutate(); setConfirm(null) }}
            onCancel={() => setConfirm(null)}/>
        )}
      </div>
    )
  }

  const steps      = wf.steps || []
  const done       = steps.filter(s => s.status === 'completed').length
  const total      = steps.filter(s => !s.step_name.startsWith('hss_rollback') &&
                                       !s.step_name.includes('_delete_') &&
                                       !s.step_name.includes('_release_') &&
                                       !s.step_name.includes('_deactivate_') &&
                                       !s.step_name.includes('_revert_')).length
  const pct        = total > 0 ? Math.round((done / total) * 100) : 0
  const isActive   = wf.status === 'running' || wf.status === 'rolling_back'
  const canRetry   = wf.status === 'failed' || wf.status === 'rolled_back'
  const canDeprov  = wf.status === 'completed'

  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">

      {/* Header */}
      <div className="px-4 py-3 flex items-center justify-between gap-3 cursor-pointer hover:bg-slate-50"
        onClick={() => setExpanded(e => !e)}>
        <div className="flex items-center gap-3 min-w-0">
          <div>
            <div className="text-sm font-medium text-slate-800">{orderNumber}</div>
            <div className="text-xs text-slate-400 mt-0.5 capitalize">
              {wf.workflow_type?.replace(/_/g, ' ')} · {fmt.datetime(wf.created_at)}
            </div>
          </div>
          <WFBadge status={wf.status}/>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Progress bar — shown when running */}
          {(wf.status === 'running' || wf.status === 'completed') && (
            <div className="flex items-center gap-2">
              <div style={{width:80,height:5,background:'#E2E8F0',borderRadius:9}}>
                <div style={{width:`${pct}%`,height:'100%',
                  background: wf.status==='completed' ? '#059669' : '#1B4FD8',
                  borderRadius:9,transition:'width .3s'}}/>
              </div>
              <span className="text-xs text-slate-500 font-mono">{pct}%</span>
            </div>
          )}

          {/* {canRetry && (
            <button className="btn btn-primary btn-sm"
              disabled={provisionMut.isPending}
              onClick={e => { e.stopPropagation(); setConfirm({ type: 'retry' }) }}>
              ↺ Retry
            </button>
          )} */}
          {canDeprov && (
            <button className="btn btn-danger btn-sm"
              disabled={deprovisionMut.isPending}
              onClick={e => { e.stopPropagation(); setConfirm({ type: 'deprovision' }) }}>
              Deprovision
            </button>
          )}

          <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" className="text-slate-400 flex-shrink-0"
            style={{transform: expanded ? 'rotate(180deg)' : 'none', transition:'transform .15s'}}>
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
      </div>

      {/* Error banner */}
      {wf.error_message && (
        <div className="px-4 pb-3">
          <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-xs text-red-700">
            <span className="font-semibold">Failed at {wf.error_step?.replace(/_/g,' ')}: </span>
            {wf.error_message}
          </div>
        </div>
      )}

      {/* Steps — expanded view */}
      {expanded && steps.length > 0 && (
        <div className="border-t border-slate-100">
          {/* Provision steps */}
          {steps.filter(s => !s.step_name.startsWith('ROLLBACK') &&
            !s.step_description?.startsWith('ROLLBACK')).length > 0 && (
            <div>
              <div className="px-4 py-2 text-xs font-semibold text-slate-400 uppercase tracking-wide bg-slate-50">
                Provision steps
              </div>
              {steps
                .filter(s => !s.step_description?.startsWith('ROLLBACK'))
                .map((s, i) => (
                  <StepRow key={s.step_name + i} step={s}/>
                ))}
            </div>
          )}
          {/* Rollback steps */}
          {steps.filter(s => s.step_description?.startsWith('ROLLBACK')).length > 0 && (
            <div>
              <div className="px-4 py-2 text-xs font-semibold text-amber-600 uppercase tracking-wide bg-amber-50">
                ↩ Rollback steps
              </div>
              {steps
                .filter(s => s.step_description?.startsWith('ROLLBACK'))
                .map((s, i) => (
                  <StepRow key={s.step_name + 'rb' + i} step={s} isRollback/>
                ))}
            </div>
          )}
        </div>
      )}

      {/* Empty steps */}
      {expanded && steps.length === 0 && (
        <div className="px-4 py-6 text-center text-xs text-slate-400 border-t border-slate-100">
          No step details available
        </div>
      )}

      {confirm && (
        <Confirm
          title={confirm.type === 'deprovision' ? 'Deprovision Subscription' :
                 confirm.type === 'retry'        ? 'Retry Provisioning' :
                                                   'Provision Subscription'}
          message={
            confirm.type === 'deprovision'
              ? `Remove ${orderNumber} from OmniHSS and CGRateS? The MSISDN will be returned to dormant state.`
              : confirm.type === 'retry'
              ? `Retry provisioning ${orderNumber}? Completed steps will be skipped.`
              : `Start provisioning ${orderNumber} on OmniHSS and CGRateS?`
          }
          danger={confirm.type === 'deprovision'}
          onConfirm={() => {
            if (confirm.type === 'deprovision') deprovisionMut.mutate()
            else provisionMut.mutate()
            setConfirm(null)
          }}
          onCancel={() => setConfirm(null)}/>
      )}
    </div>
  )
}

function StepRow({ step, isRollback }) {
  const [open, setOpen] = useState(step.status === 'failed')

  const durationMs = step.started_at && step.completed_at
    ? new Date(step.completed_at) - new Date(step.started_at)
    : null

  return (
    <div className="border-b border-slate-100 last:border-b-0">
      <div
        className="px-4 py-2.5 flex items-center gap-3 hover:bg-slate-50 cursor-pointer"
        onClick={() => setOpen(o => !o)}>
        <StepIcon status={step.status}/>
        <div className="flex-1 min-w-0">
          <span className="text-sm text-slate-700">
            {step.step_name.replace(/_/g, ' ')}
          </span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {durationMs !== null && (
            <span className="text-xs text-slate-400 font-mono">
              {durationMs < 1000 ? `${durationMs}ms` : `${(durationMs/1000).toFixed(1)}s`}
            </span>
          )}
          {step.status === 'running' && <Spinner size={12}/>}
          {step.error_message && (
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
              stroke="#DC2626" strokeWidth="2.5">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
          )}
        </div>
      </div>

      {open && step.error_message && (
        <div className="px-4 pb-3 ml-7">
          <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-xs text-red-700 font-mono">
            {step.error_message}
          </div>
        </div>
      )}
      {open && step.status === 'completed' && step.step_name === 'cgrates_create_account' && (
        <div className="px-4 pb-3 ml-7">
          <div className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2">
            CGRateS account created with action triggers: BalanceExpired, 500MB_Remaining, 0MB_Remaining
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main panel — shown on customer 360 ────────────────────────────────────

export function ProvisioningPanel({ orders = [] }) {
  // Only show orders that are active or have been activated
  const relevantOrders = orders.filter(o =>
    ['active', 'suspended', 'cancelled'].includes(o.status)
  )

  if (relevantOrders.length === 0) return null

  return (
    <div className="card mb-4">
      <div className="card-header">
        <span className="card-title">Provisioning</span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">OmniHSS · CGRateS</span>
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse inline-block"/>
        </div>
      </div>
      <div className="p-4 space-y-3">
        {relevantOrders.map(o => (
          <WorkflowCard key={o.id} orderId={o.id} orderNumber={o.order_number}/>
        ))}
      </div>
    </div>
  )
}

// ── Global provisioning monitor — shown on Orders page ────────────────────

export function ProvisioningMonitor() {
  const nav = useNavigate()					   
  const [statusFilter, setStatusFilter] = useState('')
  
  const { data: workflows = [], isLoading } = useQuery({
    queryKey: ['provisioning-all', statusFilter],
    queryFn:  () => provApi.listWorkflows(statusFilter || undefined),
    refetchInterval: 5000,
  })

  const statusColor = {
    completed:    'badge-success',
    running:      'badge-info',
    failed:       'badge-danger',
    rolled_back:  'badge-warning',
    rolling_back: 'badge-warning',
    pending:      'badge-neutral',
  }

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Provisioning Monitor</span>
        <div className="flex items-center gap-2">
          <select className="form-select" style={{width:150}} value={statusFilter}
            onChange={e => setStatusFilter(e.target.value)}>
            <option value="">All statuses</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="rolled_back">Rolled back</option>
          </select>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead><tr>
            <th className="table-th">Order</th>
            <th className="table-th">Type</th>
            <th className="table-th">Status</th>
            <th className="table-th">Steps</th>
            <th className="table-th">Error</th>
            <th className="table-th">Started</th>
            <th className="table-th">Duration</th>
          </tr></thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={7} className="table-td text-center py-8">
                <Spinner size={20}/>
              </td></tr>
            ) : workflows.length === 0 ? (
              <tr><td colSpan={7} className="table-td text-center text-slate-400 py-8">
                No provisioning workflows yet
              </td></tr>
            ) : workflows.map(wf => {
              const steps     = wf.steps || []
              const completed = steps.filter(s => s.status === 'completed').length
              const durationMs = wf.created_at && wf.completed_at
                ? new Date(wf.completed_at) - new Date(wf.created_at) : null

              return (
                <tr key={wf.id} className="table-row" onClick={() => nav(`/provisioning/${wf.order_id}`)}>
                  <td className="table-td font-mono text-xs text-slate-500">
                    {wf.order_id?.slice(0, 8)}…
                  </td>
                  <td className="table-td">
                    <span className="chip capitalize">
                      {wf.workflow_type?.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td className="table-td">
                    <WFBadge status={wf.status}/>
                  </td>
                  <td className="table-td text-xs text-slate-500 font-mono">
                    {completed}/{steps.length}
                  </td>
                  <td className="table-td text-xs text-red-600 max-w-xs truncate">
                    {wf.error_step
                      ? <span title={wf.error_message}>
                          {wf.error_step.replace(/_/g,' ')}
                        </span>
                      : <span className="text-slate-300">—</span>}
                  </td>
                  <td className="table-td text-xs text-slate-400">
                    {fmt.datetime(wf.created_at)}
                  </td>
                  <td className="table-td text-xs text-slate-400 font-mono">
                    {durationMs !== null
                      ? durationMs < 60000
                        ? `${(durationMs/1000).toFixed(1)}s`
                        : `${Math.floor(durationMs/60000)}m ${Math.floor((durationMs%60000)/1000)}s`
                      : wf.status === 'running' ? '⏱ running…' : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
