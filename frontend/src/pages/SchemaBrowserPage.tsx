import { useState, useEffect } from 'react'
import { useConnectionsStore } from '../stores'
import { connectionsApi, queryApi } from '../lib/api'
import {
  Database, Table2, ChevronRight, ChevronDown, Search,
  Key, Hash, AlignLeft, ToggleLeft, Calendar, RefreshCw, Copy
} from 'lucide-react'
import toast from 'react-hot-toast'

const C = {
  bg2: '#0d1425', bg3: '#111b30', border: '#1a2640', borderLit: '#243450',
  blue: '#3b8ef3', teal: '#00d4aa', amber: '#f59e0b', red: '#ef4444', green: '#22c55e',
  text0: '#f0f4ff', text1: '#8ba3c7', text2: '#3d5a7a',
  oracle: '#f97316', mysql: '#00b4d8', postgres: '#818cf8', mongodb: '#22c55e', redis: '#ef4444',
}

const DB_COLORS: Record<string, string> = {
  oracle: C.oracle, mysql: C.mysql, postgresql: C.postgres, mongodb: C.mongodb, redis: C.redis
}

const TYPE_ICONS: Record<string, any> = {
  NUMBER: Hash, INT: Hash, INTEGER: Hash, BIGINT: Hash, DECIMAL: Hash, FLOAT: Hash, DOUBLE: Hash,
  VARCHAR: AlignLeft, CHAR: AlignLeft, TEXT: AlignLeft, CLOB: AlignLeft, NVARCHAR: AlignLeft,
  DATE: Calendar, DATETIME: Calendar, TIMESTAMP: Calendar,
  BOOLEAN: ToggleLeft, BOOL: ToggleLeft,
}

function getTypeIcon(dataType: string) {
  const upper = (dataType || '').toUpperCase()
  for (const [key, Icon] of Object.entries(TYPE_ICONS)) {
    if (upper.includes(key)) return Icon
  }
  return Hash
}

function TypeBadge({ type }: { type: string }) {
  const upper = (type || '').toUpperCase()
  let color = C.text2
  if (/INT|NUMBER|FLOAT|DECIMAL|DOUBLE/.test(upper)) color = C.amber
  else if (/CHAR|TEXT|CLOB/.test(upper)) color = C.blue
  else if (/DATE|TIME/.test(upper)) color = C.teal
  else if (/BOOL/.test(upper)) color = C.green

  return (
    <span style={{
      fontSize: 10, padding: '1px 6px', borderRadius: 4, fontFamily: 'DM Mono, monospace',
      background: `${color}15`, color, border: `1px solid ${color}25`, whiteSpace: 'nowrap',
    }}>
      {type?.toUpperCase()}
    </span>
  )
}

interface Column { name: string; data_type: string; nullable: boolean; default?: string; primary_key: boolean }
interface Index { name: string; columns: string[]; unique: boolean }
interface Table { name: string; schema?: string; row_count?: number; size_bytes?: number; columns?: Column[]; indexes?: Index[] }

export default function SchemaBrowserPage() {
  const { connections, activeConnectionId, setActive } = useConnectionsStore()
  const [selectedConn, setSelectedConn] = useState(activeConnectionId || '')
  const [schema, setSchema] = useState<Table[]>([])
  const [selectedTable, setSelectedTable] = useState<Table | null>(null)
  const [tableDetail, setTableDetail] = useState<any>(null)
  const [expandedTables, setExpandedTables] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [databases, setDatabases] = useState<string[]>([])
  const [selectedDb, setSelectedDb] = useState('')

  useEffect(() => {
    if (selectedConn) loadDatabases()
  }, [selectedConn])

  useEffect(() => {
    if (selectedConn) loadSchema()
  }, [selectedConn, selectedDb])

  const loadDatabases = async () => {
    try {
      const res = await connectionsApi.list()
      // Try to get databases list
      const dbRes = await fetch(`/connections/${selectedConn}/databases`)
      if (dbRes.ok) {
        const data = await dbRes.json()
        setDatabases(data.databases || [])
      }
    } catch { /* silent */ }
  }

  const loadSchema = async () => {
    if (!selectedConn) return
    setLoading(true)
    setSelectedTable(null)
    setTableDetail(null)
    try {
      const res = await queryApi.schema(selectedConn, selectedDb || undefined)
      setSchema(res.tables || [])
    } catch (e: any) {
      toast.error('Erreur chargement schéma')
      setSchema([])
    } finally {
      setLoading(false)
    }
  }

  const loadTableDetail = async (table: Table) => {
    setSelectedTable(table)
    setLoadingDetail(true)
    try {
      const res = await fetch(`/query/schema/${selectedConn}/table/${table.name}${table.schema ? `?schema=${table.schema}` : ''}`)
      const data = await res.json()
      setTableDetail(data)
    } catch {
      setTableDetail(null)
    } finally {
      setLoadingDetail(false)
    }
  }

  const filteredTables = schema.filter(t =>
    !search || t.name.toLowerCase().includes(search.toLowerCase())
  )

  const conn = connections.find(c => c.id === selectedConn)
  const dbColor = conn ? (DB_COLORS[conn.db_type] || C.blue) : C.blue

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
    toast.success('Copié !')
  }

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 100px)', background: '#05080f', borderRadius: 10, overflow: 'hidden', border: `1px solid ${C.border}` }}>

      {/* Left: Table list */}
      <div style={{ width: 280, borderRight: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', flexShrink: 0, background: C.bg2 }}>
        {/* Header */}
        <div style={{ padding: '14px 14px 10px', borderBottom: `1px solid ${C.border}` }}>
          <select
            value={selectedConn}
            onChange={e => { setSelectedConn(e.target.value); setActive(e.target.value) }}
            style={{
              width: '100%', padding: '7px 10px', borderRadius: 7, fontSize: 12,
              background: C.bg3, border: `1px solid ${C.border}`, color: C.text1,
              marginBottom: 8,
            }}
          >
            <option value="">— Sélectionner une connexion —</option>
            {connections.filter(c => c.enabled).map(c => (
              <option key={c.id} value={c.id}>{c.name} ({c.db_type})</option>
            ))}
          </select>

          {databases.length > 0 && (
            <select
              value={selectedDb}
              onChange={e => setSelectedDb(e.target.value)}
              style={{
                width: '100%', padding: '6px 10px', borderRadius: 7, fontSize: 12,
                background: C.bg3, border: `1px solid ${C.border}`, color: C.text1,
                marginBottom: 8,
              }}
            >
              <option value="">— Toutes les bases —</option>
              {databases.map(d => <option key={d} value={d}>{d}</option>)}
            </select>
          )}

          <div style={{ position: 'relative' }}>
            <Search size={12} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: C.text2 }} />
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Filtrer les tables..."
              style={{
                width: '100%', padding: '7px 10px 7px 28px', borderRadius: 7, fontSize: 12,
                background: C.bg3, border: `1px solid ${C.border}`, color: C.text1,
              }}
            />
          </div>
        </div>

        {/* Stats bar */}
        {schema.length > 0 && (
          <div style={{ padding: '8px 14px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 11, color: C.text2 }}>
              {filteredTables.length} table{filteredTables.length > 1 ? 's' : ''}
              {search && ` sur ${schema.length}`}
            </span>
            <div style={{ flex: 1 }} />
            <button
              onClick={loadSchema}
              disabled={loading}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: C.text2, padding: 2 }}
            >
              <RefreshCw size={11} style={loading ? { animation: 'spin 0.8s linear infinite' } : {}} />
            </button>
          </div>
        )}

        {/* Table list */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {!selectedConn ? (
            <div style={{ textAlign: 'center', color: C.text2, fontSize: 12, padding: 32 }}>
              <Database size={28} style={{ margin: '0 auto 10px', opacity: 0.3 }} />
              Sélectionnez une connexion
            </div>
          ) : loading ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: 32, color: C.text2, fontSize: 12 }}>
              <span style={{ width: 14, height: 14, border: `2px solid ${C.border}`, borderTopColor: C.blue, borderRadius: '50%', animation: 'spin 0.7s linear infinite', display: 'inline-block' }} />
              Chargement du schéma...
            </div>
          ) : filteredTables.length === 0 ? (
            <div style={{ textAlign: 'center', color: C.text2, fontSize: 12, padding: 32 }}>
              {search ? 'Aucune table trouvée' : 'Aucune table'}
            </div>
          ) : (
            <div style={{ padding: '6px 8px' }}>
              {filteredTables.map(table => {
                const isSelected = selectedTable?.name === table.name
                return (
                  <div
                    key={`${table.schema}-${table.name}`}
                    onClick={() => loadTableDetail(table)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '8px 10px', borderRadius: 7, cursor: 'pointer',
                      background: isSelected ? `${dbColor}15` : 'transparent',
                      border: `1px solid ${isSelected ? `${dbColor}40` : 'transparent'}`,
                      marginBottom: 2, transition: 'all 0.12s',
                    }}
                    onMouseEnter={e => { if (!isSelected) e.currentTarget.style.background = C.bg3 }}
                    onMouseLeave={e => { if (!isSelected) e.currentTarget.style.background = 'transparent' }}
                  >
                    <Database size={13} color={isSelected ? dbColor : C.text2} style={{ flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, fontWeight: 500, color: isSelected ? C.text0 : C.text1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {table.name}
                      </div>
                      {table.schema && (
                        <div style={{ fontSize: 10, color: C.text2 }}>{table.schema}</div>
                      )}
                    </div>
                    {table.row_count != null && (
                      <span style={{ fontSize: 10, color: C.text2, fontFamily: 'DM Mono, monospace', flexShrink: 0 }}>
                        {table.row_count.toLocaleString()}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* Right: Table detail */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: '#05080f' }}>
        {!selectedTable ? (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: C.text2, gap: 12 }}>
            <Database size={40} style={{ opacity: 0.2 }} />
            <div style={{ fontSize: 14, color: C.text1 }}>Sélectionnez une table</div>
            <div style={{ fontSize: 12, color: C.text2 }}>pour explorer sa structure</div>
          </div>
        ) : (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {/* Table header */}
            <div style={{ padding: '16px 20px', borderBottom: `1px solid ${C.border}`, display: 'flex', alignItems: 'center', gap: 12, background: C.bg2 }}>
              <div style={{ width: 36, height: 36, borderRadius: 9, background: `${dbColor}15`, border: `1px solid ${dbColor}30`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Database size={16} color={dbColor} />
              </div>
              <div>
                <div style={{ fontSize: 15, fontWeight: 600, color: C.text0, fontFamily: 'Syne, sans-serif' }}>
                  {selectedTable.schema && <span style={{ color: C.text2, fontWeight: 400 }}>{selectedTable.schema}.</span>}
                  {selectedTable.name}
                </div>
                <div style={{ fontSize: 11, color: C.text2, display: 'flex', gap: 12, marginTop: 2 }}>
                  {selectedTable.row_count != null && <span>{selectedTable.row_count.toLocaleString()} lignes</span>}
                  {selectedTable.size_bytes != null && <span>{Math.round(selectedTable.size_bytes / 1024)} KB</span>}
                </div>
              </div>
              <div style={{ flex: 1 }} />
              <button
                onClick={() => copyToClipboard(`SELECT * FROM ${selectedTable.schema ? selectedTable.schema + '.' : ''}${selectedTable.name} WHERE ROWNUM <= 100`)}
                style={{ padding: '6px 12px', borderRadius: 7, border: `1px solid ${C.borderLit}`, background: C.bg3, color: C.text1, fontSize: 11, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5 }}
              >
                <Copy size={11} /> Copier SELECT
              </button>
            </div>

            {loadingDetail ? (
              <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, color: C.text2 }}>
                <span style={{ width: 14, height: 14, border: `2px solid ${C.border}`, borderTopColor: C.blue, borderRadius: '50%', animation: 'spin 0.7s linear infinite', display: 'inline-block' }} />
                Chargement...
              </div>
            ) : tableDetail ? (
              <div style={{ flex: 1, overflow: 'auto' }}>
                {/* Columns */}
                <div style={{ padding: '16px 20px' }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: C.text1, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                    <AlignLeft size={13} /> Colonnes ({(tableDetail.columns || []).length})
                  </div>
                  <div style={{ border: `1px solid ${C.border}`, borderRadius: 10, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                      <thead>
                        <tr style={{ background: C.bg3 }}>
                          {['Colonne', 'Type', 'Null', 'Défaut', 'PK'].map(h => (
                            <th key={h} style={{ padding: '9px 14px', textAlign: 'left', fontSize: 10, color: C.text2, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: `1px solid ${C.border}`, whiteSpace: 'nowrap' }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {(tableDetail.columns || []).map((col: Column, i: number) => {
                          const TypeIcon = getTypeIcon(col.data_type)
                          return (
                            <tr key={i} style={{ borderBottom: `1px solid ${C.border}` }}
                              onMouseEnter={e => (e.currentTarget.style.background = C.bg3)}
                              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                            >
                              <td style={{ padding: '10px 14px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                                  {col.primary_key && <Key size={10} color={C.amber} />}
                                  <TypeIcon size={12} color={C.text2} />
                                  <span style={{ fontFamily: 'DM Mono, monospace', color: col.primary_key ? C.amber : C.text0, fontWeight: col.primary_key ? 600 : 400 }}>
                                    {col.name}
                                  </span>
                                </div>
                              </td>
                              <td style={{ padding: '10px 14px' }}>
                                <TypeBadge type={col.data_type} />
                              </td>
                              <td style={{ padding: '10px 14px' }}>
                                <span style={{ fontSize: 11, color: col.nullable ? C.text2 : C.red }}>
                                  {col.nullable ? 'YES' : 'NO'}
                                </span>
                              </td>
                              <td style={{ padding: '10px 14px', fontFamily: 'DM Mono, monospace', fontSize: 11, color: C.text2 }}>
                                {col.default != null ? String(col.default).slice(0, 30) : '—'}
                              </td>
                              <td style={{ padding: '10px 14px' }}>
                                {col.primary_key && (
                                  <span style={{ fontSize: 9, padding: '2px 6px', borderRadius: 4, background: `${C.amber}20`, color: C.amber, fontWeight: 700 }}>PK</span>
                                )}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Indexes */}
                {(tableDetail.indexes || []).length > 0 && (
                  <div style={{ padding: '0 20px 16px' }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: C.text1, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <Hash size={13} /> Index ({(tableDetail.indexes || []).length})
                    </div>
                    <div style={{ border: `1px solid ${C.border}`, borderRadius: 10, overflow: 'hidden' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                        <thead>
                          <tr style={{ background: C.bg3 }}>
                            {['Nom', 'Colonnes', 'Unique'].map(h => (
                              <th key={h} style={{ padding: '9px 14px', textAlign: 'left', fontSize: 10, color: C.text2, fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.06em', borderBottom: `1px solid ${C.border}` }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {(tableDetail.indexes || []).map((idx: Index, i: number) => (
                            <tr key={i} style={{ borderBottom: i < tableDetail.indexes.length - 1 ? `1px solid ${C.border}` : 'none' }}>
                              <td style={{ padding: '10px 14px', fontFamily: 'DM Mono, monospace', fontSize: 11, color: C.text0 }}>{idx.name}</td>
                              <td style={{ padding: '10px 14px', fontFamily: 'DM Mono, monospace', fontSize: 11, color: C.blue }}>
                                {(idx.columns || []).join(', ')}
                              </td>
                              <td style={{ padding: '10px 14px' }}>
                                {idx.unique
                                  ? <span style={{ fontSize: 9, padding: '2px 6px', borderRadius: 4, background: `${C.teal}20`, color: C.teal, fontWeight: 700 }}>UNIQUE</span>
                                  : <span style={{ fontSize: 11, color: C.text2 }}>—</span>
                                }
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* Oracle stats */}
                {tableDetail.oracle_stats && Object.keys(tableDetail.oracle_stats).length > 0 && (
                  <div style={{ padding: '0 20px 16px' }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: C.text1, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <Database size={13} color={C.oracle} /> Statistiques Oracle
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 8 }}>
                      {Object.entries(tableDetail.oracle_stats).map(([k, v]) => (
                        <div key={k} style={{ background: C.bg3, border: `1px solid ${C.border}`, borderRadius: 8, padding: '10px 12px' }}>
                          <div style={{ fontSize: 10, color: C.text2, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>{k.replace(/_/g, ' ')}</div>
                          <div style={{ fontSize: 14, fontWeight: 600, color: C.text0, fontFamily: 'DM Mono, monospace' }}>{String(v) || '—'}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        )}
      </div>

      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  )
}
