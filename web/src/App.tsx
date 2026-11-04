import type { ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { OfficeShell } from './components/Shell'
import type { Role } from './lib/api'
import { AuthProvider, homeFor, useAuth } from './lib/auth'
import { LangProvider } from './lib/i18n'
import Billing from './pages/Billing'
import Capture from './pages/Capture'
import Dashboard from './pages/Dashboard'
import DriverHome from './pages/DriverHome'
import ImportTrips from './pages/ImportTrips'
import Login from './pages/Login'
import OfficeTrips from './pages/OfficeTrips'
import ReviewDetail from './pages/ReviewDetail'
import ReviewList from './pages/ReviewList'
import Account from './pages/Account'
import ClientPod from './pages/ClientPod'
import SmsCapture from './pages/SmsCapture'
import Progress from './pages/Progress'

function Guard({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return null
  if (!user) return <Navigate to="/login" replace />
  if (!roles.includes(user.role) && user.role !== 'admin') return <Navigate to={homeFor(user.role)} replace />
  return <>{children}</>
}

/** Role-based landing: ops head and MD see the dashboard; billing executives go straight to their work queue. */
function OfficeHome() {
  const { user } = useAuth()
  if (user?.role === 'billing') return <Navigate to="/office/review" replace />
  return <OfficeShell><Dashboard /></OfficeShell>
}

function Root() {
  const { user, loading } = useAuth()
  if (loading) return null
  return <Navigate to={user ? homeFor(user.role) : '/login'} replace />
}

export default function App() {
  return (
    <LangProvider>
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Root />} />
          <Route path="/login" element={<Login />} />
          <Route path="/progress" element={<Progress />} />
          <Route path="/u/:token" element={<SmsCapture />} />
          <Route path="/v/:token" element={<ClientPod />} />
          <Route path="/driver" element={<Guard roles={['driver']}><DriverHome /></Guard>} />
          <Route path="/driver/trip/:id" element={<Guard roles={['driver']}><Capture /></Guard>} />
          <Route path="/office" element={<Guard roles={['ops', 'billing', 'md']}><OfficeHome /></Guard>} />
          <Route path="/office/trips" element={<Guard roles={['ops', 'billing', 'md']}><OfficeShell><OfficeTrips /></OfficeShell></Guard>} />
          <Route path="/office/account" element={<Guard roles={['ops', 'billing', 'md']}><OfficeShell><Account /></OfficeShell></Guard>} />
          <Route path="/office/import" element={<Guard roles={['ops', 'billing']}><OfficeShell><ImportTrips /></OfficeShell></Guard>} />
          <Route path="/office/billing" element={<Guard roles={['ops', 'billing']}><OfficeShell><Billing /></OfficeShell></Guard>} />
          <Route path="/office/review" element={<Guard roles={['ops', 'billing']}><OfficeShell><ReviewList /></OfficeShell></Guard>} />
          <Route path="/office/review/:tripId" element={<Guard roles={['ops', 'billing']}><OfficeShell><ReviewDetail /></OfficeShell></Guard>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
    </LangProvider>
  )
}
