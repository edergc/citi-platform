import { Navigate, Route, Routes } from 'react-router-dom'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { RequirePermission } from '@/components/RequirePermission'
import { Layout } from '@/components/Layout'
import { LoginPage } from '@/pages/LoginPage'
import { ForgotPasswordPage } from '@/pages/ForgotPasswordPage'
import { ResetPasswordPage } from '@/pages/ResetPasswordPage'
import { PublicStatusPage } from '@/pages/PublicStatusPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { ServersPage } from '@/pages/ServersPage'
import { ServerDetailPage } from '@/pages/ServerDetailPage'
import { NetworkOverviewPage } from '@/pages/NetworkOverviewPage'
import { ConnectivityPage } from '@/pages/ConnectivityPage'
import { ConnectivityServerDetailPage } from '@/pages/ConnectivityServerDetailPage'
import { AlertsPage } from '@/pages/AlertsPage'
import { ProblemsPage } from '@/pages/ProblemsPage'
import { MaintenancePage } from '@/pages/MaintenancePage'
import { SyntheticChecksPage } from '@/pages/SyntheticChecksPage'
import { FleetDashboardsPage } from '@/pages/FleetDashboardsPage'
import { SystemDetailPage } from '@/pages/SystemDetailPage'
import { WeeklyReportPage } from '@/pages/WeeklyReportPage'
import { NotificationsPage } from '@/pages/NotificationsPage'
import { AdminPage } from '@/pages/AdminPage'
import { ProfilePage } from '@/pages/ProfilePage'

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/estado" element={<PublicStatusPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route element={<RequirePermission code="systems.manage" />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/systems/:id" element={<SystemDetailPage />} />
          </Route>
          <Route path="/servers" element={<ServersPage />} />
          <Route path="/servers/:id" element={<ServerDetailPage />} />
          <Route path="/connectivity" element={<ConnectivityPage />} />
          <Route path="/connectivity/:id" element={<ConnectivityServerDetailPage />} />
          <Route path="/network" element={<NetworkOverviewPage />} />
          <Route path="/problemas" element={<ProblemsPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/mantenimiento" element={<MaintenancePage />} />
          <Route path="/sinteticos" element={<SyntheticChecksPage />} />
          <Route path="/dashboards" element={<FleetDashboardsPage />} />
          <Route path="/reports/weekly" element={<WeeklyReportPage />} />
          <Route element={<RequirePermission code="notifications.manage" />}>
            <Route path="/notifications" element={<NotificationsPage />} />
          </Route>
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/profile" element={<ProfilePage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
