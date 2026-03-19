import { useEffect, useState } from 'react'
import { auditApi } from '../lib/api'
import { useConnectionsStore } from '../stores'
import { Shield, Search, AlertTriangle } from 'lucide-react'
import toast from 'react-hot-toast'

export default function AuditPage() {
  const { connections } = useConnectionsStore()
  const [logs, setLogs] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [riskMin, setRiskMin] = useState(0)
  const [days, setDays] = useState(7)
  const [sessions, setSessions] = useState<any[]>([])
  const [privileges, setPrivileges] = useState<any[]>([])
  const [activeTab, setActiveTab] = useState<'logs' | 'sessions' | 'privileges'>('logs')
  const [selectedConn, setSelectedConn] = useState('')
  const [loading, setLoading] = useState(false)

  const loadLogs = async () => {
    setLoading(true)
    try {
      const res = await auditApi.logs({ action: search, risk_min: riskMin, days, page, limit: 50 })
      setLogs(res.data || [])
      setTotal(res.total || 0)
    } catch { toast.error('Erreur chargement audit') }
    finally { setLoading(false) }
  }

  const loadSessions = async () => {
    if (!selectedConn) return
    const data = await auditApi.sessions(selectedConn)
    setSessions(Array.isArray(data) ? data : [])
  }

  const loadPrivileges = async () => {
    if (!selectedConn) return
    const data = await auditApi.privileges(selectedConn)
    setPrivileges(data?.flagged || [])
  }

  useEffect(() => { loadLogs() }, [page, days, riskMin, search])
  useEffect(() => { if (selectedConn) { loadSessions(); loadPrivileges() } }, [selectedConn])

  const riskColor = (score: number) => {
    if (score >= 70) return 'var(--danger)'
    if (score >= 40) return 'var(--warning)'
    return 'var(--text-muted)'
  }

  const resultColor = (r: string) => r === 'success' ? 'var(--success)' : r === 'blocked' ? 'var(--danger)' : 'var(--warning)'

  return (
    <div className="fade-in">
      <div className="page-header"><h1 className="page-title font-display">Audit & Sécurité</h1><p className="page-sub">Traçabilité complète — logs immuables, sessions, privilèges</p></div>

      {/* Tabs */}
      <div className="tabs" style={{ marginBottom: 20 }}>
        {(['logs', 'sessions', 'privileges'] as const).map(t => (
          <button key={t} className={`tab ${activeTab === t ? 'active' : ''}`} onClick={() => setActiveTab(t)}>
            {t === 'logs' ? '📋 Logs d\'audit' : t === 'sessions' ? '👥 Sessions actives' : '🔐 Privilèges Oracle'}
          </button>
        ))}
      </div>

      {activeTab === 'logs' && (
        <>
          <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
            <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
              <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-dim)' }} />
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Filtrer par action…" style={{ paddingLeft: 30 }} />
            </div>
            <select value={days} onChange={e => setDays(+e.target.value)} style={{ width: 'auto', padding: '8px 12px' }}>
              <option value={1}>Aujourd'hui</option><option value={7}>7 jours</option><option value={30}>30 jours</option>
            </select>
            <select value={riskMin} onChange={e => setRiskMin(+e.target.value)} style={{ width: 'auto', padding: '8px 12px' }}>
              <option value={0}>Tous risques</option><option value={40}>Risque moyen+</option><option value={70}>Risque élevé</option>
            </select>
          </div>
          <div className="card">
            <table className="table-raxus">
              <thead><tr><th>Utilisateur</th><th>Action</th><th>Resource</th><th>IP</th><th>Résultat</th><th>Risque</th><th>Date</th></tr></thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={7} style={{ textAlign: 'center', padding: 24 }}><span className="spinner" style={{ margin: 'auto' }} /></td></tr>
                ) : logs.length === 0 ? (
                  <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--text-dim)', padding: 24 }}>Aucun log trouvé</td></tr>
                ) : logs.map((log: any, i) => (
                  <tr key={i}>
                    <td className="primary">{log.username || log.user_id?.slice(0, 8)}</td>
                    <td className="font-mono" style={{ fontSize: 11 }}>{log.action}</td>
                    <td style={{ fontSize: 11 }}>{log.resource_type} {log.resource_id?.slice(0, 8)}</td>
                    <td className="font-mono" style={{ fontSize: 11 }}>{log.request_ip || '—'}</td>
                    <td><span style={{ fontSize: 12, color: resultColor(log.result), fontWeight: 500 }}>{log.result}</span></td>
                    <td><span style={{ fontFamily: 'DM Mono', fontSize: 12, color: riskColor(log.risk_score), fontWeight: 500 }}>{log.risk_score}</span></td>
                    <td style={{ fontSize: 11 }}>{log.created_at ? new Date(log.created_at).toLocaleString('fr') : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {total > 50 && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 12 }}>
              <button className="btn btn-ghost btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>← Préc.</button>
              <span style={{ fontSize: 12, color: 'var(--text-muted)', padding: '5px 10px' }}>Page {page} · {total} entrées</span>
              <button className="btn btn-ghost btn-sm" disabled={page * 50 >= total} onClick={() => setPage(p => p + 1)}>Suiv. →</button>
            </div>
          )}
        </>
      )}

      {activeTab === 'sessions' && (
        <div>
          <div style={{ marginBottom: 14 }}>
            <select value={selectedConn} onChange={e => setSelectedConn(e.target.value)} style={{ width: 'auto', padding: '8px 12px' }}>
              <option value="">— Choisir une connexion Oracle —</option>
              {connections.filter(c => c.db_type === 'oracle').map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div className="card">
            <table className="table-raxus">
              <thead><tr><th>SID</th><th>Username</th><th>Status</th><th>Wait Event</th><th>Machine</th><th>SQL</th></tr></thead>
              <tbody>
                {sessions.length === 0 ? (
                  <tr><td colSpan={6} style={{ textAlign: 'center', color: 'var(--text-dim)', padding: 24 }}>{selectedConn ? 'Aucune session active' : 'Sélectionnez une connexion Oracle'}</td></tr>
                ) : sessions.map((s: any, i) => (
                  <tr key={i}>
                    <td className="font-mono">{s.sid}</td>
                    <td className="primary">{s.username}</td>
                    <td><span className={`badge badge-${s.status === 'ACTIVE' ? 'success' : 'muted'}`}>{s.status}</span></td>
                    <td style={{ fontSize: 11 }}>{s.event}</td>
                    <td style={{ fontSize: 11 }}>{s.machine}</td>
                    <td className="font-mono" style={{ fontSize: 10, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.sql_text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === 'privileges' && (
        <div>
          <div style={{ marginBottom: 14 }}>
            <select value={selectedConn} onChange={e => setSelectedConn(e.target.value)} style={{ width: 'auto', padding: '8px 12px' }}>
              <option value="">— Choisir une connexion Oracle —</option>
              {connections.filter(c => c.db_type === 'oracle').map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          {privileges.length > 0 && (
            <div style={{ marginBottom: 14, padding: '12px 16px', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 10 }}>
              <AlertTriangle size={14} color="var(--danger)" />
              <span style={{ fontSize: 13, color: 'var(--danger)' }}>{privileges.length} privilège(s) dangereux détecté(s)</span>
            </div>
          )}
          <div className="card">
            <table className="table-raxus">
              <thead><tr><th>Grantee</th><th>Privilège</th><th>Admin option</th></tr></thead>
              <tbody>
                {privileges.length === 0 ? (
                  <tr><td colSpan={3} style={{ textAlign: 'center', color: 'var(--text-dim)', padding: 24 }}>{selectedConn ? 'Aucun privilège dangereux' : 'Sélectionnez une connexion Oracle'}</td></tr>
                ) : privileges.map((p: any, i) => (
                  <tr key={i}>
                    <td className="primary">{p.grantee}</td>
                    <td className="font-mono" style={{ color: 'var(--danger)' }}>{p.privilege}</td>
                    <td>{p.admin_option === 'YES' ? <span className="badge badge-danger">YES</span> : 'NO'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
