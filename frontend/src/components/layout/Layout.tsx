import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuthStore, useAppStore, useConnectionsStore } from '../../stores'
import { connectionsApi } from '../../lib/api'
import { useEffect } from 'react'
import toast from 'react-hot-toast'
import { LayoutDashboard, Database, Code2, Activity, Shield, ListTodo, MessageSquare, Users, Server, LogOut, Bell, ChevronRight, FolderTree } from 'lucide-react'

const C={bg1:'#080d18',bg2:'#0d1425',border:'#1a2640',blue:'#3b8ef3',text0:'#f0f4ff',text1:'#8ba3c7',text2:'#3d5a7a',red:'#ef4444'}
const ROLE_COLORS:Record<string,string>={admin:'#f97316',dba:'#3b8ef3',analyst:'#22c55e',viewer:'#8ba3c7'}
const DB_COLORS:Record<string,string>={oracle:'#f97316',mysql:'#00b4d8',postgresql:'#818cf8',mongodb:'#22c55e',redis:'#ef4444'}

const NAV=[
  {to:'/dashboard',icon:LayoutDashboard,label:'Dashboard'},
  {to:'/connections',icon:Database,label:'Connexions'},
  {to:'/editor',icon:Code2,label:'SQL Editor'},
  {to:'/schema',icon:FolderTree,label:'Schema Browser'},
  {to:'/monitoring',icon:Activity,label:'Monitoring'},
  {to:'/audit',icon:Shield,label:'Audit'},
  {to:'/tasks',icon:ListTodo,label:'Tâches'},
  {to:'/chat',icon:MessageSquare,label:'Chat IA'},
  {to:'/servers',icon:Server,label:'Serveurs'},
  {to:'/users',icon:Users,label:'Utilisateurs',adminOnly:true},
]

export default function Layout(){
  const {user,logout,can}=useAuthStore()
  const {sidebarOpen,unreadCount}=useAppStore()
  const {setConnections}=useConnectionsStore()
  const navigate=useNavigate()
  const roleColor=ROLE_COLORS[user?.role||'viewer']

  useEffect(()=>{connectionsApi.list().then(setConnections).catch(()=>toast.error('Erreur connexions'))},[])

  const handleLogout=()=>{logout();navigate('/login');toast.success('Déconnecté')}

  return (
    <div style={{display:'flex',height:'100vh',overflow:'hidden',background:'#05080f'}}>
      <aside style={{width:sidebarOpen?220:58,background:C.bg1,borderRight:`1px solid ${C.border}`,display:'flex',flexDirection:'column',transition:'width 0.2s',flexShrink:0,overflow:'hidden'}}>
        <div style={{padding:'18px 16px 14px',borderBottom:`1px solid ${C.border}`}}>
          <div style={{fontSize:18,fontWeight:700,color:C.blue,fontFamily:'Syne,sans-serif',letterSpacing:'-0.5px'}}>{sidebarOpen?'Raxus':'R'}</div>
          {sidebarOpen&&<div style={{fontSize:10,color:C.text2,marginTop:2,letterSpacing:'0.08em',textTransform:'uppercase'}}>Data Platform v1.0</div>}
        </div>
        <nav style={{flex:1,padding:'10px 8px',display:'flex',flexDirection:'column',gap:2,overflowY:'auto'}}>
          {NAV.map(({to,icon:Icon,label,adminOnly})=>{
            if(adminOnly&&!can('admin'))return null
            return (
              <NavLink key={to} to={to}
                style={({isActive})=>({
                  display:'flex',alignItems:'center',gap:10,
                  padding:sidebarOpen?'9px 12px':'9px 0',
                  justifyContent:sidebarOpen?'flex-start':'center',
                  borderRadius:8,textDecoration:'none',border:'1px solid transparent',
                  color:isActive?C.blue:C.text2,
                  background:isActive?'rgba(59,142,243,0.12)':'transparent',
                  borderColor:isActive?'rgba(59,142,243,0.2)':'transparent',
                  fontSize:13,fontWeight:isActive?500:400,transition:'all 0.12s',
                })}
              >
                <Icon size={15} style={{flexShrink:0}}/>
                {sidebarOpen&&<span style={{whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>{label}</span>}
              </NavLink>
            )
          })}
        </nav>
        <div style={{padding:'10px 8px',borderTop:`1px solid ${C.border}`}}>
          {sidebarOpen?(
            <div style={{display:'flex',alignItems:'center',gap:8,padding:'8px 10px',borderRadius:8,background:C.bg2}}>
              <div style={{width:28,height:28,borderRadius:'50%',background:`${roleColor}20`,border:`2px solid ${roleColor}50`,display:'flex',alignItems:'center',justifyContent:'center',fontSize:11,fontWeight:700,color:roleColor,flexShrink:0}}>
                {user?.username?.[0]?.toUpperCase()||'U'}
              </div>
              <div style={{flex:1,minWidth:0}}>
                <div style={{fontSize:12,fontWeight:500,color:C.text0,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{user?.username}</div>
                <div style={{fontSize:10,color:roleColor}}>{user?.role}</div>
              </div>
              <button onClick={handleLogout} style={{background:'none',border:'none',cursor:'pointer',color:C.text2,padding:4,display:'flex'}}><LogOut size={13}/></button>
            </div>
          ):(
            <button onClick={handleLogout} style={{width:'100%',padding:'8px 0',background:'none',border:`1px solid ${C.border}`,borderRadius:7,cursor:'pointer',color:C.text2,display:'flex',justifyContent:'center'}}><LogOut size={13}/></button>
          )}
        </div>
      </aside>

      <div style={{flex:1,display:'flex',flexDirection:'column',overflow:'hidden'}}>
        <header style={{height:50,background:C.bg1,borderBottom:`1px solid ${C.border}`,display:'flex',alignItems:'center',paddingInline:16,gap:12,flexShrink:0}}>
          <button onClick={()=>useAppStore.getState().setSidebar(!sidebarOpen)} style={{background:'none',border:`1px solid ${C.border}`,borderRadius:6,cursor:'pointer',color:C.text2,padding:'5px 7px',display:'flex'}}>
            <ChevronRight size={13} style={{transform:sidebarOpen?'rotate(180deg)':'none',transition:'transform 0.2s'}}/>
          </button>
          <div style={{flex:1}}/>
          <DBStatusBar/>
          <div style={{width:1,height:20,background:C.border}}/>
          <div style={{display:'flex',alignItems:'center',gap:5,fontSize:10,color:'#22c55e',fontFamily:'DM Mono,monospace',letterSpacing:'0.06em'}}>
            <span style={{width:6,height:6,borderRadius:'50%',background:'#22c55e',boxShadow:'0 0 6px #22c55e',animation:'pdot 1.5s ease-in-out infinite'}}/>LIVE
          </div>
        </header>
        <main style={{flex:1,overflow:'auto',background:'#05080f'}}>
          <Outlet/>
        </main>
      </div>
      <style>{`@keyframes pdot{0%,100%{opacity:1}50%{opacity:0.3}}`}</style>
    </div>
  )
}

function DBStatusBar(){
  const{connections,activeConnectionId,setActive}=useConnectionsStore()
  const active=connections.find(c=>c.id===activeConnectionId)
  if(!connections.length)return <span style={{fontSize:11,color:'#3d5a7a',fontFamily:'DM Mono,monospace'}}>0 connexion</span>
  return (
    <div style={{display:'flex',alignItems:'center',gap:8}}>
      <span style={{fontSize:11,color:'#3d5a7a'}}>DB :</span>
      <select value={activeConnectionId||''} onChange={e=>setActive(e.target.value||null)}
        style={{padding:'4px 10px',fontSize:11,borderRadius:6,background:'#0d1425',border:'1px solid #1a2640',color:'#8ba3c7',width:'auto'}}>
        <option value="">— Choisir —</option>
        {connections.filter(c=>c.enabled).map(c=><option key={c.id} value={c.id}>{c.name} ({c.db_type})</option>)}
      </select>
      {active&&<span style={{width:6,height:6,borderRadius:'50%',flexShrink:0,background:active.last_test_ok?'#22c55e':'#3d5a7a',boxShadow:active.last_test_ok?'0 0 5px #22c55e':'none'}}/>}
    </div>
  )
}
