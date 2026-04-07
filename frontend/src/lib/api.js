import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.response.use(
  r => r.data,
  e => Promise.reject(e?.response?.data?.detail || e?.message || 'Request failed')
)

// ── Customers ─────────────────────────────────────────────────────────────
export const customers = {
  list:   ()       => api.get('/customers'),
  get:    (id)     => api.get(`/customers/${id}`),
  create: (data)   => api.post('/customers', data),
  update: (id, d)  => api.patch(`/customers/${id}`, d),
  orders:   (id)   => api.get(`/customers/${id}/orders`),
  invoices: (id)   => api.get(`/customers/${id}/invoices`),
  balance:  (id)   => api.get(`/customers/${id}/balance`),
}

// ── Products ──────────────────────────────────────────────────────────────
export const products = {
  list:   ()       => api.get('/products'),
  get:    (id)     => api.get(`/products/${id}`),
  create: (data)   => api.post('/products', data),
  update: (id, d)  => api.patch(`/products/${id}`, d),
}

// ── Inventory ─────────────────────────────────────────────────────────────
export const inventory = {
  list:      ()     => api.get('/inventory'),
  available: (type) => api.get(`/inventory/available${type ? `?type=${type}` : ''}`),
  create:    (d)    => api.post('/inventory', d),
  bulk:      (d)    => api.post('/inventory/bulk', d),
  update:    (id,d) => api.patch(`/inventory/${id}`, d),
}

// ── Orders ────────────────────────────────────────────────────────────────
export const orders = {
  list:   ()            => api.get('/orders'),
  get:    (id)          => api.get(`/orders/${id}`),
  create: (data)        => api.post('/orders', data),
  action: (id, action)  => api.patch(`/orders/${id}`, { action }),
}

// ── Subscriptions ─────────────────────────────────────────────────────────
export const subscriptions = {
  list: (customerId, subType) => {
    const params = new URLSearchParams();
    if (customerId) params.append('customer_id', customerId);
    if (subType) params.append('sub_type', subType);
    
    return api.get(`/subscriptions?${params.toString()}`);
  },
}

// ── Usage ─────────────────────────────────────────────────────────────────
export const usage = {
  ingest:   (data)   => api.post('/usage/events', data),
  batch:    (events) => api.post('/usage/events/batch', { events }),
  list:     (params) => api.get('/usage/events', { params }),
  rejected: ()       => api.get('/usage/rejected'),
  replay:   (id)     => api.post(`/usage/rejected/${id}/replay`),
  upload:   (file)   => {
    const fd = new FormData(); fd.append('file', file)
    return api.post('/usage/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
}

// ── Invoices ──────────────────────────────────────────────────────────────
export const invoices = {
  list:     (customerId) => api.get('/invoices' + (customerId ? `?customer_id=${customerId}` : '')),
  get:       (id)     => api.get(`/invoices/${id}`),
  finalise:  (id)     => api.post(`/invoices/${id}/finalise`),
  pdfUrl:   (id)         => `/api/v1/invoices/${id}/pdf`,
}

// ── Payments ──────────────────────────────────────────────────────────────
export const payments = {
  list:   (customerId) => api.get(`/payments${customerId ? `?customer_id=${customerId}` : ''}`),
  create: (data)       => api.post('/payments', data),
}

// ── Billing runs ──────────────────────────────────────────────────────────
export const billingRuns = {
  trigger: (data) => api.post('/billing-runs', data),
  get:     (id)   => api.get(`/billing-runs/${id}`),
}
export const provisioning = {
  getWorkflow:   (orderId) => api.get(`/provisioning/workflows/${orderId}`),
  listWorkflows: (status)  => api.get('/provisioning/workflows' + (status ? `?status=${status}` : '')),
  provision:     (orderId) => api.post(`/provisioning/provision/${orderId}`),
  deprovision:   (orderId) => api.post(`/provisioning/deprovision/${orderId}`),
}
