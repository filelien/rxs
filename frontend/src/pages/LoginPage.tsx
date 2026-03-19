import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores'
import { authApi } from '../lib/api'
import toast from 'react-hot-toast'
import { Database, Eye, EyeOff } from 'lucide-react'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [loading, setLoading] = useState(false)
  const { setAuth } = useAuthStore()
  const navigate = useNavigate()

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !password) return
    setLoading(true)
    try {
      const data = await authApi.login(username, password)
      const me = await authApi.me()
      setAuth({ user_id: me.user_id, username: me.username, role: me.role }, data.access_token, data.refresh_token)
      toast.success(`Bienvenue, ${me.username}`)
      navigate('/dashboard')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Identifiants incorrects')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', background: 'var(--bg-base)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 24,
    }}>
      {/* Glow background */}
      <div style={{
        position: 'absolute', top: '20%', left: '50%', transform: 'translateX(-50%)',
        width: 600, height: 300, background: 'radial-gradient(ellipse, rgba(59,130,246,0.08) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      <div style={{ width: '100%', maxWidth: 400, position: 'relative' }}>
        {/* Logo */}
        <div style={{ textAlign: 'center', marginBottom: 40 }}>
          <div style={{
            width: 52, height: 52, borderRadius: 14,
            background: 'var(--bg-raised)', border: '1px solid var(--border-lit)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            margin: '0 auto 16px',
          }}>
            <Database size={24} color="var(--accent)" />
          </div>
          <h1 className="font-display" style={{ fontSize: 28, fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-1px' }}>
            Raxus
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
            Unified Intelligent Data Platform
          </p>
        </div>

        {/* Form */}
        <div className="card" style={{ padding: 28 }}>
          <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <label style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 6, display: 'block' }}>
                Nom d'utilisateur
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="admin"
                autoComplete="username"
                autoFocus
              />
            </div>
            <div>
              <label style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500, marginBottom: 6, display: 'block' }}>
                Mot de passe
              </label>
              <div style={{ position: 'relative' }}>
                <input
                  type={showPw ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  style={{ paddingRight: 40 }}
                />
                <button
                  type="button"
                  onClick={() => setShowPw(!showPw)}
                  style={{
                    position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                    background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-dim)',
                  }}
                >
                  {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading || !username || !password}
              style={{ marginTop: 4, justifyContent: 'center', height: 40 }}
            >
              {loading ? <span className="spinner" /> : 'Se connecter'}
            </button>
          </form>
        </div>

        <p style={{ textAlign: 'center', fontSize: 12, color: 'var(--text-dim)', marginTop: 20 }}>
          Compte par défaut : <span className="font-mono" style={{ color: 'var(--text-muted)' }}>admin / Admin@Raxus2025!</span>
        </p>
      </div>
    </div>
  )
}
