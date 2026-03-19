import { useEffect, useState } from 'react'
import { tasksApi } from '../lib/api'
import { useConnectionsStore } from '../stores'
import { Plus, Play, StopCircle, X, RefreshCw } from 'lucide-react'
import toast from 'react-hot-toast'

const statusColor: Record<string,string> = { success:'var(--success)',failed:'var(--danger)',running:'var(--accent)',pending:'var(--warning)',cancelled:'var(--text-dim)' }

export default function TasksPage() {
  const { connections } = useConnectionsStore()
  const [tasks, setTasks] = useState<any[]>([])
  const [schedules, setSchedules] = useState<any[]>([])
  const [tab, setTab] = useState<'tasks'|'schedules'>('tasks')
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState({ name:'', type:'SQL_SCRIPT', connector_id:'', sql:'' })
  const [loading, setLoading] = useState(false)

  const load = async () => {
    const [t,s] = await Promise.allSettled([tasksApi.list(), tasksApi.schedules()])
    if (t.status==='fulfilled') setTasks(Array.isArray(t.value)?t.value:[])
    if (s.status==='fulfilled') setSchedules(Array.isArray(s.value)?s.value:[])
  }
  useEffect(()=>{ load() },[])

  const createTask = async () => {
    setLoading(true)
    try {
      await tasksApi.create({ name:form.name, type:form.type, connector_id:form.connector_id, payload:{ sql:form.sql } })
      setShowModal(false); setForm({ name:'', type:'SQL_SCRIPT', connector_id:'', sql:'' })
      await load(); toast.success('Tâche créée')
    } catch { toast.error('Erreur') } finally { setLoading(false) }
  }

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
        <div><h1 className="page-title font-display">Tâches</h1><p className="page-sub">Automatisation et planification</p></div>
        <div style={{ display:'flex', gap:8 }}>
          <button className="btn btn-ghost btn-sm" onClick={load}><RefreshCw size={13}/></button>
          <button className="btn btn-primary" onClick={()=>setShowModal(true)}><Plus size={14}/> Nouvelle tâche</button>
        </div>
      </div>
      <div className="tabs" style={{ marginBottom:20 }}>
        <button className={`tab ${tab==='tasks'?'active':''}`} onClick={()=>setTab('tasks')}>Exécutions ({tasks.length})</button>
        <button className={`tab ${tab==='schedules'?'active':''}`} onClick={()=>setTab('schedules')}>Planification ({schedules.length})</button>
      </div>
      {tab==='tasks' && (
        <div className="card">
          <table className="table-raxus">
            <thead><tr><th>Nom</th><th>Type</th><th>Statut</th><th>Durée</th><th>Résultat</th><th>Créé</th></tr></thead>
            <tbody>
              {tasks.length===0 ? <tr><td colSpan={6} style={{ textAlign:'center', color:'var(--text-dim)', padding:24 }}>Aucune tâche</td></tr>
              : tasks.map((t:any)=>(
                <tr key={t.id}>
                  <td className="primary">{t.name}</td>
                  <td><span className="badge badge-muted">{t.type}</span></td>
                  <td><span style={{ fontSize:12, fontWeight:500, color:statusColor[t.status]||'var(--text-muted)' }}>{t.status}</span></td>
                  <td className="font-mono" style={{ fontSize:11 }}>{t.duration_ms?`${t.duration_ms}ms`:'—'}</td>
                  <td style={{ fontSize:11, maxWidth:200, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{t.output||t.error_msg||'—'}</td>
                  <td style={{ fontSize:11 }}>{t.created_at?new Date(t.created_at).toLocaleString('fr'):'—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {tab==='schedules' && (
        <div className="card">
          <table className="table-raxus">
            <thead><tr><th>Nom</th><th>Cron</th><th>Prochaine exécution</th><th>Actions</th></tr></thead>
            <tbody>
              {schedules.length===0 ? <tr><td colSpan={4} style={{ textAlign:'center', color:'var(--text-dim)', padding:24 }}>Aucune planification</td></tr>
              : schedules.map((s:any)=>(
                <tr key={s.id}>
                  <td className="primary">{s.name}</td>
                  <td className="font-mono" style={{ fontSize:11 }}>{s.cron_expr}</td>
                  <td style={{ fontSize:11 }}>{s.next_run_at?new Date(s.next_run_at).toLocaleString('fr'):'—'}</td>
                  <td><button className="btn btn-ghost btn-sm" onClick={()=>tasksApi.triggerSchedule(s.id).then(load)}><Play size={11}/></button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {showModal && (
        <div className="modal-overlay" onClick={e=>e.target===e.currentTarget&&setShowModal(false)}>
          <div className="modal">
            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:20 }}>
              <h2 className="modal-title" style={{ margin:0 }}>Nouvelle tâche</h2>
              <button className="btn-icon" onClick={()=>setShowModal(false)}><X size={14}/></button>
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
              <div><label style={{ fontSize:12, color:'var(--text-muted)', marginBottom:5, display:'block' }}>Nom *</label>
                <input value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} placeholder="Backup nightly"/></div>
              <div><label style={{ fontSize:12, color:'var(--text-muted)', marginBottom:5, display:'block' }}>Type</label>
                <select value={form.type} onChange={e=>setForm(f=>({...f,type:e.target.value}))}>
                  <option value="SQL_SCRIPT">SQL Script</option>
                  <option value="ANALYZE">Analyse</option>
                  <option value="REPORT">Rapport</option>
                </select></div>
              <div><label style={{ fontSize:12, color:'var(--text-muted)', marginBottom:5, display:'block' }}>Connexion</label>
                <select value={form.connector_id} onChange={e=>setForm(f=>({...f,connector_id:e.target.value}))}>
                  <option value="">— Choisir —</option>
                  {connections.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}
                </select></div>
              {form.type==='SQL_SCRIPT' && <div><label style={{ fontSize:12, color:'var(--text-muted)', marginBottom:5, display:'block' }}>SQL</label>
                <textarea value={form.sql} onChange={e=>setForm(f=>({...f,sql:e.target.value}))} rows={4} style={{ fontFamily:'DM Mono', fontSize:12 }}/></div>}
              <div style={{ display:'flex', gap:10, justifyContent:'flex-end' }}>
                <button className="btn btn-ghost" onClick={()=>setShowModal(false)}>Annuler</button>
                <button className="btn btn-primary" onClick={createTask} disabled={loading||!form.name}>
                  {loading?<span className="spinner"/>:<Play size={13}/>} Lancer
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
