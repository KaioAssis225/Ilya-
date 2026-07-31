import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router'
import axios from 'axios'
import { Eye, EyeOff, KeyRound, ShieldCheck } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import PasswordStrength from '../components/PasswordStrength'
import { firstUnmetRule, isPasswordValid } from '../lib/passwordRules'
import api from '../lib/api'

export default function TrocarSenhaPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const [newPassword, setNewPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showNew, setShowNew] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (user && !user.must_change_password) {
    return <Navigate to="/" replace />
  }

  const canSubmit = isPasswordValid(newPassword) && newPassword === confirm

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')

    const unmet = firstUnmetRule(newPassword)
    if (unmet) {
      setError(`A senha ainda não atende: ${unmet.label.toLowerCase()}.`)
      return
    }
    if (newPassword !== confirm) {
      setError('As senhas não coincidem.')
      return
    }

    setLoading(true)
    try {
      await api.post('/auth/change-password', { new_password: newPassword })
      await logout()
      navigate('/login', { replace: true })
    } catch (err) {
      // O servidor é quem valida de fato; quando ele recusa a senha (422),
      // mostramos o motivo exato em vez de um erro genérico.
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null
      setError(typeof detail === 'string' ? detail : 'Erro ao trocar a senha. Tente novamente.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-gold/10 mb-4">
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
              <div className="relative">
                <input
                  id="new-pw"
                  type={showNew ? 'text' : 'password'}
                  required
                  autoFocus
                  autoComplete="new-password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="input w-full pr-11"
                  placeholder="crie sua nova senha"
                />
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={() => setShowNew((s) => !s)}
                  aria-label={showNew ? 'Ocultar senha' : 'Mostrar senha'}
                  className="absolute inset-y-0 right-0 w-11 flex items-center justify-center text-muted hover:text-ink transition-colors"
                >
                  {showNew ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="confirm-pw" className="block text-[11px] font-semibold text-muted uppercase tracking-wider">
                Confirmar Senha
              </label>
              <div className="relative">
                <input
                  id="confirm-pw"
                  type={showConfirm ? 'text' : 'password'}
                  required
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  className="input w-full pr-11"
                  placeholder="repita a nova senha"
                />
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={() => setShowConfirm((s) => !s)}
                  aria-label={showConfirm ? 'Ocultar senha' : 'Mostrar senha'}
                  className="absolute inset-y-0 right-0 w-11 flex items-center justify-center text-muted hover:text-ink transition-colors"
                >
                  {showConfirm ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <PasswordStrength password={newPassword} confirm={confirm} />

            {error && <p className="text-sm text-red-700 text-center" role="alert">{error}</p>}

            <button
              type="submit"
              disabled={loading || !canSubmit}
              className="btn-primary w-full tracking-widest py-2.5 mt-1 disabled:opacity-50 disabled:cursor-not-allowed"
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
