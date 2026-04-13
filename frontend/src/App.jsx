import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './lib/auth'
import Login from './pages/Login'
import SettingsPage from './pages/Settings'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import { CustomersPage, CustomerDetailPage } from './pages/Customers'
import {
  ProductsPage, OrdersPage, InventoryPage,
  InvoicesPage, UsagePage, PaymentsPage, ProvisioningPage,
} from './pages/Pages'
import {
  OrderDetailPage, ProductDetailPage, InventoryDetailPage, InvoiceDetailPage,
  UsageDetailPage, PaymentDetailPage, ProvisioningDetailPage,
} from './pages/DetailPages'

function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? children : <Navigate to="/login" replace/>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login/>}/>
      <Route element={<ProtectedRoute><Layout/></ProtectedRoute>}>
        {/* Dashboard */}
        <Route path="/"                       element={<Dashboard/>}/>

        {/* Customers */}
        <Route path="/customers"              element={<CustomersPage/>}/>
        <Route path="/customers/:id"          element={<CustomerDetailPage/>}/>

        {/* Products */}
        <Route path="/products"               element={<ProductsPage/>}/>
        <Route path="/products/:id"           element={<ProductDetailPage/>}/>

        {/* Orders */}
        <Route path="/orders"                 element={<OrdersPage/>}/>
		<Route path="/orders/:id"             element={<OrderDetailPage/>}/>																	

        {/* Inventory */}
        <Route path="/inventory"              element={<InventoryPage/>}/>
        <Route path="/inventory/:id"          element={<InventoryDetailPage/>}/>

        {/* Invoices */}
        <Route path="/invoices"               element={<InvoicesPage/>}/>
        <Route path="/invoices/:id"           element={<InvoiceDetailPage/>}/>

        {/* Usage events */}
        <Route path="/usage"                  element={<UsagePage/>}/>
        <Route path="/usage/:id"              element={<UsageDetailPage/>}/>

        {/* Payments */}
        <Route path="/payments"               element={<PaymentsPage/>}/>
        <Route path="/payments/:id"           element={<PaymentDetailPage/>}/>

        {/* Provisioning */}
        <Route path="/provisioning"           element={<ProvisioningPage/>}/>
        <Route path="/provisioning/:id"       element={<ProvisioningDetailPage/>}/>

        {/* Settings */}
        <Route path="/settings"               element={<SettingsPage/>}/>
      </Route>
    </Routes>
  )
}
