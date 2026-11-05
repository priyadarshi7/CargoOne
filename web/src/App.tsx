import { lazy, Suspense, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { OfficeShell } from './components/Shell'
import type { Role } from './lib/api'
import { AuthProvider, homeFor, useAuth } from './lib/auth'
import { LangProvider } from './lib/i18n'
import { ThemeProvider } from './lib/theme'
import Capture from './pages/Capture'
import Landing from './pages/Landing'
import DriverExpense from './pages/DriverExpense'
import DriverPin from './pages/DriverPin'
import DriverHelp from './pages/DriverHelp'
import DriverMessages from './pages/DriverMessages'
import DriverHome from './pages/DriverHome'
import Onboard from './pages/Onboard'
import RequestStatus from './pages/RequestStatus'
import RequestTransport from './pages/RequestTransport'
import Login from './pages/Login'
import ClientPod from './pages/ClientPod'
import SmsCapture from './pages/SmsCapture'
import Progress from './pages/Progress'

// Office screens are loaded only when an office person opens them: a driver's phone never downloads charts, tables or the map.
const Billing = lazy(() => import('./pages/Billing'))
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Expenses = lazy(() => import('./pages/Expenses'))
const Setup = lazy(() => import('./pages/Setup'))
const ImportTrips = lazy(() => import('./pages/ImportTrips'))
const Requests = lazy(() => import('./pages/Requests'))
const OfficeTrips = lazy(() => import('./pages/OfficeTrips'))
const Planning = lazy(() => import('./pages/Planning'))
const ReviewDetail = lazy(() => import('./pages/ReviewDetail'))
const ReviewList = lazy(() => import('./pages/ReviewList'))
const Account = lazy(() => import('./pages/Account'))
const Desk = lazy(() => import('./pages/Desk'))
// The map library is heavy: load it only when a map page is opened
const LiveMapPage = lazy(() => import('./pages/LiveMapPage'))
const TrackPublic = lazy(() => import('./pages/TrackPublic'))

function Guard({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth()
  const { pathname } = useLocation()
  if (loading) return null
  if (!user) return <Navigate to="/login" replace />
  if (user.must_change_secret && user.role === 'driver' && pathname !== '/driver/pin') return <Navigate to="/driver/pin" replace />
  if (user.must_change_secret && user.role !== 'driver' && pathname !== '/office/account') return <Navigate to="/office/account" replace /> // new office accounts start with a temporary password
  if (!roles.includes(user.role) && user.role !== 'admin') return <Navigate to={homeFor(user.role)} replace />
  return <>{children}</>
}

/** Each office role gets its own home: ops (and admin) the operations desk, billing the billing desk, the MD the performance dashboard. */
function OfficeHome() {
  const { user } = useAuth()
  return <OfficeShell>{user?.role === 'md' ? <Dashboard /> : <Desk billing={user?.role === 'billing'} />}</OfficeShell>
}

function Root() {
  const { user, loading } = useAuth()
  if (loading) return null
  return user ? <Navigate to={homeFor(user.role)} replace /> : <Landing />
}

export default function App() {
  return (
    <ThemeProvider>
    <LangProvider>
    <AuthProvider>
      <BrowserRouter>
        <Suspense fallback={null}>
        <Routes>
          <Route path="/" element={<Root />} />
          <Route path="/login" element={<Login />} />
          <Route path="/progress" element={<Progress />} />
          <Route path="/onboard/:token" element={<Onboard />} />
          <Route path="/request" element={<RequestTransport />} />
          <Route path="/request/:token" element={<RequestStatus />} />
          <Route path="/u/:token" element={<SmsCapture />} />
          <Route path="/v/:token" element={<ClientPod />} />
          <Route path="/t/:token" element={<TrackPublic />} />
          <Route path="/driver" element={<Guard roles={['driver']}><DriverHome /></Guard>} />
          <Route path="/driver/messages" element={<Guard roles={['driver']}><DriverMessages /></Guard>} />
          <Route path="/driver/help" element={<Guard roles={['driver']}><DriverHelp /></Guard>} />
          <Route path="/driver/expense" element={<Guard roles={['driver']}><DriverExpense /></Guard>} />
          <Route path="/driver/pin" element={<Guard roles={['driver']}><DriverPin /></Guard>} />
          <Route path="/driver/trip/:id" element={<Guard roles={['driver']}><Capture /></Guard>} />
          <Route path="/office" element={<Guard roles={['ops', 'billing', 'md']}><OfficeHome /></Guard>} />
          <Route path="/office/performance" element={<Guard roles={['ops', 'md']}><OfficeShell><Dashboard /></OfficeShell></Guard>} />
          <Route path="/office/trips" element={<Guard roles={['ops', 'billing', 'md']}><OfficeShell><OfficeTrips /></OfficeShell></Guard>} />
          <Route path="/office/account" element={<Guard roles={['ops', 'billing', 'md']}><OfficeShell><Account /></OfficeShell></Guard>} />
          <Route path="/office/setup" element={<Guard roles={['ops', 'billing']}><OfficeShell><Setup /></OfficeShell></Guard>} />
          <Route path="/office/drivers" element={<Navigate to="/office/setup?tab=drivers" replace />} />
          <Route path="/office/expenses" element={<Guard roles={['ops', 'billing', 'md']}><OfficeShell><Expenses /></OfficeShell></Guard>} />
          <Route path="/office/live" element={<Guard roles={['ops', 'md']}><OfficeShell><LiveMapPage /></OfficeShell></Guard>} />
          <Route path="/office/requests" element={<Guard roles={['ops', 'billing']}><OfficeShell><Requests /></OfficeShell></Guard>} />
          <Route path="/office/planning" element={<Guard roles={['ops', 'billing']}><OfficeShell><Planning /></OfficeShell></Guard>} />
          <Route path="/office/import" element={<Guard roles={['ops', 'billing']}><OfficeShell><ImportTrips /></OfficeShell></Guard>} />
          <Route path="/office/billing" element={<Guard roles={['ops', 'billing']}><OfficeShell><Billing /></OfficeShell></Guard>} />
          <Route path="/office/review" element={<Guard roles={['ops', 'billing']}><OfficeShell><ReviewList /></OfficeShell></Guard>} />
          <Route path="/office/review/:tripId" element={<Guard roles={['ops', 'billing']}><OfficeShell><ReviewDetail /></OfficeShell></Guard>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
      </BrowserRouter>
    </AuthProvider>
    </LangProvider>
    </ThemeProvider>
  )
}
