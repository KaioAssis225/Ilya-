import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { KeyRound, ShieldCheck } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import api from '../lib/api'

export default function TrocarSenhaPage() {
  const { user, refreshMe } = useAuth()
  const navigate = useNavigate()

  const [newPassword, setNewPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (user && !user.must_change_password) {
    navigate('/', { replace: true })
    return null
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')

    if (newPassword.length < 8) {
      setError('A senha deve ter pelo menos 8 caracteres.')
      return
    }
    if (newPassword !== confirm) {
      setError('As senhas não coincidem.')
      return
    }

    setLoading(true)
    try {
      await api.post('/auth/change-password', { new_password: newPassword })
      await refreshMe()
      navigate('/', { replace: true })
    } catch {
      setError('Erro ao trocar a senha. Tente novamente.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-[#8b6914]/10 mb-4">
            <ShieldCheck className="w-7 h-7 text-gold" />
          </div>
          <h1 className="text-2xl font-medium text-ink" style={{ fontFamily: "'Cormorant Garamond', Georgia, serif" }}>
            Troca de Senha Obrigatória
          </h1>
          <p className="mt-2 text-sm text-muted-2 leading-relaxed">
            Por segurança, defina uma nova senha antes de acessar o sistema.
          </p>
          <div className="gold-rule mt-4" />
        </div>

        <div className="bg-surface rounded-2xl shadow-sm border border-line px-8 py-9">
          {user && (
            <p className="text-xs text-muted-2 text-center mb-5">
              Bem-vindo(a), <strong className="text-ink">{user.full_name}</strong>
            </p>
          )}
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-1.5">
              <label htmlFor="new-pw" className="block text-[11px] font-semibold text-muted uppercase tracking-wider">
                Nova Senha
              </label>
              <input
                id="new-pw"
                type="password"
                required
                autoFocus
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="input"
                placeholder="mínimo 8 caracteres"
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="confirm-pw" className="block text-[11px] font-semibold text-muted uppercase tracking-wider">
                Confirmar Senha
              </label>
              <input
                id="confirm-pw"
                type="password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="input"
                placeholder="repita a nova senha"
              />
            </div>

            {error && <p className="text-sm text-red-700 text-center" role="alert">{error}</p>}

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full tracking-widest py-2.5 mt-1"
            >
              <KeyRound className="w-4 h-4" />
              {loading ? 'Salvando…' : 'Definir Nova Senha'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
