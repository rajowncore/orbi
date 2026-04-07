import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './lib/auth'
import Login from './pages/Login'
import SettingsPage from './pages/Settings'
import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import { CustomersPage, CustomerDetailPage } from './pages/Customers'
import { ProductsPage, OrdersPage, InventoryPage, InvoicesPage, UsagePage, PaymentsPage, ProvisioningPage } from './pages/Pages'

function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? children : <Navigate to="/login" replace/>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login/>}/>
      <Route element={<ProtectedRoute><Layout/></ProtectedRoute>}>
        <Route path="/"                  element={<Dashboard/>}/>
        <Route path="/customers"         element={<CustomersPage/>}/>
        <Route path="/customers/:id"     element={<CustomerDetailPage/>}/>
        <Route path="/products"          element={<ProductsPage/>}/>
        <Route path="/orders"            element={<OrdersPage/>}/>
        <Route path="/inventory"         element={<InventoryPage/>}/>
        <Route path="/invoices"          element={<InvoicesPage/>}/>
        <Route path="/usage"             element={<UsagePage/>}/>
        <Route path="/payments"          element={<PaymentsPage/>}/>
        <Route path="/settings"          element={<SettingsPage/>}/>
        <Route path="/provisioning"       element={<ProvisioningPage/>}/>
      </Route>
    </Routes>
  )
}
