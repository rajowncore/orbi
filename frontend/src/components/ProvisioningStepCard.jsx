// ProvisioningStepCard.jsx
// Rich step detail renderer for the provisioning workflow detail page.
// 
// Usage in ProvisioningDetailPage:
//   <StepCard step={s} index={i} ctx={wf.context || {}}/>
//
// ctx = the full workflow context (accumulated across all steps).
// This lets each step card show the relevant values even when
// the step's own result field is empty.

import { useState } from 'react'

// ── Status config ──────────────────────────────────────────────────────────
const S = {
  completed:   { bg: 'bg-emerald-50', border: 'border-emerald-200', text: 'text-emerald-700', icon: '✓', dot: '#059669' },
  failed:      { bg: 'bg-red-50',     border: 'border-red-200',     text: 'text-red-700',     icon: '✗', dot: '#DC2626' },
  running:     { bg: 'bg-brand-50',   border: 'border-brand-200',   text: 'text-brand-700',   icon: '◌', dot: '#1B4FD8' },
  rolled_back: { bg: 'bg-orange-50',  border: 'border-orange-200',  text: 'text-orange-700',  icon: '↩', dot: '#EA580C' },
  pending:     { bg: 'bg-slate-50',   border: 'border-slate-200',   text: 'text-slate-500',   icon: '○', dot: '#94A3B8' },
  skipped:     { bg: 'bg-slate-50',   border: 'border-slate-100',   text: 'text-slate-400',   icon: '–', dot: '#CBD5E1' },
}

// ── Step descriptions ──────────────────────────────────────────────────────
const DESC = {
  resolve_inventory:           'Resolves MSISDN / SIM from Orbi inventory pool and generates service UUID',
  fetch_customer_details:      'Validates customer profile and product package from database',
  hss_lookup_subscriber:       'Searches OmniHSS for existing subscriber record by IMSI',
  hss_create_msisdn:           'Creates or finds MSISDN entry in OmniHSS',
  hss_activate_subscriber:     'Links MSISDN to subscriber and enables IMS in OmniHSS',
  cgrates_create_enum:         'Creates E164/ENUM routing entry for SIP number lookup',
  cgrates_create_filter:       'Creates account filter matching MSISDN, IMSI and service UUID',
  cgrates_create_attributes:   'Creates attribute profile with MSISDN, IMSI, QoS and policy',
  cgrates_create_resources:    'Creates resource profile limiting concurrent sessions to 5',
  cgrates_create_stats:        'Creates stats queue for real-time session metrics',
  cgrates_create_account:      'Creates OCS account with balance alert action triggers',
  cgrates_set_balance:         'Initialises £0 monetary balance bucket in CGRateS',
  orbi_assign_inventory:       'Marks MSISDN and SIM as assigned in Orbi inventory',
  orbi_activate_subscription:  'Records provisioning completion and activates subscription',
  cgrates_remove_action_plans: 'Removes action plans and reloads CGRateS scheduler',
  cgrates_delete_account:      'Deletes CGRateS account and all balance buckets',
  cgrates_delete_attributes:   'Removes attribute profile (MSISDN/IMSI/QoS mapping)',
  cgrates_delete_enum:         'Removes E164/ENUM routing entry',
  cgrates_delete_resources:    'Removes resource profile',
  cgrates_delete_filter:       'Removes account filter rule',
  cgrates_delete_stats:        'Removes stats queue profile',
  hss_revert_subscriber:       'Reverts subscriber to dormant with placeholder MSISDN',
  orbi_release_inventory:      'Returns MSISDN to available pool',
  orbi_deactivate_subscription:'Marks subscription as cancelled',
}

// ── Error hints ────────────────────────────────────────────────────────────
const HINTS = {
  hss_lookup_subscriber:   [
    { match: '404',        hint: 'IMSI not found in OmniHSS — check the SIM is pre-registered in HSS.' },
    { match: 'Connection', hint: 'Cannot reach OmniHSS — check HSS_API_URL in .env.' },
    { match: 'timeout',    hint: 'OmniHSS is slow to respond — check HSS server load.' },
  ],
  hss_create_msisdn: [
    { match: '422',        hint: 'MSISDN already exists. May have been created in a previous attempt — safe to retry.' },
    { match: 'duplicate',  hint: 'MSISDN is already assigned to another subscriber in OmniHSS.' },
  ],
  hss_activate_subscriber: [
    { match: '404',        hint: 'Subscriber ID not found — retry provisioning to re-lookup.' },
    { match: '400',        hint: 'Invalid request body — check MSISDN ID from previous step.' },
  ],
  cgrates_create_enum: [
    { match: 'EXISTS',     hint: 'Entry already exists from a previous attempt — safe to retry.' },
    { match: 'MANDATORY',  hint: 'Missing required field — check CGRateS version compatibility.' },
    { match: 'Connection', hint: 'Cannot reach CGRateS — check CGRATES_API_URL in .env.' },
  ],
  cgrates_create_account: [
    { match: 'ActionTrigger', hint: 'ActionTrigger not found in CGRateS. Hit POST /api/v1/self-care/admin/poll-balances to create them.' },
    { match: 'EXISTS',     hint: 'Account already exists — safe to retry.' },
  ],
  cgrates_set_balance: [
    { match: 'NOT_FOUND',  hint: 'Account was not created — check cgrates_create_account step above.' },
  ],
}

// ── Per-step detail renderer ───────────────────────────────────────────────
// ctx = full workflow context, r = step.result (may be empty)
function StepDetail({ stepName, r = {}, ctx = {} }) {
  const rows = []

  const add = (label, value, type = 'text') => {
    if (value !== undefined && value !== null && value !== '') {
      rows.push({ label, value: String(value), type })
    }
  }

  switch (stepName) {

    case 'resolve_inventory':
      add('Service UUID', ctx.service_uuid || r.service_uuid, 'mono')
      add('MSISDN',       ctx.msisdn,  'mono')
      add('ICCID',        ctx.iccid,   'mono')
      add('IMSI',         ctx.imsi,    'mono')
      if (!ctx.service_uuid && !r.service_uuid)
        add('Note', 'service_uuid not generated — check provisioning config', 'warn')
      break

    case 'fetch_customer_details':
      add('Customer',      ctx.customer_name)
      add('Package',       ctx.package_name)
      add('Credit type',   ctx.is_prepaid ? 'Prepaid' : 'Postpaid')
      add('CGRateS tenant',ctx.cgrates_tenant, 'mono')
      break

    case 'hss_lookup_subscriber':
      if (ctx.hss_subscriber_exists === true) {
        add('Result',            'Subscriber found in OmniHSS', 'success')
        add('HSS subscriber ID', ctx.hss_subscriber_id, 'mono')
      } else if (ctx.hss_subscriber_exists === false) {
        if (!ctx.imsi) {
          add('Result', 'Skipped — no IMSI in context (SIM not assigned or HSS not configured)', 'warn')
          add('Effect', 'hss_activate_subscriber step will also be skipped')
          add('Action', 'Set HSS_API_URL in .env and assign a SIM with IMSI to enable HSS provisioning')
        } else {
          add('Result', 'Not found in OmniHSS — activate step will be skipped', 'warn')
          add('IMSI searched', ctx.imsi, 'mono')
        }
      } else {
        add('Result', 'Skipped — no IMSI available', 'warn')
      }
      break

    case 'hss_create_msisdn':
      add('HSS MSISDN ID', ctx.hss_msisdn_id || r.hss_msisdn_id, 'mono')
      add('MSISDN',        ctx.msisdn, 'mono')
      add('Action', ctx.hss_msisdn_id ? 'Found existing entry' : 'Created new entry')
      break

    case 'hss_activate_subscriber':
      if (ctx.hss_subscriber_id) {
        add('Subscriber ID', ctx.hss_subscriber_id, 'mono')
        add('IMS enabled',   'true', 'success')
        add('MSISDN linked', ctx.hss_msisdn_id, 'mono')
        add('Result',        'Subscriber active and linked to real MSISDN', 'success')
      } else {
        add('Result', 'Skipped — no HSS subscriber found in lookup step', 'warn')
      }
      break

    case 'cgrates_create_enum': {
      const uuid = ctx.service_uuid || r.service_uuid
      add('Profile ID',  uuid ? `ATTR_E164_${uuid}` : undefined, 'mono')
      add('Context',     '*sessions')
      add('Filter',      ctx.msisdn ? `*prefix:~*req.E164Address:${ctx.msisdn}` : undefined, 'mono')
      add('Purpose',     'Routes SIP ENUM lookups for this MSISDN to the IMS core')
      break
    }

    case 'cgrates_create_filter': {
      const uuid = ctx.service_uuid || r.service_uuid
      add('Filter ID',   uuid ? `FLTR_ACCOUNT_${uuid}` : undefined, 'mono')
      const matchVals = [uuid, ctx.imsi, ctx.msisdn].filter(Boolean)
      add('Matches',     matchVals.length ? matchVals.join(' · ') : undefined, 'mono')
      add('Type',        '*string — exact match on Account field')
      if (!uuid) add('Note', 'service_uuid not in context — provisioning may be incomplete', 'warn')
      break
    }

    case 'cgrates_create_attributes': {
      const uuid = ctx.service_uuid || r.service_uuid
      add('Profile ID',  uuid ? `ATTR_ACCOUNT_${uuid}` : undefined, 'mono')
      add('Account',     uuid, 'mono')
      add('MSISDN',      ctx.msisdn, 'mono')
      add('IMSI',        ctx.imsi || '(not set — no SIM with IMSI assigned)')
      add('MaxBitrateDL','5242880 bps (5Mbps default)')
      add('MaxBitrateUL','5242880 bps (5Mbps default)')
      add('PcefPolicy',  'Inactive')
      break
    }

    case 'cgrates_create_resources': {
      const uuid = ctx.service_uuid
      add('Profile ID',    uuid ? `RESOURCE_Account_${uuid}` : undefined, 'mono')
      add('Session limit', '5 concurrent sessions')
      add('TTL',           'Unlimited (-1)')
      add('Blocker',       'false — allows session even if limit exceeded')
      break
    }

    case 'cgrates_create_stats': {
      const uuid = ctx.service_uuid || r.service_uuid
      add('Profile ID',  uuid ? `STATS_Account_${uuid}` : undefined, 'mono')
      add('Metrics',     '*sum#1 (sessions), *sum#~*req.Usage (bytes)')
      add('Queue length','50 samples')
      if (uuid) add('Filter', `FLTR_ACCOUNT_${uuid} · *sessions subsystem`, 'mono')
      else      add('Filter',  '*sessions subsystem')
      break
    }

    case 'cgrates_create_account':
      add('Account',         ctx.service_uuid || r.service_uuid, 'mono')
      add('Tenant',          ctx.cgrates_tenant || 'cgrates.org', 'mono')
      add('Allow negative',  ctx.is_prepaid ? 'false (prepaid — blocked at zero)' : 'true (postpaid)')
      add('Action triggers', 'BalanceExpired · 500MB_Remaining · 0MB_Remaining')
      break

    case 'cgrates_set_balance':
      add('Account',       ctx.service_uuid || r.service_uuid, 'mono')
      add('Balance type',  '*monetary — PAYG Balance')
      add('Initial value', '£0.00 (customer tops up separately)')
      add('Expiry',        '+4320h (6 months from now)')
      add('Blocker',       'true — stops further deductions when exhausted')
      break

    case 'orbi_assign_inventory':
      add('MSISDN',  ctx.msisdn, 'mono')
      add('ICCID',   ctx.iccid,  'mono')
      add('Notes',   ctx.provisioning_notes || r.provisioning_notes)
      break

    case 'orbi_activate_subscription':
      add('Provisioned at', ctx.provisioned_at || r.provisioned_at)
      add('Service UUID',   ctx.service_uuid, 'mono')
      add('Status',         'Subscription created and active', 'success')
      break

    // Deprovision steps
    case 'cgrates_delete_account':
      add('Account removed', ctx.service_uuid, 'mono')
      add('Action', 'Action plans cleared, account deleted, scheduler reloaded')
      break

    case 'hss_revert_subscriber':
      add('Subscriber ID', ctx.hss_subscriber_id, 'mono')
      add('Action', 'IMS disabled, placeholder MSISDN assigned (dormant state)')
      break

    case 'orbi_release_inventory':
      add('MSISDN', ctx.msisdn, 'mono')
      add('Action', 'Status set to available, service_id cleared')
      break

    default:
      // Generic: show non-null result values
      Object.entries(r || {}).forEach(([k, v]) => {
        if (v !== null && v !== undefined && typeof v !== 'object') {
          add(k.replace(/_/g, ' '), v)
        }
      })
  }

  if (rows.length === 0) return null

  return (
    <div className="space-y-2 mt-2">
      {rows.map(({ label, value, type }) => (
        <div key={label} className="flex items-start gap-2 text-xs">
          <span className="text-slate-400 flex-shrink-0" style={{ width: 140 }}>{label}</span>
          <span className={
            type === 'mono'    ? 'font-mono text-slate-700 break-all leading-relaxed' :
            type === 'success' ? 'text-emerald-700 font-medium' :
            type === 'warn'    ? 'text-amber-700' :
                                 'text-slate-600'
          }>
            {value}
          </span>
        </div>
      ))}
    </div>
  )
}

// ── Error hint ─────────────────────────────────────────────────────────────
function ErrorHint({ stepName, errorMessage }) {
  if (!errorMessage) return null
  const hints = HINTS[stepName] || []
  const matched = hints.find(h =>
    errorMessage.toLowerCase().includes(h.match.toLowerCase())
  )
  if (!matched) return null
  return (
    <div className="mt-2 flex items-start gap-2 text-xs bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
      <span className="text-amber-500 flex-shrink-0">💡</span>
      <span className="text-amber-800">{matched.hint}</span>
    </div>
  )
}

// ── Duration formatter ─────────────────────────────────────────────────────
function fmtMs(ms) {
  if (ms === null || ms === undefined) return null
  if (ms < 1000)  return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
}

// ══════════════════════════════════════════════════════════════════════════
// MAIN STEPCARD
// ══════════════════════════════════════════════════════════════════════════
export function StepCard({ step, index, ctx = {} }) {
  const cfg = S[step.status] || S.pending

  // Auto-open failed/rolled-back steps
  const [open, setOpen] = useState(
    step.status === 'failed' || step.status === 'rolled_back'
  )

  const isRollback = step.step_description?.startsWith('ROLLBACK')
  const durationMs = step.started_at && step.completed_at
    ? new Date(step.completed_at) - new Date(step.started_at)
    : null

  const hasDetail = step.status !== 'pending' && step.status !== 'skipped'
  const description = DESC[step.step_name]

  return (
    <div className={`border rounded-xl overflow-hidden mb-2 ${cfg.border} ${isRollback ? 'opacity-85' : ''}`}>

      {/* ── Header row ── */}
      <div
        className={`px-4 py-3 flex items-center gap-3 ${hasDetail ? 'cursor-pointer hover:brightness-[0.97]' : ''} ${cfg.bg}`}
        onClick={() => hasDetail && setOpen(o => !o)}>

        {/* Status dot + icon */}
        <div className={`w-7 h-7 rounded-full flex items-center justify-center text-sm font-semibold flex-shrink-0 ${cfg.bg} ${cfg.text} border ${cfg.border}`}
          style={step.status === 'running' ? { animation: 'spin 1.5s linear infinite' } : {}}>
          {cfg.icon}
        </div>

        {/* Name */}
        <div className="flex-1 min-w-0">
          <div className={`text-sm font-medium ${cfg.text}`}>
            {isRollback && (
              <span className="text-xs bg-orange-100 text-orange-600 border border-orange-200 px-1.5 py-0.5 rounded mr-2">
                ROLLBACK
              </span>
            )}
            {step.step_name.replace(/_/g, ' ')}
          </div>
          {description && (
            <div className="text-xs text-slate-400 mt-0.5 truncate">{description}</div>
          )}
        </div>

        {/* Meta */}
        <div className="flex items-center gap-2.5 flex-shrink-0 text-xs text-slate-400">
          {durationMs !== null && (
            <span className="font-mono tabular-nums">{fmtMs(durationMs)}</span>
          )}
          {step.started_at && (
            <span className="hidden sm:inline tabular-nums">
              {new Date(step.started_at).toLocaleTimeString()}
            </span>
          )}
          {(step.attempt || 0) > 1 && (
            <span className="bg-amber-100 text-amber-700 border border-amber-200 px-1.5 py-0.5 rounded text-[10px] font-semibold">
              Attempt {step.attempt}
            </span>
          )}
          {hasDetail && (
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="2" className="text-slate-300"
              style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform .15s' }}>
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          )}
        </div>
      </div>

      {/* ── Expanded body ── */}
      {open && hasDetail && (
        <div className="px-4 py-3 border-t border-slate-100 bg-white space-y-3">

          {/* Timestamps + attempt */}
          <div className="grid grid-cols-3 gap-3 text-xs">
            <div>
              <div className="text-slate-400 mb-0.5">Attempt</div>
              <div className="font-medium text-slate-700">{step.attempt || 1}</div>
            </div>
            {step.started_at && (
              <div>
                <div className="text-slate-400 mb-0.5">Started</div>
                <div className="font-medium text-slate-700">
                  {new Date(step.started_at).toLocaleString()}
                </div>
              </div>
            )}
            {step.completed_at && (
              <div>
                <div className="text-slate-400 mb-0.5">Completed</div>
                <div className="font-medium text-slate-700">
                  {new Date(step.completed_at).toLocaleString()}
                </div>
              </div>
            )}
          </div>

          {/* Step-specific output */}
          {step.status === 'completed' && (
            <div>
              <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">
                Step output
              </div>
              <StepDetail stepName={step.step_name} r={step.result || {}} ctx={ctx}/>
            </div>
          )}

          {/* Error + hint */}
          {step.error_message && (
            <div>
              <div className="text-xs font-semibold text-red-500 uppercase tracking-wide mb-1.5">
                Error
              </div>
              <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2.5 text-xs text-red-700 font-mono leading-relaxed break-all">
                {step.error_message}
              </div>
              <ErrorHint stepName={step.step_name} errorMessage={step.error_message}/>
            </div>
          )}

          {/* Full description at bottom */}
          {step.step_description && (
            <div className="text-xs text-slate-400 pt-1 border-t border-slate-50 leading-relaxed">
              {step.step_description.replace('ROLLBACK: ', '')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
