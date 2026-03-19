import { useState, useEffect } from 'react'
import { useConnectionsStore } from '../stores'
import { connectionsApi } from '../lib/api'
import toast from 'react-hot-toast'
import { Plus, Trash2, Zap, Database, Eye, EyeOff, RefreshCw, ToggleLeft, ToggleRight, X } from 'lucide-react'

const DB_TYPES = [
  { value: 'oracle',     label: 'Oracle',     color: 'var(--oracle)' },
  { value: 'mysql',      label: 'MySQL',      color: 'var(--mysql)' },
  { value: 'postgresql', label: 'PostgreSQL', color: 'var(--postgres)' },
  { value: 'mongodb',    label: 'MongoDB',    color: 'var(--mongodb)' },
  { value: 'redis',      label: 'Redis',      color: 'var(--redis)' },
]

const DEFAULT_PORTS: Record<string, number> = { oracle: 1521, mysql: 3306, postgresql: 5432, mongodb: 27017, redis: 6379 }

const INITIAL_FORM = {
  name: '', db_type: 'mysql', host: '', port: 3306,
  database_name: '', username: '', password: '',
  description: '', ssh_tunnel: false, ssh_host: '', ssh_port: 22, ssh_user: '',
}

export default function ConnectionsPage() {
  const { connections, setConnections, addConnection, removeConnection, updateTest } = useConnectionsStore()
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState(INITIAL_FORM)
  const [showPassword, setShowPassword] = useState(false)
  const [creating, setCreating] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)

  useEffect(() => {
    connectionsApi.list().then(setConnections).catch(() => toast.error('Erreur chargement connexions'))
  }, [])

  const handleDbTypeChange = (db_type: string) => {
    setForm(f => ({ ...f, db_type, port: DEFAULT_PORTS[db_type] || 5432 }))
  }

  const handleCreate = async () => {
    if (!form.name || !form.host) return toast.error('Nom et hôte requis')
    setCreating(true)
    try {
      const payload = {
        name: form.name, db_type: form.db_type, description: form.description,
        config: {
          host: form.host, port: form.port,
          database: form.database_name, user: form.username, password: form.password,
          service_name: form.database_name, // for Oracle
        }
      }
      const res = await connectionsApi.create(payload)
      const newConn = { id: res.id, name: form.name, db_type: form.db_type, host: form.host, database_name: form.database_name, enabled: true, last_test_ok: null, last_test_ms: null }
      addConnection(newConn)
      setShowModal(false)
      setForm(INITIAL_FORM)
      toast.success(`Connexion "${form.name}" créée et active`)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Échec de la connexion')
    } finally {
      setCreating(false)
    }
  }

  const handleTest = async (id: string, name: string) => {
    setTestingId(id)
    try {
      const res = await connectionsApi.test(id)
      updateTest(id, res.healthy, res.latency_ms || 0)
      if (res.healthy) toast.success(`${name} — ${res.latency_ms}ms · ${res.version || ''}`)
      else toast.error(`${name} — ${res.error || 'Connexion échouée'}`)
    } catch {
      updateTest(id, false, 0)
      toast.error(`Test échoué pour ${name}`)
    } finally {
      setTestingId(null)
    }
  }

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Supprimer la connexion "${name}" ?`)) return
    try {
      await connectionsApi.delete(id)
      removeConnection(id)
      toast.success(`"${name}" supprimée`)
    } catch {
      toast.error('Erreur lors de la suppression')
    }
  }

  const dbInfo = (type: string) => DB_TYPES.find(d => d.value === type) || DB_TYPES[1]

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <h1 className="page-title font-display">Connexions</h1>
          <p className="page-sub">Gérez vos sources de données — Oracle, MySQL, PostgreSQL, MongoDB, Redis</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
          <Plus size={15} /> Nouvelle connexion
        </button>
      </div>

      {/* Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24 }}>
        {[
          { label: 'Total', value: connections.length },
          { label: 'Actives', value: connections.filter(c => c.enabled).length, color: 'var(--success)' },
          { label: 'Testées OK', value: connections.filter(c => c.last_test_ok).length, color: 'var(--accent)' },
          { label: 'Erreur', value: connections.filter(c => c.last_test_ok === false).length, color: 'var(--danger)' },
        ].map(({ label, value, color }) => (
          <div key={label} className="metric-card">
            <div className="metric-label">{label}</div>
            <div className="metric-value" style={color ? { color } : {}}>{value}</div>
          </div>
        ))}
      </div>

      {/* Connections grid */}
      {connections.length === 0 ? (
        <div className="card empty-state">
          <Database size={40} />
          <p>Aucune connexion configurée.<br />Ajoutez votre première base de données.</p>
          <button className="btn btn-primary" onClick={() => setShowModal(true)}>
            <Plus size={14} /> Ajouter une connexion
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 14 }}>
          {connections.map((conn) => {
            const db = dbInfo(conn.db_type)
            const isTesting = testingId === conn.id
            return (
              <div key={conn.id} className="card" style={{ padding: 18 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{
                      width: 38, height: 38, borderRadius: 9,
                      background: `${db.color}15`,
                      border: `1px solid ${db.color}30`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                      <Database size={18} color={db.color} />
                    </div>
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>{conn.name}</div>
                      <span className={`badge badge-${conn.db_type}`}>{conn.db_type}</span>
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    {conn.enabled
                      ? <span className="dot dot-green pulse" />
                      : <span className="dot dot-gray" />
                    }
                  </div>
                </div>

                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 14, display: 'flex', flexDirection: 'column', gap: 3 }}>
                  <div><span style={{ color: 'var(--text-dim)' }}>Hôte : </span>{conn.host}</div>
                  {conn.database_name && <div><span style={{ color: 'var(--text-dim)' }}>Base : </span>{conn.database_name}</div>}
                  {conn.last_test_ms != null && (
                    <div>
                      <span style={{ color: 'var(--text-dim)' }}>Latence : </span>
                      <span style={{ color: conn.last_test_ok ? 'var(--success)' : 'var(--danger)' }}>
                        {conn.last_test_ok ? `${conn.last_test_ms}ms` : 'Erreur'}
                      </span>
                    </div>
                  )}
                </div>

                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => handleTest(conn.id, conn.name)} disabled={isTesting} style={{ flex: 1, justifyContent: 'center' }}>
                    {isTesting ? <span className="spinner" /> : <><Zap size={13} /> Tester</>}
                  </button>
                  <button className="btn btn-danger btn-sm btn-icon" onClick={() => handleDelete(conn.id, conn.name)}>
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Modal création */}
      {showModal && (
        <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && setShowModal(false)}>
          <div className="modal" style={{ maxWidth: 560, maxHeight: '90vh', overflowY: 'auto' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
              <h2 className="modal-title" style={{ margin: 0 }}>Nouvelle connexion</h2>
              <button className="btn-icon" onClick={() => setShowModal(false)}><X size={14} /></button>
            </div>

            {/* DB Type selector */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8, marginBottom: 20 }}>
              {DB_TYPES.map(({ value, label, color }) => (
                <button
                  key={value}
                  onClick={() => handleDbTypeChange(value)}
                  style={{
                    padding: '10px 4px', borderRadius: 8, border: '1px solid',
                    borderColor: form.db_type === value ? color : 'var(--border)',
                    background: form.db_type === value ? `${color}15` : 'var(--bg-overlay)',
                    color: form.db_type === value ? color : 'var(--text-muted)',
                    cursor: 'pointer', fontSize: 11, fontWeight: 500, textAlign: 'center',
                    transition: 'all 0.15s',
                  }}
                >
                  <Database size={14} style={{ margin: '0 auto 4px', display: 'block' }} />
                  {label}
                </button>
              ))}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 5, display: 'block' }}>Nom *</label>
                  <input value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="Production Oracle" />
                </div>
                <div>
                  <label style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 5, display: 'block' }}>Description</label>
                  <input value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} placeholder="Optionnel" />
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 5, display: 'block' }}>Hôte *</label>
                  <input value={form.host} onChange={e => setForm(f => ({ ...f, host: e.target.value }))} placeholder="192.168.1.10" />
                </div>
                <div>
                  <label style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 5, display: 'block' }}>Port</label>
                  <input type="number" value={form.port} onChange={e => setForm(f => ({ ...f, port: +e.target.value }))} style={{ width: 90 }} />
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 5, display: 'block' }}>
                    {form.db_type === 'oracle' ? 'Service Name / SID' : form.db_type === 'mongodb' ? 'Database' : form.db_type === 'redis' ? 'DB index' : 'Base de données'}
                  </label>
                  <input value={form.database_name} onChange={e => setForm(f => ({ ...f, database_name: e.target.value }))} placeholder={form.db_type === 'oracle' ? 'ORCL' : form.db_type === 'redis' ? '0' : 'mydb'} />
                </div>
                <div>
                  <label style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 5, display: 'block' }}>Utilisateur</label>
                  <input value={form.username} onChange={e => setForm(f => ({ ...f, username: e.target.value }))} placeholder={form.db_type === 'oracle' ? 'sys' : 'root'} />
                </div>
              </div>
              <div>
                <label style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 5, display: 'block' }}>Mot de passe</label>
                <div style={{ position: 'relative' }}>
                  <input type={showPassword ? 'text' : 'password'} value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} placeholder="••••••••" style={{ paddingRight: 40 }} />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} style={{ position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-dim)' }}>
                    {showPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>

              {/* SSH Tunnel */}
              <div style={{ borderTop: '1px solid var(--border)', paddingTop: 14 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13, color: 'var(--text-muted)' }}>
                  <input type="checkbox" checked={form.ssh_tunnel} onChange={e => setForm(f => ({ ...f, ssh_tunnel: e.target.checked }))} style={{ width: 'auto' }} />
                  Tunnel SSH
                </label>
                {form.ssh_tunnel && (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 10, marginTop: 12 }}>
                    <input value={form.ssh_host} onChange={e => setForm(f => ({ ...f, ssh_host: e.target.value }))} placeholder="SSH Host" />
                    <input type="number" value={form.ssh_port} onChange={e => setForm(f => ({ ...f, ssh_port: +e.target.value }))} style={{ width: 70 }} />
                    <input value={form.ssh_user} onChange={e => setForm(f => ({ ...f, ssh_user: e.target.value }))} placeholder="SSH User" />
                  </div>
                )}
              </div>

              <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 4 }}>
                <button className="btn btn-ghost" onClick={() => setShowModal(false)}>Annuler</button>
                <button className="btn btn-primary" onClick={handleCreate} disabled={creating || !form.name || !form.host}>
                  {creating ? <><span className="spinner" /> Connexion en cours…</> : <><Database size={14} /> Connecter</>}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
