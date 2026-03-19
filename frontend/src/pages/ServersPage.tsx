import { useEffect, useState } from 'react'
import { agentsApi } from '../lib/api'
import { Server, RefreshCw, Terminal } from 'lucide-react'
import toast from 'react-hot-toast'

const COMMANDS = ['disk_usage','top_processes','uptime','read_log']

export default function ServersPage() {
  const [servers, setServers] = useState<any[]>([])
  const [cmdResult, setCmdResult] = useState<Record<string, any>>({})
  const [running, setRunning] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try { const s = await agentsApi.list(); setServers(Array.isArray(s)?s:[]) } catch { toast.error('Erreur chargement serveurs') }
    finally { setLoading(false) }
  }
  useEffect(()=>{ load() },[])

  const sendCommand = async (server_id: string, command: string) => {
    setRunning(`${server_id}-${command}`)
    try {
      const res = await agentsApi.sendCommand(server_id, command)
      setCmdResult(prev=>({ ...prev, [`${server_id}-${command}`]: res }))
      toast.success(`Commande "${command}" envoyée`)
    } catch { toast.error('Erreur envoi commande') }
    finally { setRunning(null) }
  }

  const statusColor: Record<string,string> = { online:'var(--success)', offline:'var(--danger)', unknown:'var(--text-dim)' }

  return (
    <div className="fade-in">
      <div className="page-header" style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
        <div><h1 className="page-title font-display">Serveurs</h1><p className="page-sub">Agents de monitoring — état et commandes à distance</p></div>
        <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading}>{loading?<span className="spinner"/>:<RefreshCw size={13}/>} Actualiser</button>
      </div>

      {servers.length === 0 ? (
        <div className="card empty-state">
          <Server size={36}/>
          <p>Aucun serveur enregistré.<br/>Installez l'agent Raxus sur vos serveurs Linux.</p>
          <code style={{ fontSize:11, color:'var(--text-muted)', background:'var(--bg-overlay)', padding:'8px 14px', borderRadius:7, display:'block', textAlign:'left' }}>
            python raxus_agent.py --config /etc/raxus/agent.yaml
          </code>
        </div>
      ) : (
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(340px, 1fr))', gap:14 }}>
          {servers.map((srv:any)=>(
            <div key={srv.id} className="card" style={{ padding:18 }}>
              <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:14 }}>
                <div style={{ width:40, height:40, borderRadius:10, background:'var(--bg-overlay)', border:'1px solid var(--border)', display:'flex', alignItems:'center', justifyContent:'center' }}>
                  <Server size={18} color="var(--text-muted)"/>
                </div>
                <div style={{ flex:1 }}>
                  <div style={{ fontWeight:600, fontSize:14, color:'var(--text-primary)' }}>{srv.hostname||srv.id}</div>
                  <div style={{ fontSize:11, color:'var(--text-muted)' }}>{srv.ip_address||'IP inconnue'}</div>
                </div>
                <span style={{ fontSize:11, fontWeight:500, color:statusColor[srv.status]||'var(--text-dim)' }}>
                  {srv.status==='online'&&<span className="dot dot-green pulse" style={{ display:'inline-block', marginRight:5 }}/>}
                  {srv.status}
                </span>
              </div>

              <div style={{ fontSize:11, color:'var(--text-muted)', marginBottom:14, display:'flex', flexDirection:'column', gap:3 }}>
                <div><span style={{ color:'var(--text-dim)' }}>Agent : </span>v{srv.agent_version||'—'}</div>
                <div><span style={{ color:'var(--text-dim)' }}>Vu : </span>{srv.last_seen_at?new Date(srv.last_seen_at).toLocaleString('fr'):'Jamais'}</div>
              </div>

              <div style={{ borderTop:'1px solid var(--border)', paddingTop:12 }}>
                <div style={{ fontSize:11, color:'var(--text-dim)', marginBottom:8, display:'flex', alignItems:'center', gap:6 }}>
                  <Terminal size={11}/> Commandes distantes
                </div>
                <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
                  {COMMANDS.map(cmd=>(
                    <button key={cmd} className="btn btn-ghost btn-sm" onClick={()=>sendCommand(srv.id, cmd)} disabled={running===`${srv.id}-${cmd}`}>
                      {running===`${srv.id}-${cmd}`?<span className="spinner"/>:null}
                      {cmd}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
