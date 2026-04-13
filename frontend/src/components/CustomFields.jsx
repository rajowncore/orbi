// src/components/CustomFields.jsx
// Allows operators to add/edit arbitrary key-value pairs on any entity
// stored in the entity's `extra` JSON column.
//
// Usage:
//   <CustomFieldsEditor value={customer.extra} onChange={setExtra}/>
//   <CustomFieldsDisplay value={customer.extra}/>
//
// Field definitions can be pre-configured in Settings (stored in localStorage)
// so commonly used fields (e.g. "Account Manager", "Contract Ref") appear
// automatically on every customer form.

import { useState } from 'react'

const PRESETS_KEY = 'orbi_custom_field_presets'

export function getPresets(entity = 'customer') {
  try {
    const all = JSON.parse(localStorage.getItem(PRESETS_KEY) || '{}')
    return all[entity] || []
  } catch { return [] }
}

export function savePreset(entity = 'customer', fieldName) {
  try {
    const all  = JSON.parse(localStorage.getItem(PRESETS_KEY) || '{}')
    const list = all[entity] || []
    if (!list.includes(fieldName)) {
      all[entity] = [...list, fieldName]
      localStorage.setItem(PRESETS_KEY, JSON.stringify(all))
    }
  } catch {}
}

export function removePreset(entity = 'customer', fieldName) {
  try {
    const all  = JSON.parse(localStorage.getItem(PRESETS_KEY) || '{}')
    const list = (all[entity] || []).filter(f => f !== fieldName)
    all[entity] = list
    localStorage.setItem(PRESETS_KEY, JSON.stringify(all))
  } catch {}
}

// ── Read-only display ──────────────────────────────────────────────────────

export function CustomFieldsDisplay({ value, entity = 'customer' }) {
  if (!value || Object.keys(value).length === 0) return null
  return (
    <div className="mt-3 pt-3 border-t border-slate-100">
      <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">
        Custom fields
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-2">
        {Object.entries(value).map(([k, v]) => (
          <div key={k}>
            <div className="text-xs text-slate-400">{k}</div>
            <div className="text-sm text-slate-700 truncate">{String(v)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Editable form ──────────────────────────────────────────────────────────

export function CustomFieldsEditor({ value = {}, onChange, entity = 'customer' }) {
  const [pairs, setPairs]     = useState(() =>
    Object.entries(value || {}).map(([k, v]) => ({ k, v }))
  )
  const [newKey, setNewKey]   = useState('')
  const [newVal, setNewVal]   = useState('')
  const presets               = getPresets(entity)

  const emit = (updated) => {
    const obj = {}
    updated.forEach(({ k, v }) => { if (k.trim()) obj[k.trim()] = v })
    onChange(obj)
  }

  const update = (i, field, val) => {
    const next = pairs.map((p, idx) => idx === i ? { ...p, [field]: val } : p)
    setPairs(next)
    emit(next)
  }

  const add = (key = newKey, val = newVal) => {
    if (!key.trim()) return
    const next = [...pairs, { k: key.trim(), v: val }]
    setPairs(next)
    emit(next)
    setNewKey('')
    setNewVal('')
    savePreset(entity, key.trim())
  }

  const remove = (i) => {
    const next = pairs.filter((_, idx) => idx !== i)
    setPairs(next)
    emit(next)
  }

  // Preset fields not yet added
  const unusedPresets = presets.filter(p => !pairs.find(pair => pair.k === p))

  return (
    <div>
      <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2 flex items-center justify-between">
        <span>Custom fields</span>
        <span className="text-slate-300 font-normal normal-case tracking-normal">
          Stored as JSON on the entity
        </span>
      </div>

      {/* Existing pairs */}
      <div className="space-y-2 mb-3">
        {pairs.map((pair, i) => (
          <div key={i} className="flex gap-2 items-center">
            <input className="form-input text-xs" style={{width:'40%'}}
              value={pair.k}
              onChange={e => update(i, 'k', e.target.value)}
              placeholder="Field name"/>
            <input className="form-input text-xs flex-1"
              value={pair.v}
              onChange={e => update(i, 'v', e.target.value)}
              placeholder="Value"/>
            <button onClick={() => remove(i)}
              className="text-slate-400 hover:text-red-500 transition-colors flex-shrink-0 text-lg leading-none">
              ×
            </button>
          </div>
        ))}
      </div>

      {/* Preset suggestions */}
      {unusedPresets.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {unusedPresets.map(p => (
            <button key={p}
              onClick={() => add(p, '')}
              className="text-xs bg-brand-50 border border-brand-100 text-brand-600 px-2 py-0.5 rounded-full hover:bg-brand-100 transition-colors">
              + {p}
            </button>
          ))}
        </div>
      )}

      {/* Add new field */}
      <div className="flex gap-2 items-center">
        <input className="form-input text-xs" style={{width:'40%'}}
          value={newKey} onChange={e => setNewKey(e.target.value)}
          placeholder="New field name"
          onKeyDown={e => e.key === 'Enter' && add()}/>
        <input className="form-input text-xs flex-1"
          value={newVal} onChange={e => setNewVal(e.target.value)}
          placeholder="Value"
          onKeyDown={e => e.key === 'Enter' && add()}/>
        <button onClick={() => add()}
          disabled={!newKey.trim()}
          className="btn btn-ghost btn-sm flex-shrink-0 disabled:opacity-30">
          Add
        </button>
      </div>

      <p className="text-xs text-slate-400 mt-2">
        Press Enter to add. Field names you use will be suggested next time.
      </p>
    </div>
  )
}

// ── Settings panel for managing presets ───────────────────────────────────

export function CustomFieldPresetsManager() {
  const entities = ['customer', 'product', 'order', 'inventory']
  const [selected, setSelected] = useState('customer')
  const [presets, setPresets]   = useState(() => getPresets(selected))
  const [input, setInput]       = useState('')

  const refresh = (entity) => {
    setSelected(entity)
    setPresets(getPresets(entity))
  }

  const addPreset = () => {
    if (!input.trim()) return
    savePreset(selected, input.trim())
    setPresets(getPresets(selected))
    setInput('')
  }

  const delPreset = (name) => {
    removePreset(selected, name)
    setPresets(getPresets(selected))
  }

  return (
    <div>
      <div className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">
        Custom field presets
      </div>
      <div className="flex gap-2 mb-4">
        {entities.map(e => (
          <button key={e} onClick={() => refresh(e)}
            className={`btn btn-sm capitalize ${e === selected ? 'btn-primary' : 'btn-ghost'}`}>
            {e}
          </button>
        ))}
      </div>
      <div className="space-y-1.5 mb-3">
        {presets.length === 0 && (
          <div className="text-sm text-slate-400">
            No presets yet — they're auto-saved when you add custom fields.
          </div>
        )}
        {presets.map(p => (
          <div key={p} className="flex items-center justify-between px-3 py-1.5 bg-slate-50 rounded-lg">
            <span className="text-sm">{p}</span>
            <button onClick={() => delPreset(p)}
              className="text-slate-400 hover:text-red-500 text-xs">Remove</button>
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <input className="form-input text-sm flex-1" value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && addPreset()}
          placeholder={`Add preset for ${selected}…`}/>
        <button onClick={addPreset} className="btn btn-ghost btn-sm">Add</button>
      </div>
    </div>
  )
}
