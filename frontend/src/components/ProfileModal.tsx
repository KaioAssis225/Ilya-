import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import { X, PenLine, Check, Eye, EyeOff, KeyRound, Trash2, AlertTriangle, Download, LogOut } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import api from '../lib/api'
import { getProfileSignature, setProfileSignature } from '../lib/signatureMemory'

const ROLE_LABELS: Record<string, string> = {
  admin: 'Administrador',
  vendedor: 'Vendedor',
  representante: 'Representante',
  cadastros: 'Cadastros',
  produtos: 'Produtos',
  cliente: 'Cliente',
  executivo: 'Executivo',
}

export default function ProfileModal({ onClose }: { onClose: () => void }) {
  const { user, logout } = useAuth()
  if (!user) return null
  const userId = user.id

  const isCliente = user.role === 'cliente' || (user.role === 'vendedor' && !!user.linked_id)
  const [sigData, setSigData] = useState<string | null>(() => getProfileSignature(user.id))
  const [sigModalOpen, setSigModalOpen] = useState(false)
  const [saved, setSaved] = useState(false)

  // Bloco 93: alteração de senha
  const [pwOpen, setPwOpen] = useState(false)
  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [showCurPw, setShowCurPw] = useState(false)
  const [showNewPw, setShowNewPw] = useState(false)
  const [pwSaving, setPwSaving] = useState(false)
  const [pwError, setPwError] = useState('')

  // Bloco 93: exclusão da própria conta
  const [delOpen, setDelOpen] = useState(false)
  const [delBusy, setDelBusy] = useState(false)
  const [delError, setDelError] = useState('')

  const [exportOpen, setExportOpen] = useState(false)
  const [exportPassword, setExportPassword] = useState('')
  const [exportBusy, setExportBusy] = useState(false)
  const [exportError, setExportError] = useState('')
  const [logoutAllBusy, setLogoutAllBusy] = useState(false)

  async function handleChangePassword() {
    if (!currentPw || !newPw) return
    setPwSaving(true)
    setPwError('')
    try {
      await api.post('/auth/change-password', { current_password: currentPw, new_password: newPw })
      await logout()
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 401) {
        setPwError('Senha atual incorreta.')
      } else if (axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string') {
        setPwError(err.response.data.detail)
      } else {
        setPwError('Não foi possível alterar a senha. Tente novamente.')
      }
    } finally {
      setPwSaving(false)
    }
  }

  async function handleDeleteAccount() {
    setDelBusy(true)
    setDelError('')
    try {
      await api.delete('/auth/me')
      await logout()
    } catch (err) {
      if (axios.isAxiosError(err) && typeof err.response?.data?.detail === 'string') {
        setDelError(err.response.data.detail)
      } else {
        setDelError('Não foi possível excluir a conta. Tente novamente.')
      }
      setDelBusy(false)
    }
  }

  async function handleExportData() {
    if (!exportPassword) return
    setExportBusy(true)
    setExportError('')
    try {
      const response = await api.post(
        '/auth/my-data/export',
        { password: exportPassword },
        { responseType: 'blob' },
      )
      const url = URL.createObjectURL(response.data)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'meus-dados-ilya.json'
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
      setExportPassword('')
      setExportOpen(false)
    } catch (err) {
      setExportError(
        axios.isAxiosError(err) && err.response?.status === 401
          ? 'Senha incorreta.'
          : 'Não foi possível gerar a exportação.',
      )
    } finally {
      setExportBusy(false)
    }
  }

  async function handleLogoutAll() {
    setLogoutAllBusy(true)
    try {
      await api.post('/auth/logout-all')
    } finally {
      await logout()
      setLogoutAllBusy(false)
    }
  }
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const isDrawingRef = useRef(false)

  useEffect(() => {
    if (!sigModalOpen || !canvasRef.current) return
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')!
    ctx.strokeStyle = '#2c2420'
    ctx.lineWidth = 2
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'

    function getXY(e: TouchEvent | MouseEvent) {
      const rect = canvas.getBoundingClientRect()
      if ('touches' in e) {
        return { x: (e as TouchEvent).touches[0].clientX - rect.left, y: (e as TouchEvent).touches[0].clientY - rect.top }
      }
      return { x: (e as MouseEvent).clientX - rect.left, y: (e as MouseEvent).clientY - rect.top }
    }
    function onStart(e: TouchEvent | MouseEvent) {
      e.preventDefault(); isDrawingRef.current = true
      const { x, y } = getXY(e); ctx.beginPath(); ctx.moveTo(x, y)
    }
    function onMove(e: TouchEvent | MouseEvent) {
      e.preventDefault(); if (!isDrawingRef.current) return
      const { x, y } = getXY(e); ctx.lineTo(x, y); ctx.stroke()
    }
    function onEnd() { isDrawingRef.current = false }

    canvas.addEventListener('mousedown', onStart)
    canvas.addEventListener('mousemove', onMove)
    canvas.addEventListener('mouseup', onEnd)
    canvas.addEventListener('touchstart', onStart, { passive: false })
    canvas.addEventListener('touchmove', onMove, { passive: false })
    canvas.addEventListener('touchend', onEnd)
    return () => {
      canvas.removeEventListener('mousedown', onStart)
      canvas.removeEventListener('mousemove', onMove)
      canvas.removeEventListener('mouseup', onEnd)
      canvas.removeEventListener('touchstart', onStart)
      canvas.removeEventListener('touchmove', onMove)
      canvas.removeEventListener('touchend', onEnd)
    }
  }, [sigModalOpen])

  function confirmSig() {
    const data = canvasRef.current!.toDataURL('image/png')
    setProfileSignature(userId, data)
    setSigData(data)
    setSigModalOpen(false)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-scrim/60 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 p-6 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>

        <div className="flex items-start justify-between mb-5">
          <div>
            <h3 className="text-lg font-semibold text-ink">Minha Conta</h3>
            <span className="text-xs text-gold uppercase tracking-wider font-medium">
              {ROLE_LABELS[user.role] ?? user.role}
            </span>
          </div>
          <button onClick={onClose} className="text-muted hover:text-ink transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {isCliente && (
          <div className="mb-4 px-3 py-2 bg-bg border border-line rounded-lg">
            <p className="text-xs text-muted">Dados em modo somente leitura</p>
          </div>
        )}

        <div className="space-y-3 mb-6">
          <div>
            <label className="text-xs text-muted block mb-0.5">Nome completo</label>
            <p className="text-sm text-ink font-medium border border-line rounded-lg px-3 py-2 bg-bg">
              {user.full_name}
            </p>
          </div>
          <div>
            <label className="text-xs text-muted block mb-0.5">E-mail</label>
            <p className="text-sm text-ink border border-line rounded-lg px-3 py-2 bg-bg">
              {user.email}
            </p>
          </div>
          {user.username && (
            <div>
              <label className="text-xs text-muted block mb-0.5">Usuário</label>
              <p className="text-sm text-ink font-mono border border-line rounded-lg px-3 py-2 bg-bg">
                {user.username}
              </p>
            </div>
          )}
        </div>

        {/* Signature */}
        <div className="border-t border-line pt-4">
          <p className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">Assinatura Pessoal</p>
          {sigData ? (
            <div className="flex flex-col items-center gap-2">
              <div className="w-full border border-line rounded-xl px-4 py-3 bg-[#fafaf9] flex items-center justify-center">
                <img src={sigData} alt="Assinatura" className="max-h-16 max-w-full" />
              </div>
              {saved && (
                <p className="text-xs text-green-600 flex items-center gap-1">
                  <Check className="w-3 h-3" /> Disponível somente nesta sessão.
                </p>
              )}
              <button
                onClick={() => setSigModalOpen(true)}
                className="text-xs text-muted hover:text-gold underline transition-colors"
              >
                Alterar assinatura
              </button>
            </div>
          ) : (
            <button
              onClick={() => setSigModalOpen(true)}
              className="w-full flex items-center justify-center gap-2 py-3 border border-dashed border-gold-soft text-gold rounded-xl hover:bg-[#fdf9f0] transition-colors text-sm font-medium"
            >
              <PenLine className="w-4 h-4" />
              Adicionar Assinatura
            </button>
          )}
        </div>

        {/* Segurança (Bloco 93) */}
        <div className="border-t border-line pt-4 mt-4">
          <p className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">Segurança</p>

          {!pwOpen ? (
            <button
              onClick={() => { setPwOpen(true); setPwError('') }}
              className="w-full flex items-center justify-center gap-2 py-2.5 border border-line text-ink-2 rounded-xl hover:bg-bg transition-colors text-sm font-medium"
            >
              <KeyRound className="w-4 h-4" />
              Alterar Senha
            </button>
          ) : (
            <div className="space-y-3 border border-line rounded-xl p-4 bg-bg">
              <div>
                <label htmlFor="pw-atual" className="text-xs text-muted block mb-1">Senha atual</label>
                <div className="relative">
                  <input
                    id="pw-atual"
                    type={showCurPw ? 'text' : 'password'}
                    value={currentPw}
                    onChange={(e) => setCurrentPw(e.target.value)}
                    className="input w-full pr-11"
                    placeholder="••••••••"
                    autoComplete="current-password"
                  />
                  <button type="button" onClick={() => setShowCurPw(s => !s)} tabIndex={-1}
                    aria-label={showCurPw ? 'Ocultar senha' : 'Mostrar senha'}
                    className="absolute inset-y-0 right-0 w-11 flex items-center justify-center text-muted hover:text-ink transition-colors">
                    {showCurPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
              <div>
                <label htmlFor="pw-nova" className="text-xs text-muted block mb-1">Nova senha</label>
                <div className="relative">
                  <input
                    id="pw-nova"
                    type={showNewPw ? 'text' : 'password'}
                    value={newPw}
                    onChange={(e) => setNewPw(e.target.value)}
                    className="input w-full pr-11"
                    placeholder="Mín. 8 caracteres, maiúscula, minúscula e número"
                    autoComplete="new-password"
                  />
                  <button type="button" onClick={() => setShowNewPw(s => !s)} tabIndex={-1}
                    aria-label={showNewPw ? 'Ocultar senha' : 'Mostrar senha'}
                    className="absolute inset-y-0 right-0 w-11 flex items-center justify-center text-muted hover:text-ink transition-colors">
                    {showNewPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
              {pwError && <p className="text-xs text-red-700" role="alert">{pwError}</p>}
              <div className="flex gap-2">
                <button
                  onClick={() => { setPwOpen(false); setCurrentPw(''); setNewPw(''); setPwError('') }}
                  className="flex-1 py-2 border border-line text-muted rounded-lg text-sm hover:bg-white transition-colors"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleChangePassword}
                  disabled={pwSaving || !currentPw || !newPw}
                  className="flex-1 py-2 bg-gold text-white rounded-lg text-sm font-medium hover:bg-gold-600 transition-colors disabled:opacity-50"
                >
                  {pwSaving ? 'Salvando…' : 'Salvar'}
                </button>
              </div>
            </div>
          )}

          <button
            onClick={() => { setDelOpen(true); setDelError('') }}
            className="mt-3 w-full flex items-center justify-center gap-2 py-2.5 border border-red-200 text-red-700 rounded-xl hover:bg-red-50 transition-colors text-sm font-medium"
          >
            <Trash2 className="w-4 h-4" />
            Excluir Minha Conta
          </button>
        </div>

        <div className="border-t border-line pt-4 mt-4">
          <p className="text-xs font-semibold text-muted uppercase tracking-wider mb-3">Privacidade e sessões</p>
          {!exportOpen ? (
            <button
              onClick={() => { setExportOpen(true); setExportError('') }}
              className="w-full flex items-center justify-center gap-2 py-2.5 border border-line text-ink-2 rounded-xl hover:bg-bg transition-colors text-sm font-medium"
            >
              <Download className="w-4 h-4" />
              Baixar Meus Dados
            </button>
          ) : (
            <div className="space-y-3 border border-line rounded-xl p-4 bg-bg">
              <p className="text-xs text-muted">Confirme sua senha para gerar o arquivo JSON.</p>
              <input
                type="password"
                value={exportPassword}
                onChange={(e) => setExportPassword(e.target.value)}
                className="input w-full"
                placeholder="Senha atual"
                autoComplete="current-password"
              />
              {exportError && <p className="text-xs text-red-700" role="alert">{exportError}</p>}
              <div className="flex gap-2">
                <button
                  onClick={() => { setExportOpen(false); setExportPassword(''); setExportError('') }}
                  className="flex-1 py-2 border border-line text-muted rounded-lg text-sm hover:bg-white"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleExportData}
                  disabled={exportBusy || !exportPassword}
                  className="flex-1 py-2 bg-gold text-white rounded-lg text-sm font-medium disabled:opacity-50"
                >
                  {exportBusy ? 'Gerando…' : 'Baixar'}
                </button>
              </div>
            </div>
          )}
          <button
            onClick={handleLogoutAll}
            disabled={logoutAllBusy}
            className="mt-3 w-full flex items-center justify-center gap-2 py-2.5 border border-line text-ink-2 rounded-xl hover:bg-bg transition-colors text-sm font-medium disabled:opacity-50"
          >
            <LogOut className="w-4 h-4" />
            {logoutAllBusy ? 'Encerrando…' : 'Encerrar Todas as Sessões'}
          </button>
          <a href="/privacy-policy" className="mt-3 block text-center text-xs text-gold underline">
            Consultar Política de Privacidade
          </a>
        </div>
      </div>

      {/* Confirmação de exclusão de conta (Bloco 93) */}
      {delOpen && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center bg-scrim/80 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-sm mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-50 flex items-center justify-center flex-shrink-0">
                <AlertTriangle className="w-5 h-5 text-red-600" />
              </div>
              <div>
                <h4 className="text-base font-semibold text-ink">Excluir sua conta?</h4>
                <p className="text-sm text-muted-2 mt-1 leading-snug">
                  Esta ação é <strong>permanente</strong>. Seu acesso será removido imediatamente
                  e todas as suas sessões serão encerradas.
                </p>
              </div>
            </div>
            {delError && <p className="text-xs text-red-700 mb-3" role="alert">{delError}</p>}
            <div className="flex gap-2">
              <button
                onClick={() => setDelOpen(false)}
                disabled={delBusy}
                className="flex-1 py-2 border border-line text-muted rounded-lg text-sm hover:bg-bg transition-colors disabled:opacity-50"
              >
                Cancelar
              </button>
              <button
                onClick={handleDeleteAccount}
                disabled={delBusy}
                className="flex-1 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition-colors disabled:opacity-50"
              >
                {delBusy ? 'Excluindo…' : 'Excluir Conta'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Canvas modal */}
      {sigModalOpen && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center bg-scrim/80 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h4 className="text-base font-semibold text-ink">Assinatura Pessoal</h4>
              <button onClick={() => setSigModalOpen(false)} className="text-muted hover:text-ink">
                <X className="w-5 h-5" />
              </button>
            </div>
            <p className="text-xs text-muted mb-3">Assine no campo abaixo com o mouse ou dedo.</p>
            <canvas
              ref={canvasRef}
              width={420}
              height={160}
              className="w-full border border-line rounded-xl bg-[#fafaf9] cursor-crosshair touch-none"
            />
            <div className="flex gap-2 mt-4">
              <button
                onClick={() => canvasRef.current?.getContext('2d')?.clearRect(0, 0, 420, 160)}
                className="flex-1 py-2 border border-line text-muted rounded-lg text-sm hover:bg-bg transition-colors"
              >
                Limpar
              </button>
              <button
                onClick={() => setSigModalOpen(false)}
                className="flex-1 py-2 border border-line text-muted rounded-lg text-sm hover:bg-bg transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={confirmSig}
                className="flex-1 py-2 bg-gold text-white rounded-lg text-sm font-medium hover:bg-gold-600 transition-colors"
              >
                Confirmar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
