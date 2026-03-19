import { useEffect, useState } from 'react'
import { usersApi } from '../lib/api'
import { useAuthStore } from '../stores'
import { Plus, X, UserCheck, UserX, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'

const ROLES = ['admin','dba','analyst','viewer']
const roleColor: Record<string,string> = { admin:'var(--oracle)', dba:'var(--accent)', analyst:'var(--success)', viewer:'var(--text-muted)' }

export default function UsersPage() {
  const { can } = useAuthStore()
  const [users, setUsers] = useState<any[]>([])
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState({ username:'', email:'', password:'', role:'viewer', full_name:'' })
  const [loading, setLoading] = useState(false)

  const load = async () => {
    try { const u = await usersApi.list(); setUsers(Array.isArray(u)?u:[]) } catch { toast.error('Erreur chargement utilisateurs') }
  }
  useEffect(()=>{ load() },[])

  const create = async () => {
    if (!form.username||!form.email||!form.password) return toast.error('Champs requis manquants')
    setLoading(true)
    try { await usersApi.create(form); setShowModal(false); setForm({ username:'',email:'',password:'',role:'viewer',full_name:'' }); await load(); toast.success('Utilisateur créé') }
    catch(e:any){ toast.error(e?.response?.data?.detail||'Erreur') } finally { setLoading(false) }
  }

  const toggleActive = async (id:string, active:boolean) => {
    await usersApi.update(id,{ active:!active }); await load()
    toast.success(active?'Utilisateur suspendu':'Utilisateur réactivé')
  }

  const del = async (id:string, username:string) => {
    if (!confirm(`Supprimer "${username}" ?`)) return
    await usersApi.delete(id); await load(); toast.success('Utilisateur supprimé')
  }

  if (!can('admin')) return <div style={{ padding:40, textAlign:'center', color:'var(--text-dim)' }}>Accès refusé — rôle admin requis</div>

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
        <div><h1 className="page-title font-display">Utilisateurs</h1><p className="page-sub">Gestion des comptes et des rôles</p></div>
        <button className="btn btn-primary" onClick={()=>setShowModal(true)}><Plus size={14}/> Nouvel utilisateur</button>
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12, marginBottom:20 }}>
        {ROLES.map(role=>({role, count:users.filter(u=>u.role===role).length})).map(({role,count})=>(
          <div key={role} className="metric-card">
            <div className="metric-label">{role}</div>
            <div className="metric-value" style={{ color:roleColor[role] }}>{count}</div>
          </div>
        ))}
      </div>

      <div className="card">
        <table className="table-raxus">
          <thead><tr><th>Utilisateur</th><th>Email</th><th>Rôle</th><th>Statut</th><th>Dernière connexion</th><th>Actions</th></tr></thead>
          <tbody>
            {users.map((u:any)=>(
              <tr key={u.id}>
                <td>
                  <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                    <div style={{ width:30, height:30, borderRadius:'50%', background:`${roleColor[u.role]}20`, border:`1.5px solid ${roleColor[u.role]}40`, display:'flex', alignItems:'center', justifyContent:'center', fontSize:12, fontWeight:600, color:roleColor[u.role] }}>
                      {u.username[0].toUpperCase()}
                    </div>
                    <div>
                      <div style={{ fontSize:13, fontWeight:500, color:'var(--text-primary)' }}>{u.username}</div>
                      {u.full_name && <div style={{ fontSize:11, color:'var(--text-dim)' }}>{u.full_name}</div>}
                    </div>
                  </div>
                </td>
                <td style={{ fontSize:12 }}>{u.email}</td>
                <td><span style={{ fontSize:12, fontWeight:500, color:roleColor[u.role] }}>{u.role}</span></td>
                <td><span className={`badge badge-${u.active?'success':'danger'}`}>{u.active?'Actif':'Suspendu'}</span></td>
                <td style={{ fontSize:11 }}>{u.last_login_at?new Date(u.last_login_at).toLocaleString('fr'):'Jamais'}</td>
                <td>
                  <div style={{ display:'flex', gap:4 }}>
                    <button className="btn-icon" onClick={()=>toggleActive(u.id, u.active)} title={u.active?'Suspendre':'Activer'}>
                      {u.active?<UserX size={13}/>:<UserCheck size={13}/>}
                    </button>
                    <button className="btn-icon" onClick={()=>del(u.id, u.username)} title="Supprimer">
                      <Trash2 size={13} color="var(--danger)"/>
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showModal && (
        <div className="modal-overlay" onClick={e=>e.target===e.currentTarget&&setShowModal(false)}>
          <div className="modal">
            <div style={{ display:'flex', justifyContent:'space-between', marginBottom:20 }}>
              <h2 className="modal-title" style={{ margin:0 }}>Nouvel utilisateur</h2>
              <button className="btn-icon" onClick={()=>setShowModal(false)}><X size={14}/></button>
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
                <div><label style={{ fontSize:12, color:'var(--text-muted)', marginBottom:5, display:'block' }}>Nom d'utilisateur *</label>
                  <input value={form.username} onChange={e=>setForm(f=>({...f,username:e.target.value}))} placeholder="jdupont"/></div>
                <div><label style={{ fontSize:12, color:'var(--text-muted)', marginBottom:5, display:'block' }}>Nom complet</label>
                  <input value={form.full_name} onChange={e=>setForm(f=>({...f,full_name:e.target.value}))} placeholder="Jean Dupont"/></div>
              </div>
              <div><label style={{ fontSize:12, color:'var(--text-muted)', marginBottom:5, display:'block' }}>Email *</label>
                <input type="email" value={form.email} onChange={e=>setForm(f=>({...f,email:e.target.value}))} placeholder="j.dupont@example.com"/></div>
              <div><label style={{ fontSize:12, color:'var(--text-muted)', marginBottom:5, display:'block' }}>Mot de passe *</label>
                <input type="password" value={form.password} onChange={e=>setForm(f=>({...f,password:e.target.value}))} placeholder="••••••••"/></div>
              <div><label style={{ fontSize:12, color:'var(--text-muted)', marginBottom:5, display:'block' }}>Rôle</label>
                <select value={form.role} onChange={e=>setForm(f=>({...f,role:e.target.value}))}>
                  {ROLES.map(r=><option key={r} value={r}>{r}</option>)}
                </select></div>
              <div style={{ display:'flex', gap:10, justifyContent:'flex-end' }}>
                <button className="btn btn-ghost" onClick={()=>setShowModal(false)}>Annuler</button>
                <button className="btn btn-primary" onClick={create} disabled={loading||!form.username||!form.email||!form.password}>
                  {loading?<span className="spinner"/>:<Plus size={13}/>} Créer
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
