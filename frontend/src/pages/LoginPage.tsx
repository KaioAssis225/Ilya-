import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()

  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(identifier, password)
      navigate('/', { replace: true })
    } catch {
      setError('Usuário ou senha incorretos.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        {/* Wordmark */}
        <div className="text-center mb-9">
          <h1
            className="text-5xl font-light text-ink"
            style={{ fontFamily: "'Cormorant Garamond', Georgia, serif", letterSpacing: '0.28em' }}
          >
            ILYA
          </h1>
          <p className="mt-3 text-[11px] text-muted-2 tracking-[0.4em] uppercase">
            Sistema de Orçamentos
          </p>
          <div className="gold-rule mt-5" />
        </div>

        {/* Card */}
        <div className="bg-surface rounded-2xl shadow-sm border border-line px-8 py-9">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-1.5">
              <label htmlFor="login-id" className="block text-[11px] font-semibold text-muted uppercase tracking-wider">
                E-mail ou Usuário
              </label>
              <input
                id="login-id"
                type="text"
                required
                autoFocus
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                className="input"
                placeholder="seu@email.com ou usuário"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="login-pw" className="block text-[11px] font-semibold text-muted uppercase tracking-wider">
                Senha
              </label>
              <input
                id="login-pw"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <p className="text-sm text-red-700 text-center" role="alert">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full tracking-widest py-2.5 mt-1"
            >
              {loading ? 'Entrando…' : 'Entrar'}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-muted mt-6">
          © {new Date().getFullYear()} Ilya — Uso interno
        </p>
      </div>
    </div>
  )
}
