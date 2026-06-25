import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

export default function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch {
      setError('E-mail ou senha incorretos.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#f5f0eb]">
      <div className="w-full max-w-sm">
        {/* Logotipo / Cabeçalho */}
        <div className="text-center mb-10">
          <h1 className="text-4xl font-medium text-[#2c2420] tracking-wide" style={{ fontFamily: "'Cormorant Garamond', Georgia, serif" }}>
            Projeto Ilya
          </h1>
          <p className="mt-1 text-sm text-[#8a7e72] tracking-widest uppercase">
            Sistema de Orçamentos
          </p>
          <div className="mt-4 mx-auto w-12 h-[2px] bg-[#8b6914]" />
        </div>

        {/* Card */}
        <div className="bg-white rounded-lg shadow-md border border-[#e8e0d6] px-8 py-8">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-xs font-medium text-[#8a7e72] uppercase tracking-widest mb-1">
                E-mail
              </label>
              <input
                type="email"
                required
                autoFocus
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full border border-[#e8e0d6] rounded-md px-3 py-2.5 text-sm text-[#2c2420] bg-[#faf8f5] focus:outline-none focus:border-[#8b6914] focus:ring-1 focus:ring-[#8b6914] transition"
                placeholder="seu@email.com"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-[#8a7e72] uppercase tracking-widest mb-1">
                Senha
              </label>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full border border-[#e8e0d6] rounded-md px-3 py-2.5 text-sm text-[#2c2420] bg-[#faf8f5] focus:outline-none focus:border-[#8b6914] focus:ring-1 focus:ring-[#8b6914] transition"
                placeholder="••••••••"
              />
            </div>

            {error && (
              <p className="text-sm text-red-600 text-center">{error}</p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-[#8b6914] hover:bg-[#7a5c10] text-white text-sm font-medium uppercase tracking-widest py-2.5 rounded-md transition disabled:opacity-60 disabled:cursor-not-allowed mt-2"
            >
              {loading ? 'Entrando…' : 'Entrar'}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-[#8a7e72] mt-6">
          © {new Date().getFullYear()} Ilya — Uso interno
        </p>
      </div>
    </div>
  )
}
