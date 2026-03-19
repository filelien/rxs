import { useEffect, useState, useCallback } from 'react'
import { useConnectionsStore } from '../stores'
import { monitoringApi } from '../lib/api'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { Activity, AlertTriangle, CheckCircle, RefreshCw, Bell, X } from 'lucide-react'
import toast from 'react-hot-toast'

const C={bg2:'#0d1425',bg3:'#111b30',border:'#1a2640',blue:'#3b8ef3',teal:'#00d4aa',amber:'#f59e0b',red:'#ef4444',green:'#22c55e',text0:'#f0f4ff',text1:'#8ba3c7',text2:'#3d5a7a'}

function Card({children,style={}}:any){return <div style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:12,padding:'18px 20px',...style}}>{children}</div>}
function SectionTitle({title,sub}:any){return <div style={{marginBottom:14}}><div style={{fontSize:13,fontWeight:600,color:C.text0}}>{title}</div>{sub&&<div style={{fontSize:11,color:C.text2,marginTop:2}}>{sub}</div>}</div>}

export default function MonitoringPage(){
  const{connections,activeConnectionId}=useConnectionsStore()
  const[dashboard,setDashboard]=useState<any>(null)
  const[history,setHistory]=useState<any[]>([])
  const[selectedConn,setSelectedConn]=useState(activeConnectionId||'')
  const[metric,setMetric]=useState('avg_query_ms')
  const[timeWindow,setTimeWindow]=useState(60)
  const[loading,setLoading]=useState(false)
  const[rules,setRules]=useState<any[]>([])
  const[showNewRule,setShowNewRule]=useState(false)
  const[newRule,setNewRule]=useState({name:'',metric_name:'avg_query_ms',condition_op:'>',threshold:'',severity:'warning'})

  const load=useCallback(async()=>{
    setLoading(true)
    try{
      const[d,r]=await Promise.allSettled([monitoringApi.dashboard(),monitoringApi.alertRules()])
      if(d.status==='fulfilled')setDashboard(d.value)
      if(r.status==='fulfilled')setRules(Array.isArray(r.value)?r.value:[])
    }catch{toast.error('Erreur monitoring')}
    finally{setLoading(false)}
  },[])

  const loadHistory=useCallback(async()=>{
    if(!selectedConn)return
    try{
      const h=await monitoringApi.history(selectedConn,metric,timeWindow)
      setHistory(Array.isArray(h)?h.map((p:any)=>({...p,value:parseFloat(p.value||0).toFixed(1)})):[])
    }catch{}
  },[selectedConn,metric,timeWindow])

  useEffect(()=>{load()},[load])
  useEffect(()=>{loadHistory()},[loadHistory])
  useEffect(()=>{const iv=setInterval(()=>{load();loadHistory()},30000);return()=>clearInterval(iv)},[load,loadHistory])

  const ackAlert=async(id:number)=>{
    try{await monitoringApi.ackAlert(id);await load();toast.success('Alerte acquittée')}
    catch{toast.error('Erreur')}
  }
  const resolveAlert=async(id:number)=>{
    try{await monitoringApi.resolveAlert(id);await load();toast.success('Alerte résolue')}
    catch{toast.error('Erreur')}
  }
  const createRule=async()=>{
    if(!newRule.name||!newRule.threshold)return toast.error('Nom et seuil requis')
    try{
      await monitoringApi.createRule({...newRule,threshold:parseFloat(newRule.threshold)})
      setShowNewRule(false);setNewRule({name:'',metric_name:'avg_query_ms',condition_op:'>',threshold:'',severity:'warning'})
      await load();toast.success('Règle créée')
    }catch{toast.error('Erreur création règle')}
  }

  const s=dashboard?.summary||{}
  const conns=dashboard?.connectors||[]
  const alerts=dashboard?.alerts||[]
  const servers=dashboard?.servers||[]

  return(
    <div style={{padding:'24px 26px',background:'#05080f',minHeight:'100%'}}>
      <div style={{display:'flex',alignItems:'flex-start',justifyContent:'space-between',marginBottom:20}}>
        <div><h1 style={{fontSize:20,fontWeight:700,color:C.text0,fontFamily:'Syne,sans-serif',margin:0}}>Monitoring</h1>
        <p style={{fontSize:12,color:C.text2,marginTop:4,fontFamily:'DM Mono,monospace'}}>Métriques temps réel — auto-refresh 30s</p></div>
        <div style={{display:'flex',gap:8}}>
          <button onClick={()=>setShowNewRule(true)} style={{padding:'7px 14px',borderRadius:8,border:`1px solid ${C.borderLit||C.border}`,background:C.bg3,color:C.teal,fontSize:12,cursor:'pointer',display:'flex',alignItems:'center',gap:6}}>
            <Bell size={12}/>Nouvelle règle
          </button>
          <button onClick={()=>{load();loadHistory()}} disabled={loading} style={{padding:'7px 14px',borderRadius:8,border:`1px solid ${C.border}`,background:C.bg3,color:C.text1,fontSize:12,cursor:'pointer',display:'flex',alignItems:'center',gap:6}}>
            <RefreshCw size={12} style={loading?{animation:'spin 0.8s linear infinite'}:{}}/>Actualiser
          </button>
        </div>
      </div>

      {/* KPIs */}
      <div style={{display:'grid',gridTemplateColumns:'repeat(5,1fr)',gap:10,marginBottom:18}}>
        {[
          {label:'Connecteurs',value:s.total_connectors||0,sub:`${s.active_connectors||0} actifs`,color:C.blue},
          {label:'Alertes critiques',value:s.critical_alerts||0,sub:`${s.warning_alerts||0} warnings`,color:(s.critical_alerts||0)>0?C.red:C.green},
          {label:'Requêtes lentes',value:s.slow_queries_count||0,sub:'Seuil > 1s',color:(s.slow_queries_count||0)>0?C.amber:C.teal},
          {label:'Serveurs en ligne',value:s.online_servers||0,sub:`sur ${servers.length}`,color:s.online_servers===servers.length&&servers.length>0?C.green:C.amber},
          {label:'Règles d\'alerte',value:rules.length,sub:'configurées',color:C.blue},
        ].map(({label,value,sub,color})=>(
          <div key={label} style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:10,padding:'14px 16px',position:'relative',overflow:'hidden'}}>
            <div style={{position:'absolute',inset:0,background:`radial-gradient(ellipse at top right,${color}08,transparent 60%)`,pointerEvents:'none'}}/>
            <div style={{fontSize:10,color:C.text2,textTransform:'uppercase',letterSpacing:'0.07em',marginBottom:6}}>{label}</div>
            <div style={{fontSize:26,fontWeight:700,color,fontFamily:'Syne,sans-serif'}}>{value}</div>
            <div style={{fontSize:11,color:C.text2,marginTop:3}}>{sub}</div>
          </div>
        ))}
      </div>

      <div style={{display:'grid',gridTemplateColumns:'1fr 340px',gap:14,marginBottom:14}}>
        {/* History chart */}
        <Card>
          <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:16,flexWrap:'wrap'}}>
            <div style={{fontSize:13,fontWeight:600,color:C.text0,flex:1}}>Historique de métriques</div>
            <select value={selectedConn} onChange={e=>setSelectedConn(e.target.value)} style={{padding:'5px 10px',fontSize:11,borderRadius:6,background:C.bg3,border:`1px solid ${C.border}`,color:C.text1,width:'auto'}}>
              <option value="">— Connexion —</option>
              {connections.filter(c=>c.enabled).map(c=><option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            <select value={metric} onChange={e=>setMetric(e.target.value)} style={{padding:'5px 10px',fontSize:11,borderRadius:6,background:C.bg3,border:`1px solid ${C.border}`,color:C.text1,width:'auto'}}>
              <option value="avg_query_ms">Latence (ms)</option>
              <option value="active_connections">Connexions actives</option>
              <option value="slow_queries_count">Requêtes lentes</option>
              <option value="cpu_percent">CPU %</option>
              <option value="memory_percent">RAM %</option>
            </select>
            <select value={timeWindow} onChange={e=>setTimeWindow(+e.target.value)} style={{padding:'5px 10px',fontSize:11,borderRadius:6,background:C.bg3,border:`1px solid ${C.border}`,color:C.text1,width:'auto'}}>
              <option value={15}>15 min</option><option value={60}>1h</option>
              <option value={360}>6h</option><option value={1440}>24h</option>
            </select>
          </div>
          {history.length>0?(
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={history}>
                <defs><linearGradient id="hg" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={C.blue} stopOpacity={0.2}/><stop offset="95%" stopColor={C.blue} stopOpacity={0}/>
                </linearGradient></defs>
                <CartesianGrid strokeDasharray="3 3" stroke={C.border} vertical={false}/>
                <XAxis dataKey="timestamp" tick={{fontSize:10,fill:C.text2}} tickFormatter={v=>new Date(v).toLocaleTimeString('fr',{hour:'2-digit',minute:'2-digit'})} axisLine={false} tickLine={false}/>
                <YAxis tick={{fontSize:10,fill:C.text2}} axisLine={false} tickLine={false} width={35}/>
                <Tooltip contentStyle={{background:C.bg3,border:`1px solid ${C.border}`,borderRadius:8,fontSize:12,color:C.text0}} labelFormatter={v=>new Date(v).toLocaleString('fr')}/>
                <Area type="monotone" dataKey="value" name={metric} stroke={C.blue} strokeWidth={2} fill="url(#hg)" dot={false}/>
              </AreaChart>
            </ResponsiveContainer>
          ):(
            <div style={{height:220,display:'flex',alignItems:'center',justifyContent:'center',color:C.text2,fontSize:13}}>
              {selectedConn?'Aucune donnée — le scraping démarre dès qu\'une requête est exécutée':'Sélectionnez une connexion'}
            </div>
          )}
        </Card>

        {/* Connectors status */}
        <Card>
          <SectionTitle title="Statut des connecteurs"/>
          {conns.length===0?<div style={{color:C.text2,fontSize:12,padding:'12px 0'}}>Aucun connecteur actif</div>:
          conns.map((c:any)=>(
            <div key={c.connector_id} style={{display:'flex',alignItems:'center',gap:10,padding:'8px 0',borderBottom:`1px solid ${C.border}`}}>
              <span style={{width:7,height:7,borderRadius:'50%',background:c.connected?C.green:C.red,flexShrink:0,boxShadow:c.connected?`0 0 6px ${C.green}`:undefined}}/>
              <div style={{flex:1,minWidth:0}}>
                <div style={{fontSize:12,fontWeight:500,color:C.text0,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{c.name||c.connector_id}</div>
                <div style={{fontSize:10,color:C.text2}}>{c.db_type}</div>
              </div>
              <span style={{fontSize:10,padding:'2px 7px',borderRadius:4,fontWeight:700,background:c.connected?`${C.green}18`:`${C.red}18`,color:c.connected?C.green:C.red}}>{c.connected?'UP':'DOWN'}</span>
            </div>
          ))}
        </Card>
      </div>

      {/* Alerts */}
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:14,marginBottom:14}}>
        <Card>
          <SectionTitle title="Alertes actives" sub={`${alerts.length} alerte(s)`}/>
          {alerts.length===0?(
            <div style={{display:'flex',alignItems:'center',gap:10,color:C.teal,fontSize:13,padding:'12px 0'}}><CheckCircle size={16}/>Aucune alerte active</div>
          ):alerts.map((a:any)=>{
            const col=a.severity==='critical'?C.red:C.amber
            return(
              <div key={a.id} style={{display:'flex',alignItems:'flex-start',gap:9,padding:'9px 0',borderBottom:`1px solid ${C.border}`}}>
                <AlertTriangle size={13} color={col} style={{marginTop:1,flexShrink:0}}/>
                <div style={{flex:1,minWidth:0}}>
                  <div style={{fontSize:12,color:C.text0,fontWeight:500,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{a.rule_name||a.message?.slice(0,50)||'Alerte'}</div>
                  <div style={{fontSize:10,color:C.text2,marginTop:2}}>
                    {a.connector_id||a.server_id||'—'} · val={a.metric_value} · {a.fired_at?new Date(a.fired_at).toLocaleTimeString('fr'):'now'}
                  </div>
                </div>
                <div style={{display:'flex',gap:4,flexShrink:0}}>
                  <button onClick={()=>ackAlert(a.id)} style={{fontSize:10,padding:'2px 7px',borderRadius:4,border:`1px solid ${C.amber}40`,background:'transparent',color:C.amber,cursor:'pointer'}}>ACK</button>
                  <button onClick={()=>resolveAlert(a.id)} style={{fontSize:10,padding:'2px 7px',borderRadius:4,border:`1px solid ${C.teal}40`,background:'transparent',color:C.teal,cursor:'pointer'}}>OK</button>
                </div>
              </div>
            )
          })}
        </Card>

        {/* Alert rules */}
        <Card>
          <SectionTitle title="Règles d'alerte configurées"/>
          {rules.length===0?<div style={{color:C.text2,fontSize:12,padding:'8px 0'}}>Aucune règle. Cliquez «Nouvelle règle» pour en créer.</div>:
          rules.map((r:any)=>(
            <div key={r.id} style={{display:'flex',alignItems:'center',gap:8,padding:'7px 0',borderBottom:`1px solid ${C.border}`}}>
              <div style={{flex:1,minWidth:0}}>
                <div style={{fontSize:12,fontWeight:500,color:C.text0,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{r.name}</div>
                <div style={{fontSize:10,color:C.text2,fontFamily:'DM Mono,monospace'}}>{r.metric_name} {r.condition_op} {r.threshold}</div>
              </div>
              <span style={{fontSize:9,padding:'2px 7px',borderRadius:4,fontWeight:700,background:r.severity==='critical'?`${C.red}18`:r.severity==='warning'?`${C.amber}18`:`${C.teal}18`,color:r.severity==='critical'?C.red:r.severity==='warning'?C.amber:C.teal}}>{r.severity}</span>
              <span style={{fontSize:9,padding:'2px 6px',borderRadius:4,background:r.enabled?`${C.green}15`:`${C.text2}15`,color:r.enabled?C.green:C.text2}}>{r.enabled?'ON':'OFF'}</span>
            </div>
          ))}
        </Card>
      </div>

      {/* New rule modal */}
      {showNewRule&&(
        <div style={{position:'fixed',inset:0,background:'rgba(0,0,0,0.7)',display:'flex',alignItems:'center',justifyContent:'center',zIndex:1000,padding:20}}>
          <div style={{background:'#111b30',border:`1px solid ${C.border}`,borderRadius:12,padding:24,width:'100%',maxWidth:480}}>
            <div style={{display:'flex',justifyContent:'space-between',marginBottom:20}}>
              <div style={{fontSize:15,fontWeight:600,color:C.text0,fontFamily:'Syne,sans-serif'}}>Nouvelle règle d'alerte</div>
              <button onClick={()=>setShowNewRule(false)} style={{background:'none',border:'none',cursor:'pointer',color:C.text2}}><X size={16}/></button>
            </div>
            <div style={{display:'flex',flexDirection:'column',gap:12}}>
              {[{label:'Nom',key:'name',placeholder:'CPU critique serveur prod'},
                {label:'Métrique',key:'metric_name',type:'select',options:['avg_query_ms','active_connections','slow_queries_count','cpu_percent','memory_percent','uptime_seconds']},
                {label:'Condition',key:'condition_op',type:'select',options:['>','<','==','!=','>=','<=']},
                {label:'Seuil',key:'threshold',placeholder:'85',type:'number'},
                {label:'Sévérité',key:'severity',type:'select',options:['info','warning','critical']},
              ].map(({label,key,placeholder,type,options})=>(
                <div key={key}>
                  <label style={{fontSize:11,color:C.text2,marginBottom:4,display:'block'}}>{label}</label>
                  {type==='select'?(
                    <select value={(newRule as any)[key]} onChange={e=>setNewRule(r=>({...r,[key]:e.target.value}))}
                      style={{width:'100%',padding:'7px 10px',borderRadius:7,background:'#080d18',border:`1px solid ${C.border}`,color:C.text1,fontSize:12}}>
                      {options?.map(o=><option key={o} value={o}>{o}</option>)}
                    </select>
                  ):(
                    <input type={type||'text'} value={(newRule as any)[key]} onChange={e=>setNewRule(r=>({...r,[key]:e.target.value}))} placeholder={placeholder}
                      style={{width:'100%',padding:'7px 10px',borderRadius:7,background:'#080d18',border:`1px solid ${C.border}`,color:C.text1,fontSize:12}}/>
                  )}
                </div>
              ))}
              <div style={{display:'flex',gap:10,justifyContent:'flex-end',marginTop:4}}>
                <button onClick={()=>setShowNewRule(false)} style={{padding:'7px 16px',borderRadius:7,border:`1px solid ${C.border}`,background:'transparent',color:C.text1,cursor:'pointer',fontSize:12}}>Annuler</button>
                <button onClick={createRule} style={{padding:'7px 16px',borderRadius:7,border:'none',background:C.blue,color:'#fff',cursor:'pointer',fontSize:12,fontWeight:500}}>Créer la règle</button>
              </div>
            </div>
          </div>
        </div>
      )}
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  )
}
