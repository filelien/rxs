import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { useAuthStore } from './stores'
import Layout from './components/layout/Layout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import ConnectionsPage from './pages/ConnectionsPage'
import QueryEditorPage from './pages/QueryEditorPage'
import SchemaBrowserPage from './pages/SchemaBrowserPage'
import MonitoringPage from './pages/MonitoringPage'
import AuditPage from './pages/AuditPage'
import TasksPage from './pages/TasksPage'
import ChatPage from './pages/ChatPage'
import UsersPage from './pages/UsersPage'
import ServersPage from './pages/ServersPage'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated())
  return isAuthenticated ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <BrowserRouter>
      <Toaster position="top-right" toastOptions={{
        style: { background:'#0d1425', color:'#e2e8f0', border:'1px solid #1a2640', fontFamily:'DM Sans,sans-serif', fontSize:'13px' },
        success: { iconTheme: { primary:'#22c55e', secondary:'#0d1425' } },
        error: { iconTheme: { primary:'#ef4444', secondary:'#0d1425' } },
      }}/>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<PrivateRoute><Layout /></PrivateRoute>}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="connections" element={<ConnectionsPage />} />
          <Route path="editor" element={<QueryEditorPage />} />
          <Route path="schema" element={<SchemaBrowserPage />} />
          <Route path="monitoring" element={<MonitoringPage />} />
          <Route path="audit" element={<AuditPage />} />
          <Route path="tasks" element={<TasksPage />} />
          <Route path="chat" element={<ChatPage />} />
          <Route path="users" element={<UsersPage />} />
          <Route path="servers" element={<ServersPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
