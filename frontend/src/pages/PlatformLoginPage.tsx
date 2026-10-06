import { useState } from 'react'
import { Navigate } from 'react-router'
import { ShieldCheck } from 'lucide-react'
import { usePlatformAuth } from '../hooks/usePlatformAuth'

export default function PlatformLoginPage() {
  const { user, login } = usePlatformAuth()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  if (user) return <Navigate to="/platform" replace />

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      await login(identifier, password)
    } catch {
      setError('Usuário, senha ou acesso de plataforma inválido.')
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="min-h-screen bg-bg flex items-center justify-center px-5">
      <form onSubmit={submit} className="w-full max-w-sm space-y-5 rounded-2xl border border-line bg-white p-7 shadow-xl">
        <div className="flex items-center gap-3">
          <ShieldCheck className="h-7 w-7 text-gold" />
          <div>
            <h1 className="text-xl font-semibold text-ink">Plataforma Ilya</h1>
            <p className="text-xs text-muted">Acesso administrativo global</p>
          </div>
        </div>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">E-mail ou usuário</span>
          <input className="input" value={identifier} onChange={event => setIdentifier(event.target.value)} required autoComplete="username" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Senha</span>
          <input className="input" type="password" value={password} onChange={event => setPassword(event.target.value)} required autoComplete="current-password" />
        </label>
        {error && <p className="text-sm text-terracotta">{error}</p>}
        <button className="btn-primary w-full" disabled={pending}>{pending ? 'Entrando…' : 'Entrar na plataforma'}</button>
        <a className="block text-center text-xs text-muted hover:text-gold" href="/login">Voltar ao acesso comercial</a>
      </form>
    </main>
  )
}
