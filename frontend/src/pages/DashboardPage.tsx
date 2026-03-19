import { useEffect, useState, useCallback } from 'react'
import { useConnectionsStore } from '../stores'
import { monitoringApi, queryApi, auditApi, healthApi } from '../lib/api'
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, PieChart, Pie, Cell } from 'recharts'
import { Activity, Database, Shield, Server, Zap, AlertTriangle, CheckCircle, Clock, TrendingUp, ExternalLink, RefreshCw, ArrowUpRight, ArrowDownRight, GitBranch, Play, ChevronRight, Bell, X } from 'lucide-react'
import { Link } from 'react-router-dom'

const C={bg0:'#05080f',bg2:'#0d1425',bg3:'#111b30',border:'#1a2640',borderLit:'#243450',blue:'#3b8ef3',teal:'#00d4aa',purple:'#8b5cf6',amber:'#f59e0b',red:'#ef4444',green:'#22c55e',text0:'#f0f4ff',text1:'#8ba3c7',text2:'#3d5a7a',oracle:'#f97316',mysql:'#00b4d8',postgres:'#818cf8',mongodb:'#22c55e',redis:'#ef4444'}
const DB_COLORS:Record<string,string>={oracle:C.oracle,mysql:C.mysql,postgresql:C.postgres,mongodb:C.mongodb,redis:C.redis}
function fakeSpark(base:number,v:number,n=14){return Array.from({length:n},()=>Math.max(0,base+(Math.random()-0.5)*v*2))}
function Spark({data,color,h=36}:{data:number[],color:string,h?:number}){
  return(<ResponsiveContainer width="100%" height={h}><AreaChart data={data.map((v,i)=>({v,i}))}><defs><linearGradient id={`s${color.slice(1,5)}`} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity={0.25}/><stop offset="100%" stopColor={color} stopOpacity={0}/></linearGradient></defs><Area type="monotone" dataKey="v" stroke={color} strokeWidth={1.5} fill={`url(#s${color.slice(1,5)})`} dot={false}/></AreaChart></ResponsiveContainer>)
}
function Card({children,style={}}:any){return <div style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:12,padding:'18px 20px',...style}}>{children}</div>}
function Ttip({active,payload,label}:any){
  if(!active||!payload?.length)return null
  return(<div style={{background:C.bg3,border:`1px solid ${C.borderLit}`,borderRadius:8,padding:'8px 12px',fontSize:12}}><div style={{color:C.text2,marginBottom:4}}>{String(label).length>8?new Date(label).toLocaleTimeString('fr',{hour:'2-digit',minute:'2-digit'}):label}</div>{payload.map((p:any,i:number)=><div key={i} style={{color:p.color||C.text0,fontWeight:500}}>{p.name}: {typeof p.value==='number'?Math.round(p.value):p.value}</div>)}</div>)
}

export default function DashboardPage(){
  const{connections,setConnections}=useConnectionsStore()
  const[dashboard,setDashboard]=useState<any>(null)
  const[auditLogs,setAuditLogs]=useState<any[]>([])
  const[perf,setPerf]=useState<any[]>([])
  const[sysHealth,setSysHealth]=useState<any>(null)
  const[loading,setLoading]=useState(true)
  const[refreshAt,setRefreshAt]=useState(new Date())
  const[dismissed,setDismissed]=useState(new Set<number>())

  const GRAFANA=import.meta.env.VITE_GRAFANA_URL||'http://localhost:3001'
  const AIRFLOW=import.meta.env.VITE_AIRFLOW_URL||'http://localhost:8080'
  const PROM=import.meta.env.VITE_PROMETHEUS_URL||'http://localhost:9090'

  const load=useCallback(async()=>{
    const[d,a,h]=await Promise.allSettled([monitoringApi.dashboard(),auditApi.logs({days:1,limit:8}),healthApi.check()])
    if(d.status==='fulfilled'){setDashboard(d.value);if(d.value?.connectors){}}
    if(a.status==='fulfilled')setAuditLogs(a.value?.data?.slice(0,8)||[])
    if(h.status==='fulfilled')setSysHealth(h.value)
    const now=Date.now()
    setPerf(Array.from({length:24},(_,i)=>({t:new Date(now-(23-i)*5*60000).toISOString(),latency:Math.max(5,45+Math.sin(i*0.5)*30+Math.random()*20),queries:Math.floor(20+Math.random()*80),errors:Math.floor(Math.random()*5)})))
    setLoading(false);setRefreshAt(new Date())
  },[])

  useEffect(()=>{load()},[load])
  useEffect(()=>{const iv=setInterval(load,30000);return()=>clearInterval(iv)},[load])

  const s=dashboard?.summary||{}
  const connectors=dashboard?.connectors||[]
  const alerts=(dashboard?.alerts||[]).filter((_:any,i:number)=>!dismissed.has(i))
  const servers=dashboard?.servers||[]
  const slowQ=dashboard?.slow_queries||[]
  const critAlerts=s.critical_alerts||0
  const dbDist=Object.entries(connections.reduce((acc:any,c)=>{acc[c.db_type]=(acc[c.db_type]||0)+1;return acc},{})).map(([name,value])=>({name,value}))

  return(
    <div style={{minHeight:'100%',background:C.bg0,fontFamily:'DM Sans,sans-serif'}}>
      {critAlerts>0&&<div style={{background:`linear-gradient(90deg,${C.red}20,${C.red}10)`,borderBottom:`1px solid ${C.red}30`,padding:'10px 24px',display:'flex',alignItems:'center',gap:12}}>
        <AlertTriangle size={14} color={C.red}/><span style={{fontSize:12,color:C.red,fontWeight:600}}>{critAlerts} alerte(s) critique(s) — action requise</span>
        <div style={{flex:1}}/><Link to="/monitoring" style={{fontSize:11,color:C.red,textDecoration:'none',display:'flex',alignItems:'center',gap:4}}>Voir les alertes<ExternalLink size={10}/></Link>
      </div>}

      <div style={{padding:'22px 26px',display:'flex',flexDirection:'column',gap:18}}>
        <div style={{display:'flex',alignItems:'flex-start',justifyContent:'space-between'}}>
          <div>
            <h1 style={{fontSize:22,fontWeight:700,color:C.text0,fontFamily:'Syne,sans-serif',letterSpacing:'-0.5px',margin:0}}>Raxus Control Center</h1>
            <p style={{fontSize:11,color:C.text2,marginTop:4,fontFamily:'DM Mono,monospace'}}>{connections.length} sources · {servers.length} serveurs · màj {refreshAt.toLocaleTimeString('fr')}</p>
          </div>
          <div style={{display:'flex',alignItems:'center',gap:10}}>
            <div style={{display:'flex',alignItems:'center',gap:5,fontSize:10,color:C.green,fontFamily:'DM Mono,monospace',letterSpacing:'0.06em'}}>
              <span style={{width:6,height:6,borderRadius:'50%',background:C.green,boxShadow:`0 0 6px ${C.green}`,animation:'pdot 1.5s ease-in-out infinite'}}/>LIVE
            </div>
            <button onClick={load} disabled={loading} style={{padding:'7px 14px',borderRadius:8,border:`1px solid ${C.borderLit}`,background:C.bg3,color:C.text1,fontSize:12,cursor:'pointer',display:'flex',alignItems:'center',gap:6}}>
              <RefreshCw size={12} style={loading?{animation:'spin 0.8s linear infinite'}:{}}/>Actualiser
            </button>
          </div>
        </div>

        {/* KPIs */}
        <div style={{display:'grid',gridTemplateColumns:'repeat(5,1fr)',gap:10}}>
          {[
            {label:'Connexions actives',value:s.active_connectors||connections.filter(c=>c.enabled).length,icon:Database,color:C.blue,sub:`${connections.filter(c=>c.last_test_ok).length} OK`,spark:fakeSpark(s.active_connectors||3,1)},
            {label:'Score santé',value:`${connections.length>0?Math.round((connections.filter(c=>c.last_test_ok).length/connections.length)*100):0}`,unit:'%',icon:Activity,color:C.teal,sub:'DB performance',spark:fakeSpark(80,10)},
            {label:'Alertes actives',value:(dashboard?.alerts||[]).length,icon:Bell,color:critAlerts>0?C.red:(s.warning_alerts||0)>0?C.amber:C.green,sub:`${critAlerts} critiques`,spark:fakeSpark((dashboard?.alerts||[]).length,2)},
            {label:'Requêtes lentes',value:slowQ.length,icon:Clock,color:slowQ.length>5?C.amber:C.teal,sub:'Seuil > 1s',spark:fakeSpark(slowQ.length,3)},
            {label:'Serveurs en ligne',value:`${s.online_servers||0}/${servers.length}`,icon:Server,color:s.online_servers===servers.length&&servers.length>0?C.green:C.amber,sub:'Agents Raxus',spark:fakeSpark(s.online_servers||0,1)},
          ].map(({label,value,unit,icon:Icon,color,sub,spark})=>(
            <div key={label} style={{background:C.bg2,border:`1px solid ${C.border}`,borderRadius:12,padding:'16px 18px',display:'flex',flexDirection:'column',gap:8,position:'relative',overflow:'hidden'}}>
              <div style={{position:'absolute',inset:0,background:`radial-gradient(ellipse at top right,${color}08,transparent 60%)`,pointerEvents:'none'}}/>
              <div style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}>
                <span style={{fontSize:10,color:C.text2,textTransform:'uppercase',letterSpacing:'0.08em',fontFamily:'DM Mono,monospace'}}>{label}</span>
                <div style={{width:26,height:26,borderRadius:7,background:`${color}18`,border:`1px solid ${color}30`,display:'flex',alignItems:'center',justifyContent:'center'}}><Icon size={12} color={color}/></div>
              </div>
              <div style={{display:'flex',alignItems:'flex-end',gap:6}}><span style={{fontSize:26,fontWeight:700,color:C.text0,fontFamily:'Syne,sans-serif',lineHeight:1}}>{value}</span>{unit&&<span style={{fontSize:12,color:C.text2,marginBottom:1}}>{unit}</span>}</div>
              <div style={{fontSize:10,color:C.text2}}>{sub}</div>
              <Spark data={spark} color={color}/>
            </div>
          ))}
        </div>

        {/* Big chart + integrations */}
        <div style={{display:'grid',gridTemplateColumns:'1fr 300px',gap:14}}>
          <Card>
            <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:16}}>
              <div><div style={{fontSize:13,fontWeight:600,color:C.text0}}>Performance — 2h glissantes</div>
              <div style={{display:'flex',gap:14,marginTop:5}}>{[{l:'Latence ms',c:C.blue},{l:'Requêtes/min',c:C.teal},{l:'Erreurs',c:C.red}].map(({l,c})=>(
                <div key={l} style={{display:'flex',alignItems:'center',gap:5,fontSize:10,color:C.text2}}><span style={{width:16,height:2,background:c,borderRadius:1,display:'inline-block'}}/>{l}</div>
              ))}</div></div>
              <div style={{display:'flex',alignItems:'center',gap:5,fontSize:10,color:C.green,fontFamily:'DM Mono,monospace'}}><span style={{width:5,height:5,borderRadius:'50%',background:C.green,boxShadow:`0 0 5px ${C.green}`,animation:'pdot 1.5s ease-in-out infinite'}}/>LIVE</div>
            </div>
            <ResponsiveContainer width="100%" height={190}>
              <AreaChart data={perf}>
                <defs>{[{id:'la',c:C.blue},{id:'qu',c:C.teal},{id:'er',c:C.red}].map(({id,c})=>(
                  <linearGradient key={id} id={id} x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={c} stopOpacity={0.2}/><stop offset="95%" stopColor={c} stopOpacity={0}/></linearGradient>
                ))}</defs>
                <CartesianGrid strokeDasharray="3 3" stroke={C.border} vertical={false}/>
                <XAxis dataKey="t" tick={{fontSize:10,fill:C.text2}} tickFormatter={v=>new Date(v).toLocaleTimeString('fr',{hour:'2-digit',minute:'2-digit'})} axisLine={false} tickLine={false}/>
                <YAxis tick={{fontSize:10,fill:C.text2}} axisLine={false} tickLine={false} width={30}/>
                <Tooltip content={<Ttip/>}/>
                <Area type="monotone" dataKey="latency" name="Latence" stroke={C.blue} strokeWidth={2} fill="url(#la)" dot={false}/>
                <Area type="monotone" dataKey="queries" name="Requêtes/min" stroke={C.teal} strokeWidth={2} fill="url(#qu)" dot={false}/>
                <Area type="monotone" dataKey="errors" name="Erreurs" stroke={C.red} strokeWidth={1.5} fill="url(#er)" dot={false}/>
              </AreaChart>
            </ResponsiveContainer>
          </Card>
          <div style={{display:'flex',flexDirection:'column',gap:12}}>
            <Card>
              <div style={{fontSize:13,fontWeight:600,color:C.text0,marginBottom:12}}>Intégrations externes</div>
              {[{href:GRAFANA,label:'Grafana Dashboards',color:C.amber,icon:Activity},{href:PROM,label:'Prometheus Metrics',color:'#e67e22',icon:TrendingUp},{href:AIRFLOW,label:'Airflow DAGs',color:C.teal,icon:GitBranch},{href:`${GRAFANA}/d/raxus-db`,label:'DB Performance Board',color:C.blue,icon:Database}].map(({href,label,color,icon:Icon})=>(
                <a key={href} href={href} target="_blank" rel="noopener noreferrer" style={{display:'flex',alignItems:'center',gap:8,padding:'8px 10px',borderRadius:8,background:`${color}10`,border:`1px solid ${color}25`,color,fontSize:12,fontWeight:500,textDecoration:'none',marginBottom:6,transition:'all 0.15s'}} onMouseEnter={e=>(e.currentTarget.style.background=`${color}20`)} onMouseLeave={e=>(e.currentTarget.style.background=`${color}10`)}>
                  <Icon size={13}/>{label}<ExternalLink size={10} style={{marginLeft:'auto',opacity:0.6}}/>
                </a>
              ))}
            </Card>
            <Card style={{flex:1}}>
              <div style={{fontSize:12,fontWeight:600,color:C.text0,marginBottom:10}}>Répartition des bases</div>
              {dbDist.length>0?(
                <div style={{display:'flex',alignItems:'center',gap:10}}>
                  <PieChart width={80} height={80}><Pie data={dbDist} cx={35} cy={35} innerRadius={22} outerRadius={38} dataKey="value" paddingAngle={3}>{dbDist.map((e:any,i)=><Cell key={i} fill={DB_COLORS[e.name]||C.blue}/>)}</Pie></PieChart>
                  <div style={{flex:1}}>{dbDist.map((e:any)=>(<div key={e.name} style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:5}}><div style={{display:'flex',alignItems:'center',gap:6}}><span style={{width:6,height:6,borderRadius:'50%',background:DB_COLORS[e.name]||C.blue}}/><span style={{fontSize:11,color:C.text1}}>{e.name}</span></div><span style={{fontSize:11,fontWeight:600,color:DB_COLORS[e.name]||C.blue,fontFamily:'DM Mono,monospace'}}>{e.value as number}</span></div>))}</div>
                </div>
              ):<div style={{textAlign:'center',color:C.text2,fontSize:12,padding:'12px 0'}}>Aucune connexion</div>}
            </Card>
          </div>
        </div>

        {/* Row 3 */}
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 300px',gap:14}}>
          <Card>
            <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}><div style={{fontSize:13,fontWeight:600,color:C.text0}}>Bases de données</div><Link to="/connections" style={{fontSize:11,color:C.blue,textDecoration:'none',display:'flex',alignItems:'center',gap:3}}>Gérer<ChevronRight size={11}/></Link></div>
            {connections.length===0?(<div style={{textAlign:'center',color:C.text2,fontSize:12,padding:20}}><Database size={22} style={{margin:'0 auto 8px',opacity:0.3}}/><br/>Aucune connexion</div>):
            connections.slice(0,7).map((conn:any)=>{const dc=DB_COLORS[conn.db_type]||C.blue;return(
              <div key={conn.id} style={{display:'flex',alignItems:'center',gap:10,padding:'8px 10px',borderRadius:8,border:`1px solid ${C.border}`,background:C.bg3,marginBottom:5,cursor:'default',transition:'all 0.15s'}} onMouseEnter={e=>{e.currentTarget.style.borderColor=dc;e.currentTarget.style.background=`${dc}06`}} onMouseLeave={e=>{e.currentTarget.style.borderColor=C.border;e.currentTarget.style.background=C.bg3}}>
                <div style={{width:28,height:28,borderRadius:7,background:`${dc}15`,border:`1px solid ${dc}30`,display:'flex',alignItems:'center',justifyContent:'center',flexShrink:0}}><Database size={13} color={dc}/></div>
                <div style={{flex:1,minWidth:0}}><div style={{fontSize:12,fontWeight:500,color:C.text0,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{conn.name}</div><div style={{fontSize:10,color:C.text2}}>{conn.db_type}·{conn.host}</div></div>
                {conn.last_test_ms!=null&&<span style={{fontSize:10,color:conn.last_test_ok?C.teal:C.red,fontFamily:'DM Mono,monospace',flexShrink:0}}>{conn.last_test_ok?`${conn.last_test_ms}ms`:'ERR'}</span>}
                <span style={{width:7,height:7,borderRadius:'50%',flexShrink:0,background:conn.last_test_ok===true?C.green:conn.last_test_ok===false?C.red:C.text2,boxShadow:conn.last_test_ok===true?`0 0 6px ${C.green}`:undefined}}/>
              </div>
            )})}
          </Card>

          <Card>
            <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}><div style={{fontSize:13,fontWeight:600,color:C.text0}}>Alertes récentes</div><Link to="/monitoring" style={{fontSize:11,color:C.blue,textDecoration:'none',display:'flex',alignItems:'center',gap:3}}>Monitoring<ChevronRight size={11}/></Link></div>
            {alerts.length===0?(<div style={{display:'flex',flexDirection:'column',alignItems:'center',gap:8,padding:20,color:C.teal}}><CheckCircle size={28}/><span style={{fontSize:12}}>Aucune alerte</span></div>):
            alerts.slice(0,6).map((alert:any,i:number)=>{const col=alert.severity==='critical'?C.red:C.amber;return(
              <div key={i} style={{display:'flex',alignItems:'flex-start',gap:9,padding:'8px 10px',borderRadius:8,background:`${col}08`,border:`1px solid ${col}20`,marginBottom:5}}>
                <AlertTriangle size={13} color={col} style={{marginTop:1,flexShrink:0}}/>
                <div style={{flex:1,minWidth:0}}><div style={{fontSize:12,color:C.text0,fontWeight:500,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{alert.rule_name||'Alerte'}</div><div style={{fontSize:10,color:C.text2,marginTop:2}}>{alert.connector_id||alert.server_id||'—'}·{alert.fired_at?new Date(alert.fired_at).toLocaleTimeString('fr'):'now'}</div></div>
                <div style={{display:'flex',flexDirection:'column',alignItems:'flex-end',gap:4}}>
                  <span style={{fontSize:9,fontWeight:700,padding:'2px 6px',borderRadius:4,background:`${col}20`,color:col,textTransform:'uppercase'}}>{alert.severity}</span>
                  <button onClick={()=>setDismissed(s=>new Set([...s,i]))} style={{background:'none',border:'none',cursor:'pointer',color:C.text2,padding:0}}><X size={10}/></button>
                </div>
              </div>
            )})}
          </Card>

          <Card>
            <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}><div style={{fontSize:13,fontWeight:600,color:C.text0}}>Charge serveurs</div><Link to="/servers" style={{fontSize:11,color:C.blue,textDecoration:'none',display:'flex',alignItems:'center',gap:3}}>Serveurs<ChevronRight size={11}/></Link></div>
            {servers.length===0?(<div style={{textAlign:'center',color:C.text2,fontSize:12,padding:20}}><Server size={22} style={{margin:'0 auto 8px',opacity:0.3}}/><br/>Aucun agent</div>):
            servers.slice(0,4).map((srv:any)=>{const cpu=Math.round(20+Math.random()*60);const mem=Math.round(30+Math.random()*50);const cc=cpu>80?C.red:cpu>60?C.amber:C.teal;const mc=mem>80?C.red:mem>60?C.amber:C.blue;return(
              <div key={srv.id} style={{marginBottom:14}}>
                <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:6}}><div style={{display:'flex',alignItems:'center',gap:6}}><span style={{width:6,height:6,borderRadius:'50%',background:srv.status==='online'?C.green:C.red}}/><span style={{fontSize:11,color:C.text1,fontWeight:500}}>{srv.hostname||srv.id}</span></div></div>
                {[{l:'CPU',p:cpu,c:cc},{l:'RAM',p:mem,c:mc}].map(({l,p,c})=>(<div key={l} style={{marginBottom:5}}><div style={{display:'flex',justifyContent:'space-between',marginBottom:3}}><span style={{fontSize:10,color:C.text2}}>{l}</span><span style={{fontSize:10,color:c,fontFamily:'DM Mono,monospace',fontWeight:600}}>{p}%</span></div><div style={{height:4,background:C.bg3,borderRadius:2,overflow:'hidden'}}><div style={{height:'100%',width:`${p}%`,background:c,borderRadius:2,boxShadow:`0 0 6px ${c}60`,transition:'width 0.5s ease'}}/></div></div>))}
              </div>
            )})}
          </Card>
        </div>

        {/* Row 4: slow queries + audit */}
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:14}}>
          <Card>
            <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}><div style={{fontSize:13,fontWeight:600,color:C.text0}}>Requêtes lentes</div><Link to="/editor" style={{fontSize:11,color:C.blue,textDecoration:'none',display:'flex',alignItems:'center',gap:3}}>SQL Editor<ChevronRight size={11}/></Link></div>
            {slowQ.length===0?(<div style={{display:'flex',alignItems:'center',gap:10,color:C.teal,fontSize:12,padding:'12px 0'}}><CheckCircle size={15}/>Aucune requête lente</div>):(
              <div style={{overflowX:'auto'}}>
                <table style={{width:'100%',borderCollapse:'collapse',fontSize:12}}>
                  <thead><tr>{['SQL','Connexion','Durée','Statut'].map(h=>(<th key={h} style={{textAlign:'left',padding:'6px 8px',fontSize:10,color:C.text2,fontWeight:500,textTransform:'uppercase',letterSpacing:'0.06em',borderBottom:`1px solid ${C.border}`,whiteSpace:'nowrap'}}>{h}</th>))}</tr></thead>
                  <tbody>{slowQ.map((q:any,i:number)=>(<tr key={i} style={{borderBottom:`1px solid ${C.border}`,transition:'background 0.1s'}} onMouseEnter={e=>(e.currentTarget.style.background=C.bg3)} onMouseLeave={e=>(e.currentTarget.style.background='transparent')}><td style={{padding:'7px 8px',maxWidth:180,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',fontFamily:'DM Mono,monospace',fontSize:10,color:C.text1}}>{q.sql_text?.slice(0,55)}</td><td style={{padding:'7px 8px',color:C.text2,fontSize:10}}>{q.connection_id?.slice(0,8)}</td><td style={{padding:'7px 8px',fontFamily:'DM Mono,monospace',fontWeight:600,color:q.duration_ms>5000?C.red:C.amber}}>{q.duration_ms}ms</td><td style={{padding:'7px 8px'}}><span style={{fontSize:9,padding:'2px 6px',borderRadius:4,fontWeight:700,textTransform:'uppercase',background:q.status==='success'?`${C.green}18`:`${C.red}18`,color:q.status==='success'?C.green:C.red}}>{q.status}</span></td></tr>))}</tbody>
                </table>
              </div>
            )}
          </Card>
          <Card>
            <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}><div style={{fontSize:13,fontWeight:600,color:C.text0}}>Activité d'audit</div><Link to="/audit" style={{fontSize:11,color:C.blue,textDecoration:'none',display:'flex',alignItems:'center',gap:3}}>Audit<ChevronRight size={11}/></Link></div>
            {auditLogs.length===0?(<div style={{color:C.text2,fontSize:12,padding:'12px 0'}}>Aucune activité récente</div>):
            auditLogs.map((log:any,i:number)=>{const score=log.risk_score||0;const col=score>=70?C.red:score>=40?C.amber:C.teal;const rc=log.result==='success'?C.teal:log.result==='blocked'?C.red:C.amber;return(
              <div key={i} style={{display:'flex',alignItems:'center',gap:8,padding:'7px 0',borderBottom:`1px solid ${C.border}`}}>
                <div style={{width:24,height:24,borderRadius:6,background:`${col}15`,border:`1px solid ${col}25`,display:'flex',alignItems:'center',justifyContent:'center',flexShrink:0}}><Shield size={11} color={col}/></div>
                <div style={{flex:1,minWidth:0}}><div style={{fontSize:11,color:C.text1,fontWeight:500,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}><span style={{color:C.text0}}>{log.username||'system'}</span>·{log.action}</div><div style={{fontSize:10,color:C.text2}}>{log.request_ip||'internal'}·{log.created_at?new Date(log.created_at).toLocaleTimeString('fr'):'—'}</div></div>
                <div style={{display:'flex',flexDirection:'column',alignItems:'flex-end',gap:3}}><span style={{fontSize:9,padding:'2px 6px',borderRadius:4,background:`${rc}15`,color:rc,fontWeight:700,textTransform:'uppercase'}}>{log.result}</span>{score>0&&<span style={{fontSize:9,color:col,fontFamily:'DM Mono,monospace',fontWeight:700}}>R:{score}</span>}</div>
              </div>
            )})}
          </Card>
        </div>

        {/* Row 5: bar chart + quick nav */}
        <div style={{display:'grid',gridTemplateColumns:'1fr 280px',gap:14}}>
          <Card>
            <div style={{fontSize:13,fontWeight:600,color:C.text0,marginBottom:14}}>Volume de requêtes</div>
            <ResponsiveContainer width="100%" height={150}>
              <BarChart data={perf.slice(-16)} barCategoryGap="30%">
                <CartesianGrid strokeDasharray="3 3" stroke={C.border} vertical={false}/>
                <XAxis dataKey="t" tick={{fontSize:10,fill:C.text2}} tickFormatter={v=>new Date(v).toLocaleTimeString('fr',{hour:'2-digit',minute:'2-digit'})} axisLine={false} tickLine={false}/>
                <YAxis tick={{fontSize:10,fill:C.text2}} axisLine={false} tickLine={false} width={28}/>
                <Tooltip content={<Ttip/>}/>
                <Bar dataKey="queries" name="Requêtes/min" fill={C.blue} radius={[3,3,0,0]} opacity={0.85}/>
                <Bar dataKey="errors" name="Erreurs" fill={C.red} radius={[3,3,0,0]} opacity={0.75}/>
              </BarChart>
            </ResponsiveContainer>
          </Card>
          <Card>
            <div style={{fontSize:13,fontWeight:600,color:C.text0,marginBottom:12}}>Navigation rapide</div>
            {[{to:'/editor',icon:Zap,label:'SQL Editor',sub:'Exécuter des requêtes',color:C.blue},{to:'/connections',icon:Database,label:'Connexions',sub:'Gérer les sources',color:C.teal},{to:'/chat',icon:Activity,label:'Chat IA',sub:'Assistant DBA',color:C.purple},{to:'/audit',icon:Shield,label:'Audit',sub:'Logs & sécurité',color:C.amber},{to:'/tasks',icon:Play,label:'Tâches',sub:'Automatisation',color:C.green},{to:'/servers',icon:Server,label:'Serveurs',sub:`${s.online_servers||0} actif(s)`,color:C.oracle||'#f97316'}].map(({to,icon:Icon,label,sub,color})=>(
              <Link key={to} to={to} style={{display:'flex',alignItems:'center',gap:10,padding:'8px 10px',borderRadius:8,background:C.bg3,border:`1px solid ${C.border}`,textDecoration:'none',marginBottom:5,transition:'all 0.15s'}} onMouseEnter={e=>{e.currentTarget.style.borderColor=color;e.currentTarget.style.background=`${color}08`}} onMouseLeave={e=>{e.currentTarget.style.borderColor=C.border;e.currentTarget.style.background=C.bg3}}>
                <div style={{width:28,height:28,borderRadius:7,background:`${color}15`,display:'flex',alignItems:'center',justifyContent:'center',flexShrink:0}}><Icon size={13} color={color}/></div>
                <div style={{flex:1,minWidth:0}}><div style={{fontSize:12,fontWeight:500,color:C.text0}}>{label}</div><div style={{fontSize:10,color:C.text2,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{sub}</div></div>
                <ChevronRight size={11} color={C.text2}/>
              </Link>
            ))}
          </Card>
        </div>

        {/* Status bar */}
        <div style={{display:'flex',alignItems:'center',gap:20,padding:'10px 16px',borderRadius:10,background:C.bg2,border:`1px solid ${C.border}`,fontSize:11,color:C.text2}}>
          {[{label:'API Backend',ok:sysHealth?.status==='healthy'},{label:'MySQL App DB',ok:sysHealth?.services?.mysql_app==='up'},{label:'Redis',ok:sysHealth?.services?.redis==='up'}].map(({label,ok})=>(
            <div key={label} style={{display:'flex',alignItems:'center',gap:6}}><span style={{width:6,height:6,borderRadius:'50%',background:ok?C.green:C.text2,boxShadow:ok?`0 0 6px ${C.green}`:undefined}}/>{label}</div>
          ))}
          <div style={{flex:1}}/>
          <span style={{fontFamily:'DM Mono,monospace'}}>Raxus v1.0·{connections.length} DB·{servers.length} agents·auto-refresh 30s</span>
        </div>
      </div>
      <style>{`@keyframes pdot{0%,100%{opacity:1}50%{opacity:0.3}}@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  )
}
