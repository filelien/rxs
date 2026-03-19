import { useEffect, useRef, useState } from 'react'
import { chatApi } from '../lib/api'
import { useConnectionsStore } from '../stores'
import { Send, Plus, MessageSquare, Database, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'

const SUGGESTIONS = [
  'Liste toutes les tables', 'Montre les requêtes lentes',
  'Vérifie la santé de la base', 'Affiche les sessions actives',
  'Suggère des index', 'Explique la dernière requête lente',
]

function MsgBubble({ msg }: { msg: any }) {
  const isUser = msg.role === 'user'
  return (
    <div style={{ display: 'flex', justifyContent: isUser ? 'flex-end' : 'flex-start', marginBottom: 14 }}>
      {!isUser && (
        <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'var(--accent-glow)', border: '1px solid rgba(59,130,246,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginRight: 10, flexShrink: 0, fontSize: 12, color: 'var(--accent)', fontWeight: 700 }}>R</div>
      )}
      <div style={{
        maxWidth: '75%',
        background: isUser ? 'var(--accent)' : 'var(--bg-raised)',
        border: `1px solid ${isUser ? 'transparent' : 'var(--border)'}`,
        borderRadius: isUser ? '14px 14px 4px 14px' : '4px 14px 14px 14px',
        padding: '10px 14px', fontSize: 13, lineHeight: 1.6,
        color: isUser ? 'white' : 'var(--text-primary)',
      }}>
        <p style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</p>
        {msg.sql_generated && (
          <div style={{ marginTop: 10, background: 'var(--bg-overlay)', borderRadius: 7, padding: '8px 12px', fontFamily: 'DM Mono', fontSize: 11, color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
            {msg.sql_generated}
          </div>
        )}
        {msg.duration_ms > 0 && (
          <div style={{ fontSize: 10, color: isUser ? 'rgba(255,255,255,0.6)' : 'var(--text-dim)', marginTop: 6 }}>{msg.duration_ms}ms</div>
        )}
      </div>
    </div>
  )
}

export default function ChatPage() {
  const { connections, activeConnectionId } = useConnectionsStore()
  const [sessions, setSessions] = useState<any[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<any[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [selectedConn, setSelectedConn] = useState(activeConnectionId || '')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => { loadSessions() }, [])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const loadSessions = async () => {
    try { const s = await chatApi.sessions(); setSessions(s || []) } catch {}
  }

  const newSession = async () => {
    const res = await chatApi.newSession()
    setSessionId(res.session_id)
    setMessages([])
    await loadSessions()
  }

  const selectSession = async (id: string) => {
    setSessionId(id)
    try {
      const hist = await chatApi.history(id)
      setMessages(Array.isArray(hist) ? hist : [])
    } catch { setMessages([]) }
  }

  const send = async (text?: string) => {
    const msg = text || input.trim()
    if (!msg) return
    if (!sessionId) { const res = await chatApi.newSession(); setSessionId(res.session_id); await loadSessions() }
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setLoading(true)
    try {
      const res = await chatApi.send(sessionId!, msg, selectedConn || undefined)
      setMessages(prev => [...prev, {
        role: 'assistant', content: res.message,
        sql_generated: res.sql, duration_ms: res.execution_time_ms,
      }])
    } catch { toast.error('Erreur du chatbot') }
    finally { setLoading(false) }
  }

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 100px)', gap: 0 }}>
      {/* Sidebar sessions */}
      <div style={{ width: 220, borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
        <div style={{ padding: '14px 12px', borderBottom: '1px solid var(--border)' }}>
          <button className="btn btn-primary btn-sm" onClick={newSession} style={{ width: '100%', justifyContent: 'center' }}>
            <Plus size={13} /> Nouvelle conversation
          </button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
          {sessions.map(s => (
            <button key={s.id} onClick={() => selectSession(s.id)} style={{
              width: '100%', padding: '8px 10px', borderRadius: 7, border: 'none',
              background: sessionId === s.id ? 'var(--accent-glow)' : 'transparent',
              color: sessionId === s.id ? 'var(--accent)' : 'var(--text-muted)',
              cursor: 'pointer', fontSize: 12, textAlign: 'left',
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <MessageSquare size={12} />
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.title || 'Conversation'}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Chat area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Toolbar */}
        <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
          <Database size={14} color="var(--text-dim)" />
          <select value={selectedConn} onChange={e => setSelectedConn(e.target.value)} style={{ width: 'auto', padding: '5px 10px', fontSize: 12 }}>
            <option value="">— Connexion (optionnel) —</option>
            {connections.filter(c => c.enabled).map(c => <option key={c.id} value={c.id}>{c.name} ({c.db_type})</option>)}
          </select>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', paddingTop: 40 }}>
              <div style={{ fontSize: 28, marginBottom: 10 }}>🤖</div>
              <h3 className="font-display" style={{ fontSize: 16, color: 'var(--text-primary)', marginBottom: 8 }}>Raxus AI — Assistant DBA</h3>
              <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 24 }}>Interrogez vos bases en langage naturel</p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center' }}>
                {SUGGESTIONS.map(s => (
                  <button key={s} onClick={() => send(s)} className="btn btn-ghost btn-sm">{s}</button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => <MsgBubble key={i} msg={m} />)}
          {loading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text-muted)', fontSize: 13 }}>
              <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'var(--accent-glow)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, color: 'var(--accent)', fontWeight: 700 }}>R</div>
              <Loader2 size={14} className="spinner" />
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div style={{ padding: '12px 16px', borderTop: '1px solid var(--border)' }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
              placeholder="Posez votre question… (Entrée pour envoyer, Shift+Entrée pour nouvelle ligne)"
              rows={2}
              style={{ flex: 1, resize: 'none', fontSize: 13 }}
            />
            <button className="btn btn-primary" onClick={() => send()} disabled={!input.trim() || loading} style={{ height: 62, width: 50, justifyContent: 'center', flexShrink: 0 }}>
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
