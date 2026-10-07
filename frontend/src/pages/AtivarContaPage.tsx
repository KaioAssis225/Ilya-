import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { authApi } from '../lib/api'

function takeToken(): string {
  return new URLSearchParams(window.location.hash.slice(1)).get('token') ?? ''
}

export default function AtivarContaPage() {
  const [token] = useState(takeToken)
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [pending, setPending] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    window.history.replaceState(window.history.state, '', window.location.pathname)
  }, [])

  async function activate(event: FormEvent) {
    event.preventDefault()
    if (password !== confirmation) {
      setError('As senhas não coincidem.')
      return
    }
    setPending(true)
    setError('')
    try {
      await authApi.post('/auth/activate-client', { token, new_password: password })
      setDone(true)
      setPassword('')
      setConfirmation('')
    } catch {
      setError('Não foi possível ativar a conta. Peça um novo convite ao administrador.')
    } finally {
      setPending(false)
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm bg-surface rounded-2xl shadow-sm border border-line px-8 py-9 space-y-5">
        <h1 className="text-2xl font-semibold text-ink">Ativar conta</h1>
        {done ? (
          <>
            <p role="status" className="text-sm text-ink-2">Senha definida. Sua conta está pronta para acesso.</p>
            <Link className="btn-primary inline-block" to="/login">Ir para o login</Link>
          </>
        ) : !token ? (
          <p role="alert" className="text-sm text-terracotta">Convite ausente. Peça um novo link ao administrador.</p>
        ) : (
          <form onSubmit={activate} className="space-y-4">
            <p className="text-sm text-ink-2">Defina uma senha para acessar sua conta.</p>
            <label className="block text-sm text-ink-2" htmlFor="new-password">Nova senha</label>
            <input id="new-password" className="input" type="password" autoComplete="new-password" minLength={8} maxLength={128} required value={password} onChange={event => setPassword(event.target.value)} />
            <label className="block text-sm text-ink-2" htmlFor="confirm-password">Confirme a senha</label>
            <input id="confirm-password" className="input" type="password" autoComplete="new-password" minLength={8} maxLength={128} required value={confirmation} onChange={event => setConfirmation(event.target.value)} />
            {error && <p role="alert" className="text-sm text-terracotta">{error}</p>}
            <button type="submit" className="btn-primary" disabled={pending}>{pending ? 'Ativando…' : 'Ativar conta'}</button>
          </form>
        )}
      </div>
    </main>
  )
}
