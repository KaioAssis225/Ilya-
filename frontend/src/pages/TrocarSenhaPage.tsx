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
    <div className="min-h-screen flex items-center justify-center bg-[#f5f0eb]">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-[#8b6914]/10 mb-4">
            <ShieldCheck className="w-7 h-7 text-[#8b6914]" />
          </div>
          <h1 className="text-2xl font-medium text-[#2c2420]" style={{ fontFamily: "'Cormorant Garamond', Georgia, serif" }}>
            Troca de Senha Obrigatória
          </h1>
          <p className="mt-2 text-sm text-[#8a7e72] leading-relaxed">
            Por segurança, defina uma nova senha antes de acessar o sistema.
          </p>
          <div className="mt-4 mx-auto w-12 h-[2px] bg-[#8b6914]" />
        </div>

        <div className="bg-white rounded-lg shadow-md border border-[#e8e0d6] px-8 py-8">
          {user && (
            <p className="text-xs text-[#8a7e72] text-center mb-5">
              Bem-vindo(a), <strong className="text-[#2c2420]">{user.full_name}</strong>
            </p>
          )}
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-xs font-medium text-[#8a7e72] uppercase tracking-widest mb-1">
                Nova Senha
              </label>
              <input
                type="password"
                required
                autoFocus
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full border border-[#e8e0d6] rounded-md px-3 py-2.5 text-sm text-[#2c2420] bg-[#faf8f5] focus:outline-none focus:border-[#8b6914] focus:ring-1 focus:ring-[#8b6914] transition"
                placeholder="mínimo 8 caracteres"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-[#8a7e72] uppercase tracking-widest mb-1">
                Confirmar Senha
              </label>
              <input
                type="password"
                required
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="w-full border border-[#e8e0d6] rounded-md px-3 py-2.5 text-sm text-[#2c2420] bg-[#faf8f5] focus:outline-none focus:border-[#8b6914] focus:ring-1 focus:ring-[#8b6914] transition"
                placeholder="repita a nova senha"
              />
            </div>

            {error && <p className="text-sm text-red-600 text-center">{error}</p>}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-[#8b6914] hover:bg-[#7a5c10] text-white text-sm font-medium uppercase tracking-widest py-2.5 rounded-md transition disabled:opacity-60 disabled:cursor-not-allowed mt-2 flex items-center justify-center gap-2"
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
