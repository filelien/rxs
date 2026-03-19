import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: BASE,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// Inject JWT on every request
api.interceptors.request.use((cfg) => {
  const token = localStorage.getItem('raxus_access_token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

// Auto-refresh token on 401
api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const orig = err.config
    if (err.response?.status === 401 && !orig._retry) {
      orig._retry = true
      const refresh = localStorage.getItem('raxus_refresh_token')
      if (refresh) {
        try {
          const { data } = await axios.post(`${BASE}/auth/refresh`, { refresh_token: refresh })
          localStorage.setItem('raxus_access_token', data.access_token)
          localStorage.setItem('raxus_refresh_token', data.refresh_token)
          orig.headers.Authorization = `Bearer ${data.access_token}`
          return api(orig)
        } catch {
          localStorage.clear()
          window.location.href = '/login'
        }
      } else {
        localStorage.clear()
        window.location.href = '/login'
      }
    }
    return Promise.reject(err)
  }
)

// ── Auth ──────────────────────────────────────────────────────
export const authApi = {
  login:          (username: string, password: string) => api.post('/auth/login', { username, password }).then(r => r.data),
  refresh:        (refresh_token: string) => api.post('/auth/refresh', { refresh_token }).then(r => r.data),
  logout:         () => api.post('/auth/logout'),
  me:             () => api.get('/auth/me').then(r => r.data),
  changePassword: (old_password: string, new_password: string) => api.post('/auth/change-password', { old_password, new_password }).then(r => r.data),
}

// ── Connections ───────────────────────────────────────────────
export const connectionsApi = {
  list:           () => api.get('/connections/').then(r => r.data),
  create:         (payload: any) => api.post('/connections/', payload).then(r => r.data),
  update:         (id: string, data: any) => api.patch(`/connections/${id}`, data).then(r => r.data),
  delete:         (id: string) => api.delete(`/connections/${id}`).then(r => r.data),
  test:           (id: string) => api.post(`/connections/${id}/test`).then(r => r.data),
  schema:         (id: string, database?: string) => api.get(`/connections/${id}/schema`, { params: { database } }).then(r => r.data),
  databases:      (id: string) => api.get(`/connections/${id}/databases`).then(r => r.data),
  tableDetail:    (id: string, table: string, schema?: string) => api.get(`/connections/${id}/tables/${table}`, { params: { schema } }).then(r => r.data),
}

// ── Query ─────────────────────────────────────────────────────
export const queryApi = {
  execute:        (sql: string, connector_id: string, params?: any, timeout?: number) =>
                    api.post('/query/execute', { sql, connector_id, params, timeout }).then(r => r.data),
  validate:       (sql: string, connector_id: string) =>
                    api.post('/query/validate', { sql, connector_id }).then(r => r.data),
  explain:        (sql: string, connector_id: string) =>
                    api.post('/query/explain', { sql, connector_id }).then(r => r.data),
  history:        (connector_id?: string, page = 1, limit = 50) =>
                    api.get('/query/history', { params: { connector_id, page, limit } }).then(r => r.data),
  slow:           (threshold_ms = 1000, limit = 20) =>
                    api.get('/query/slow', { params: { threshold_ms, limit } }).then(r => r.data),
  save:           (name: string, sql: string, connector_id: string, tags: string[] = [], description = '') =>
                    api.post('/query/save', { name, sql, connector_id, tags, description }).then(r => r.data),
  saved:          (connector_id?: string) =>
                    api.get('/query/saved', { params: { connector_id } }).then(r => r.data),
  deleteSaved:    (id: string) => api.delete(`/query/saved/${id}`).then(r => r.data),
  schema:         (connector_id: string, database?: string) =>
                    api.get(`/query/schema/${connector_id}`, { params: { database } }).then(r => r.data),
  tableDetail:    (connector_id: string, table: string, schema?: string) =>
                    api.get(`/query/schema/${connector_id}/table/${table}`, { params: { schema } }).then(r => r.data),
  oraclePerf:     (connector_id: string) =>
                    api.get(`/query/oracle/${connector_id}/performance`).then(r => r.data),
  // Transactions
  txBegin:        (connector_id: string) =>
                    api.post('/query/transaction/begin', null, { params: { connector_id } }).then(r => r.data),
  txExecute:      (session_id: string, sql: string, connector_id: string) =>
                    api.post(`/query/transaction/${session_id}/execute`, { sql, connector_id }).then(r => r.data),
  txCommit:       (session_id: string) =>
                    api.post(`/query/transaction/${session_id}/commit`).then(r => r.data),
  txRollback:     (session_id: string) =>
                    api.post(`/query/transaction/${session_id}/rollback`).then(r => r.data),
}

// ── Monitoring ────────────────────────────────────────────────
export const monitoringApi = {
  dashboard:      () => api.get('/monitoring/dashboard').then(r => r.data),
  connectors:     () => api.get('/monitoring/connectors').then(r => r.data),
  alerts:         () => api.get('/monitoring/alerts').then(r => r.data),
  alertRules:     () => api.get('/monitoring/rules').then(r => r.data),
  createRule:     (rule: any) => api.post('/monitoring/rules', rule).then(r => r.data),
  ackAlert:       (id: number) => api.patch(`/monitoring/alerts/${id}/acknowledge`).then(r => r.data),
  resolveAlert:   (id: number) => api.patch(`/monitoring/alerts/${id}/resolve`).then(r => r.data),
  history:        (connector_id: string, metric: string, window = 60) =>
                    api.get(`/monitoring/metrics/${connector_id}/history`, { params: { metric, window } }).then(r => r.data),
}

// ── Audit ─────────────────────────────────────────────────────
export const auditApi = {
  logs:           (params?: any) => api.get('/audit/logs', { params }).then(r => r.data),
  sessions:       (connector_id: string) => api.get(`/audit/sessions/${connector_id}`).then(r => r.data),
  privileges:     (connector_id: string) => api.get(`/audit/privileges/${connector_id}`).then(r => r.data),
  locks:          (connector_id: string) => api.get(`/audit/locks/${connector_id}`).then(r => r.data),
  report:         (days = 7, format = 'json') => api.get('/audit/report', { params: { days, format } }).then(r => r.data),
  fewShots:       (db_type?: string) => api.get('/audit/few-shots', { params: { db_type } }).then(r => r.data),
  addFewShot:     (data: any) => api.post('/audit/few-shots', data).then(r => r.data),
  deleteFewShot:  (id: string) => api.delete(`/audit/few-shots/${id}`).then(r => r.data),
}

// ── Tasks ─────────────────────────────────────────────────────
export const tasksApi = {
  list:           (status?: string) => api.get('/tasks/', { params: { status } }).then(r => r.data),
  create:         (task: any) => api.post('/tasks/', task).then(r => r.data),
  get:            (id: string) => api.get(`/tasks/${id}`).then(r => r.data),
  cancel:         (id: string) => api.delete(`/tasks/${id}`).then(r => r.data),
  schedules:      () => api.get('/tasks/schedules/list').then(r => r.data),
  createSchedule: (s: any) => api.post('/tasks/schedules/', s).then(r => r.data),
  pauseSchedule:  (id: string) => api.post(`/tasks/schedules/${id}/pause`).then(r => r.data),
  resumeSchedule: (id: string) => api.post(`/tasks/schedules/${id}/resume`).then(r => r.data),
  triggerSchedule:(id: string) => api.post(`/tasks/schedules/${id}/trigger`).then(r => r.data),
}

// ── Chat ──────────────────────────────────────────────────────
export const chatApi = {
  newSession:     (connector_id?: string) =>
                    api.post('/chat/session/new', null, { params: { connector_id } }).then(r => r.data),
  sessions:       () => api.get('/chat/sessions').then(r => r.data),
  messages:       (session_id: string) => api.get(`/chat/sessions/${session_id}/messages`).then(r => r.data),
  send:           (session_id: string, message: string, connector_id?: string) =>
                    api.post('/chat/message', { session_id, message, connector_id }).then(r => r.data),
  clearSession:   (session_id: string) => api.delete(`/chat/session/${session_id}`).then(r => r.data),
  approveSql:     (data: any) => api.post('/chat/approve-sql', data).then(r => r.data),
}

// ── Agents ────────────────────────────────────────────────────
export const agentsApi = {
  list:           () => api.get('/agents/').then(r => r.data),
  register:       (data: any) => api.post('/agents/register', data).then(r => r.data),
  delete:         (server_id: string) => api.delete(`/agents/${server_id}`).then(r => r.data),
  sendCommand:    (server_id: string, command: string) =>
                    api.post(`/agents/${server_id}/send-command`, null, { params: { command } }).then(r => r.data),
  metricHistory:  (server_id: string, metric: string, window = 60) =>
                    api.get(`/agents/${server_id}/metrics/history`, { params: { metric, window } }).then(r => r.data),
}

// ── Users ─────────────────────────────────────────────────────
export const usersApi = {
  list:           () => api.get('/users/').then(r => r.data),
  me:             () => api.get('/users/me').then(r => r.data),
  get:            (id: string) => api.get(`/users/${id}`).then(r => r.data),
  create:         (u: any) => api.post('/users/', u).then(r => r.data),
  update:         (id: string, u: any) => api.patch(`/users/${id}`, u).then(r => r.data),
  delete:         (id: string) => api.delete(`/users/${id}`).then(r => r.data),
}

// ── Health ────────────────────────────────────────────────────
export const healthApi = {
  check: () => api.get('/health').then(r => r.data),
}
