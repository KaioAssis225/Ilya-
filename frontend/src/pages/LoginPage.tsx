import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { Eye, EyeOff } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { MarketFlag, type MarketCode } from '../components/MarketFlag'
import { MarketTransition } from '../components/MarketTransition'
import { BrandLoadingOverlay } from '../components/BrandLoadingOverlay'

export default function LoginPage() {
  const { login, user, switchMarket } = useAuth()
  const navigate = useNavigate()

  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [choosingMarket, setChoosingMarket] = useState(false)
  const [loadingMarket, setLoadingMarket] = useState<MarketCode | null>(null)
  const authenticatingRef = useRef(false)

  useEffect(() => {
    if (user && !authenticatingRef.current && !choosingMarket) navigate('/', { replace: true })
  }, [choosingMarket, navigate, user])

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    authenticatingRef.current = true
    try {
      const authenticatedUser = await login(identifier, password)
      if (authenticatedUser.allowed_markets.length > 1) {
        setChoosingMarket(true)
        return
      }
      navigate('/', { replace: true })
    } catch {
      setError('Usuário ou senha incorretos.')
      authenticatingRef.current = false
    } finally {
      setLoading(false)
    }
  }

  async function chooseMarket(market: MarketCode) {
    if (!user) return
    setLoading(true)
    setLoadingMarket(market)
    const startedAt = performance.now()
    try {
      if (market !== user.active_market) await switchMarket(market, false)
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
      const remaining = Math.max(0, (reduceMotion ? 0 : 1650) - (performance.now() - startedAt))
      if (remaining > 0) await new Promise(resolve => window.setTimeout(resolve, remaining))
      navigate('/', { replace: true })
    } catch {
      setError('Não foi possível abrir esse ambiente. Tente novamente.')
      setChoosingMarket(false)
      authenticatingRef.current = false
    } finally {
      setLoading(false)
      setLoadingMarket(null)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        {/* Wordmark */}
        <div className="text-center mb-9">
          <h1 className="font-display text-5xl font-light text-ink tracking-[0.28em]">
            ILYA
          </h1>
          <p className="mt-3 text-xs text-muted-2 tracking-[0.4em] uppercase">
            Sistema de Orçamentos
          </p>
          <div className="gold-rule mt-5" />
        </div>

        {/* Card */}
        <div className="bg-surface rounded-2xl shadow-sm border border-line px-8 py-9">
          {choosingMarket && user ? (
            <div>
              <h2 className="text-center font-display text-xl font-semibold text-ink">Escolha o ambiente</h2>
              <p className="mt-1.5 text-center text-sm text-muted">Onde você quer trabalhar agora?</p>
              <div className="mt-6 grid grid-cols-2 gap-3">
                {user.allowed_markets.map(market => (
                  <button
                    key={market}
                    type="button"
                    onClick={() => void chooseMarket(market)}
                    disabled={loading}
                    className="flex min-h-24 flex-col items-center justify-center gap-3 rounded-xl border border-line bg-surface-2 text-sm font-semibold text-ink transition-colors hover:border-gold/50 hover:bg-gold-wash focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 disabled:opacity-60"
                  >
                    <MarketFlag market={market} className="h-7 w-10 shadow-sm" />
                    {market === 'BR' ? 'Brasil' : 'Portugal'}
                  </button>
                ))}
              </div>
            </div>
          ) : (
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-1.5">
              <label htmlFor="login-id" className="block text-xs font-semibold text-muted uppercase tracking-wider">
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
              <label htmlFor="login-pw" className="block text-xs font-semibold text-muted uppercase tracking-wider">
                Senha
              </label>
              <div className="relative">
                <input
                  id="login-pw"
                  type={showPw ? 'text' : 'password'}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={`input pr-11 w-full ${error ? 'border-danger focus:ring-danger/25 focus:border-danger' : ''}`}
                  placeholder="••••••••"
                  aria-invalid={error ? true : undefined}
                  aria-describedby={error ? 'login-error' : undefined}
                />
                <button
                  type="button"
                  onClick={() => setShowPw(s => !s)}
                  aria-label={showPw ? 'Ocultar senha' : 'Mostrar senha'}
                  aria-pressed={showPw}
                  className="absolute inset-y-0 right-0 w-11 flex items-center justify-center text-muted hover:text-ink transition-colors rounded-r-control"
                >
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {error && (
              <p id="login-error" className="text-sm text-danger font-medium text-center" role="alert">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full tracking-widest py-2.5 mt-1"
            >
              {loading ? 'Entrando…' : 'Entrar'}
            </button>
          </form>
          )}
        </div>

        <p className="text-center text-xs text-muted mt-6">
          © {new Date().getFullYear()} Ilya — Uso interno
        </p>
      </div>

      {/* Bloco 84: overlay premium claro durante a autenticação */}
      {loadingMarket ? (
        <MarketTransition market={loadingMarket} />
      ) : loading && (
        <BrandLoadingOverlay label="Autenticando" />
      )}
    </div>
  )
}
