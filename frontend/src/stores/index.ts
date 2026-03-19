import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// ── Auth Store ───────────────────────────────────────────────
interface User {
  user_id: string
  username: string
  role: 'admin' | 'dba' | 'analyst' | 'viewer'
}

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  setAuth: (user: User, access: string, refresh: string) => void
  logout: () => void
  isAuthenticated: () => boolean
  can: (role: string) => boolean
}

const ROLE_LEVELS: Record<string, number> = { admin: 4, dba: 3, analyst: 2, viewer: 1 }

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      setAuth: (user, accessToken, refreshToken) => {
        localStorage.setItem('raxus_access_token', accessToken)
        localStorage.setItem('raxus_refresh_token', refreshToken)
        set({ user, accessToken, refreshToken })
      },
      logout: () => {
        localStorage.removeItem('raxus_access_token')
        localStorage.removeItem('raxus_refresh_token')
        set({ user: null, accessToken: null, refreshToken: null })
      },
      isAuthenticated: () => !!get().accessToken && !!get().user,
      can: (minRole: string) => {
        const userRole = get().user?.role || 'viewer'
        return (ROLE_LEVELS[userRole] || 0) >= (ROLE_LEVELS[minRole] || 0)
      },
    }),
    { name: 'raxus-auth', partialize: (s) => ({ user: s.user, accessToken: s.accessToken, refreshToken: s.refreshToken }) }
  )
)

// ── Connections Store ─────────────────────────────────────────
interface Connection {
  id: string
  name: string
  db_type: string
  host: string
  database_name: string
  enabled: boolean
  last_test_ok: boolean | null
  last_test_ms: number | null
}

interface ConnectionsState {
  connections: Connection[]
  activeConnectionId: string | null
  loading: boolean
  setConnections: (conns: Connection[]) => void
  setActive: (id: string | null) => void
  addConnection: (conn: Connection) => void
  removeConnection: (id: string) => void
  updateTest: (id: string, ok: boolean, ms: number) => void
  getActive: () => Connection | null
}

export const useConnectionsStore = create<ConnectionsState>()(
  persist(
    (set, get) => ({
      connections: [],
      activeConnectionId: null,
      loading: false,
      setConnections: (connections) => set({ connections }),
      setActive: (id) => set({ activeConnectionId: id }),
      addConnection: (conn) => set((s) => ({ connections: [...s.connections, conn] })),
      removeConnection: (id) => set((s) => ({
        connections: s.connections.filter((c) => c.id !== id),
        activeConnectionId: s.activeConnectionId === id ? null : s.activeConnectionId,
      })),
      updateTest: (id, ok, ms) => set((s) => ({
        connections: s.connections.map((c) => c.id === id ? { ...c, last_test_ok: ok, last_test_ms: ms } : c),
      })),
      getActive: () => {
        const { connections, activeConnectionId } = get()
        return connections.find((c) => c.id === activeConnectionId) || null
      },
    }),
    { name: 'raxus-connections', partialize: (s) => ({ activeConnectionId: s.activeConnectionId }) }
  )
)

// ── App/UI Store ──────────────────────────────────────────────
interface Notification {
  id: string
  type: 'info' | 'success' | 'warning' | 'error'
  title: string
  message: string
  read: boolean
  at: string
}

interface AppState {
  sidebarOpen: boolean
  notifications: Notification[]
  setSidebar: (open: boolean) => void
  addNotification: (n: Omit<Notification, 'id' | 'read' | 'at'>) => void
  markRead: (id: string) => void
  clearAll: () => void
  unreadCount: () => number
}

export const useAppStore = create<AppState>((set, get) => ({
  sidebarOpen: true,
  notifications: [],
  setSidebar: (open) => set({ sidebarOpen: open }),
  addNotification: (n) => set((s) => ({
    notifications: [
      { ...n, id: Math.random().toString(36).slice(2), read: false, at: new Date().toISOString() },
      ...s.notifications.slice(0, 49),
    ],
  })),
  markRead: (id) => set((s) => ({
    notifications: s.notifications.map((n) => n.id === id ? { ...n, read: true } : n),
  })),
  clearAll: () => set({ notifications: [] }),
  unreadCount: () => get().notifications.filter((n) => !n.read).length,
}))

// ── Query Editor Store ────────────────────────────────────────
interface Tab {
  id: string
  title: string
  sql: string
  connector_id: string
  result: any | null
  status: 'idle' | 'running' | 'success' | 'error'
  duration_ms: number
  error: string | null
}

interface EditorState {
  tabs: Tab[]
  activeTabId: string | null
  addTab: (connector_id?: string) => string
  closeTab: (id: string) => void
  updateTab: (id: string, patch: Partial<Tab>) => void
  setActiveTab: (id: string) => void
  getActiveTab: () => Tab | null
}

export const useEditorStore = create<EditorState>((set, get) => ({
  tabs: [],
  activeTabId: null,
  addTab: (connector_id = '') => {
    const id = Math.random().toString(36).slice(2)
    const tab: Tab = { id, title: 'Nouvelle requête', sql: '', connector_id, result: null, status: 'idle', duration_ms: 0, error: null }
    set((s) => ({ tabs: [...s.tabs, tab], activeTabId: id }))
    return id
  },
  closeTab: (id) => set((s) => {
    const tabs = s.tabs.filter((t) => t.id !== id)
    const activeTabId = s.activeTabId === id ? (tabs[tabs.length - 1]?.id || null) : s.activeTabId
    return { tabs, activeTabId }
  }),
  updateTab: (id, patch) => set((s) => ({ tabs: s.tabs.map((t) => t.id === id ? { ...t, ...patch } : t) })),
  setActiveTab: (id) => set({ activeTabId: id }),
  getActiveTab: () => {
    const { tabs, activeTabId } = get()
    return tabs.find((t) => t.id === activeTabId) || null
  },
}))
