import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { Eye, EyeOff } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { MarketFlag, type MarketCode } from '../components/MarketFlag'

export default function LoginPage() {
  const { login, user, switchMarket } = useAuth()
  const navigate = useNavigate()

  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [choosingMarket, setChoosingMarket] = useState(false)
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
    try {
      if (market !== user.active_market) await switchMarket(market, false)
      navigate('/', { replace: true })
    } catch {
      setError('Não foi possível abrir esse ambiente. Tente novamente.')
      setChoosingMarket(false)
      authenticatingRef.current = false
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
          <p className="mt-3 text-xs text-muted-2 tracking-[0.4em] uppercase">
            Sistema de Orçamentos
          </p>
          <div className="gold-rule mt-5" />
        </div>

        {/* Card */}
        <div className="bg-surface rounded-2xl shadow-sm border border-line px-8 py-9">
          {choosingMarket && user ? (
            <div>
              <h2 className="text-center text-xl font-semibold text-ink" style={{ fontFamily: "'Cormorant Garamond', Georgia, serif" }}>Escolha o ambiente</h2>
              <p className="mt-1.5 text-center text-sm text-muted">Onde você quer trabalhar agora?</p>
              <div className="mt-6 grid grid-cols-2 gap-3">
                {user.allowed_markets.map(market => (
                  <button
                    key={market}
                    type="button"
                    onClick={() => void chooseMarket(market)}
                    disabled={loading}
                    className="flex min-h-24 flex-col items-center justify-center gap-3 rounded-xl border border-line bg-surface-alt text-sm font-semibold text-ink transition-colors hover:border-gold/50 hover:bg-gold-wash focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 disabled:opacity-60"
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
                  className="input pr-11 w-full"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPw(s => !s)}
                  aria-label={showPw ? 'Ocultar senha' : 'Mostrar senha'}
                  className="absolute inset-y-0 right-0 w-11 flex items-center justify-center text-muted hover:text-ink transition-colors"
                  tabIndex={-1}
                >
                  {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
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
          )}
        </div>

        <p className="text-center text-xs text-muted mt-6">
          © {new Date().getFullYear()} Ilya — Uso interno
        </p>
      </div>

      {/* Bloco 84: overlay premium claro durante a autenticação */}
      {loading && (
        <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center bg-bg/90 backdrop-blur-sm">
          <div className="absolute w-[520px] h-[520px] rounded-full pointer-events-none" style={{ background: 'radial-gradient(circle, rgba(139,105,20,0.18) 0%, transparent 68%)', animation: 'pulseRadial 2.2s ease-in-out infinite' }} />
          <p className="relative text-[50px] sm:text-[80px] leading-none tracking-[0.35em] font-light select-none" style={{ fontFamily: "'Cormorant Garamond', Georgia, serif", backgroundImage: 'linear-gradient(90deg, #5a4508 0%, #8b6914 25%, #c8952e 50%, #8b6914 75%, #5a4508 100%)', backgroundSize: '200% auto', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', animation: 'lightSweep 2.4s linear infinite' }}>ILYA</p>
          <p className="mt-5 text-[11px] tracking-[0.55em] uppercase font-semibold text-gold" style={{ animation: 'fadeInOut 1.8s ease-in-out infinite' }}>Autenticando</p>
          <div className="mt-9 w-52 h-[1px] bg-gold/25 overflow-hidden rounded-full"><div className="h-full rounded-full" style={{ background: 'linear-gradient(90deg, #5a4508, #c8952e, #5a4508)', animation: 'progressLine 3s linear forwards' }} /></div>
        </div>
      )}
    </div>
  )
}
