import { useState, useEffect, useRef } from 'react'
import { useEditorStore, useConnectionsStore } from '../stores'
import { queryApi } from '../lib/api'
import toast from 'react-hot-toast'
import { Play, Plus, X, Save, Clock, Download, ChevronDown, Database } from 'lucide-react'

function SqlTextarea({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const ref = useRef<HTMLTextAreaElement>(null)

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      const event = new CustomEvent('run-query')
      window.dispatchEvent(event)
    }
    if (e.key === 'Tab') {
      e.preventDefault()
      const ta = ref.current!
      const start = ta.selectionStart
      const end = ta.selectionEnd
      const newVal = value.substring(0, start) + '  ' + value.substring(end)
      onChange(newVal)
      setTimeout(() => { ta.selectionStart = ta.selectionEnd = start + 2 }, 0)
    }
  }

  return (
    <textarea
      ref={ref}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={handleKeyDown}
      spellCheck={false}
      placeholder="-- Écrivez votre requête SQL ici
-- Ctrl+Enter pour exécuter

SELECT * FROM users LIMIT 10;"
      style={{
        flex: 1, width: '100%', resize: 'none', border: 'none', outline: 'none',
        background: 'transparent', color: 'var(--text-primary)',
        fontFamily: 'DM Mono, monospace', fontSize: 13, lineHeight: 1.7,
        padding: '16px', caretColor: 'var(--accent)',
      }}
    />
  )
}

function ResultTable({ rows, columns, duration_ms, row_count, truncated }: any) {
  const [copied, setCopied] = useState(false)

  const exportCsv = () => {
    const header = columns.map((c: any) => c.name).join(',')
    const body = rows.map((r: any) => columns.map((c: any) => JSON.stringify(r[c.name] ?? '')).join(',')).join('\n')
    const blob = new Blob([header + '\n' + body], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'raxus-export.csv'; a.click()
    URL.revokeObjectURL(url)
    toast.success('Export CSV téléchargé')
  }

  if (!rows || rows.length === 0) return (
    <div style={{ padding: 24, textAlign: 'center', color: 'var(--text-dim)', fontSize: 13 }}>
      Aucun résultat
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 14px', borderBottom: '1px solid var(--border)', fontSize: 12, color: 'var(--text-muted)' }}>
        <span><span style={{ color: 'var(--success)' }}>{row_count}</span> ligne{row_count > 1 ? 's' : ''}</span>
        <span style={{ color: 'var(--text-dim)' }}>·</span>
        <span>{duration_ms}ms</span>
        {truncated && <span className="badge badge-warning">Tronqué à 10 000</span>}
        <div style={{ flex: 1 }} />
        <button className="btn btn-ghost btn-sm" onClick={exportCsv}><Download size={12} /> CSV</button>
      </div>
      <div className="result-table-wrap" style={{ flex: 1 }}>
        <table className="result-table">
          <thead>
            <tr>{columns.map((c: any) => <th key={c.name}>{c.name}</th>)}</tr>
          </thead>
          <tbody>
            {rows.slice(0, 500).map((row: any, i: number) => (
              <tr key={i}>
                {columns.map((c: any) => (
                  <td key={c.name} className={row[c.name] === null ? 'null' : ''} onClick={() => { navigator.clipboard.writeText(String(row[c.name] ?? '')); setCopied(true); setTimeout(() => setCopied(false), 800) }}>
                    {row[c.name] === null ? 'NULL' : String(row[c.name]).slice(0, 200)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default function QueryEditorPage() {
  const { tabs, activeTabId, addTab, closeTab, updateTab, setActiveTab, getActiveTab } = useEditorStore()
  const { connections, activeConnectionId, setActive } = useConnectionsStore()
  const [saving, setSaving] = useState(false)
  const [showSave, setShowSave] = useState(false)
  const [saveName, setSaveName] = useState('')

  const activeTab = getActiveTab()

  useEffect(() => {
    if (tabs.length === 0) addTab(activeConnectionId || '')
  }, [])

  useEffect(() => {
    const handler = () => activeTab && runQuery()
    window.addEventListener('run-query', handler)
    return () => window.removeEventListener('run-query', handler)
  }, [activeTab])

  const runQuery = async () => {
    const tab = getActiveTab()
    if (!tab || !tab.sql.trim()) return
    const connId = tab.connector_id || activeConnectionId
    if (!connId) return toast.error('Sélectionnez une base de données')
    updateTab(tab.id, { status: 'running', error: null, result: null })
    try {
      const res = await queryApi.execute(tab.sql, connId)
      if (res.status === 'blocked') {
        updateTab(tab.id, { status: 'error', error: res.error })
        toast.error(res.error)
      } else if (res.status === 'error' || res.status === 'timeout') {
        updateTab(tab.id, { status: 'error', error: res.error, duration_ms: res.duration_ms })
        toast.error(res.error || 'Erreur')
      } else {
        updateTab(tab.id, { status: 'success', result: res, duration_ms: res.duration_ms })
        toast.success(`${res.row_count} ligne${res.row_count > 1 ? 's' : ''} — ${res.duration_ms}ms`)
      }
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Erreur réseau'
      updateTab(tab.id, { status: 'error', error: msg })
      toast.error(msg)
    }
  }

  const handleSave = async () => {
    if (!activeTab || !saveName) return
    const connId = activeTab.connector_id || activeConnectionId || ''
    setSaving(true)
    try {
      await queryApi.save(saveName, activeTab.sql, connId)
      setShowSave(false)
      setSaveName('')
      toast.success('Requête sauvegardée')
    } catch { toast.error('Erreur lors de la sauvegarde') }
    finally { setSaving(false) }
  }

  return (
    <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 100px)' }}>
      {/* Tabs */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 0, borderBottom: '1px solid var(--border)', background: 'var(--bg-surface)', paddingLeft: 4 }}>
        <div style={{ display: 'flex', flex: 1, overflowX: 'auto' }}>
          {tabs.map(tab => (
            <div
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '9px 14px', cursor: 'pointer', whiteSpace: 'nowrap',
                borderBottom: `2px solid ${activeTabId === tab.id ? 'var(--accent)' : 'transparent'}`,
                color: activeTabId === tab.id ? 'var(--text-primary)' : 'var(--text-muted)',
                fontSize: 13, minWidth: 100, maxWidth: 200,
              }}
            >
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>{tab.title}</span>
              {tab.status === 'running' && <span className="spinner" />}
              {tab.status === 'error' && <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--danger)', flexShrink: 0 }} />}
              {tab.status === 'success' && <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--success)', flexShrink: 0 }} />}
              {tabs.length > 1 && (
                <button onClick={(e) => { e.stopPropagation(); closeTab(tab.id) }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-dim)', padding: 2, display: 'flex' }}>
                  <X size={11} />
                </button>
              )}
            </div>
          ))}
        </div>
        <button className="btn-icon" style={{ margin: '0 8px', flexShrink: 0 }} onClick={() => addTab(activeConnectionId || '')} title="Nouvel onglet">
          <Plus size={14} />
        </button>
      </div>

      {activeTab && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {/* Toolbar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', borderBottom: '1px solid var(--border)', background: 'var(--bg-surface)' }}>
            <select
              value={activeTab.connector_id || activeConnectionId || ''}
              onChange={(e) => { updateTab(activeTab.id, { connector_id: e.target.value }); setActive(e.target.value) }}
              style={{ width: 'auto', padding: '5px 10px', fontSize: 12 }}
            >
              <option value="">— Sélectionner une base —</option>
              {connections.filter(c => c.enabled).map(c => (
                <option key={c.id} value={c.id}>{c.name} ({c.db_type})</option>
              ))}
            </select>
            <div style={{ flex: 1 }} />
            <button className="btn btn-ghost btn-sm" onClick={() => setShowSave(true)}>
              <Save size={13} /> Sauvegarder
            </button>
            <button
              className="btn btn-primary btn-sm"
              onClick={runQuery}
              disabled={activeTab.status === 'running'}
              title="Ctrl+Enter"
            >
              {activeTab.status === 'running' ? <span className="spinner" /> : <Play size={13} />}
              {activeTab.status === 'running' ? 'Exécution…' : 'Exécuter'}
            </button>
          </div>

          {/* Editor + Results split */}
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {/* Editor */}
            <div style={{
              flex: activeTab.result ? '0 0 45%' : 1,
              borderBottom: '1px solid var(--border)',
              background: 'var(--bg-surface)',
              display: 'flex', flexDirection: 'column', overflow: 'hidden',
            }}>
              <SqlTextarea
                value={activeTab.sql}
                onChange={(sql) => updateTab(activeTab.id, { sql })}
              />
            </div>

            {/* Results */}
            {activeTab.result && (
              <div style={{ flex: 1, overflow: 'hidden', background: 'var(--bg-base)' }}>
                <ResultTable
                  rows={activeTab.result.rows}
                  columns={activeTab.result.columns}
                  duration_ms={activeTab.result.duration_ms}
                  row_count={activeTab.result.row_count}
                  truncated={activeTab.result.truncated}
                />
              </div>
            )}

            {activeTab.error && (
              <div style={{ padding: 16, background: 'rgba(239,68,68,0.08)', borderTop: '1px solid rgba(239,68,68,0.2)', color: 'var(--danger)', fontSize: 12, fontFamily: 'DM Mono', whiteSpace: 'pre-wrap' }}>
                {activeTab.error}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Save modal */}
      {showSave && (
        <div className="modal-overlay" onClick={e => e.target === e.currentTarget && setShowSave(false)}>
          <div className="modal" style={{ maxWidth: 400 }}>
            <h2 className="modal-title">Sauvegarder la requête</h2>
            <input value={saveName} onChange={e => setSaveName(e.target.value)} placeholder="Nom de la requête" autoFocus />
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 16 }}>
              <button className="btn btn-ghost" onClick={() => setShowSave(false)}>Annuler</button>
              <button className="btn btn-primary" onClick={handleSave} disabled={saving || !saveName}>
                {saving ? <span className="spinner" /> : <Save size={13} />} Sauvegarder
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
