import { useState, useRef, useEffect } from 'react'
import { X, PenLine, Check } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'

const ROLE_LABELS: Record<string, string> = {
  admin: 'Administrador',
  vendedor: 'Vendedor',
  representante: 'Representante',
  cadastros: 'Cadastros',
  produtos: 'Produtos',
}

export default function ProfileModal({ onClose }: { onClose: () => void }) {
  const { user } = useAuth()
  if (!user) return null

  const isCliente = user.role === 'vendedor' && !!user.linked_id
  const profileSigKey = `profile_signature_${user.id}`

  const [sigData, setSigData] = useState<string | null>(() => localStorage.getItem(profileSigKey))
  const [sigModalOpen, setSigModalOpen] = useState(false)
  const [saved, setSaved] = useState(false)
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
    localStorage.setItem(profileSigKey, data)
    setSigData(data)
    setSigModalOpen(false)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-[#1a1410]/60 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 p-6" onClick={(e) => e.stopPropagation()}>

        <div className="flex items-start justify-between mb-5">
          <div>
            <h3 className="text-lg font-semibold text-[#2c2420]">Minha Conta</h3>
            <span className="text-xs text-[#8b6914] uppercase tracking-wider font-medium">
              {ROLE_LABELS[user.role] ?? user.role}
            </span>
          </div>
          <button onClick={onClose} className="text-[#9d8d81] hover:text-[#2c2420] transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {isCliente && (
          <div className="mb-4 px-3 py-2 bg-[#f8f6f2] border border-[#e8e0d6] rounded-lg">
            <p className="text-xs text-[#9d8d81]">Dados em modo somente leitura</p>
          </div>
        )}

        <div className="space-y-3 mb-6">
          <div>
            <label className="text-xs text-[#9d8d81] block mb-0.5">Nome completo</label>
            <p className="text-sm text-[#2c2420] font-medium border border-[#e8e0d6] rounded-lg px-3 py-2 bg-[#f8f6f2]">
              {user.full_name}
            </p>
          </div>
          <div>
            <label className="text-xs text-[#9d8d81] block mb-0.5">E-mail</label>
            <p className="text-sm text-[#2c2420] border border-[#e8e0d6] rounded-lg px-3 py-2 bg-[#f8f6f2]">
              {user.email}
            </p>
          </div>
          {user.username && (
            <div>
              <label className="text-xs text-[#9d8d81] block mb-0.5">Usuário</label>
              <p className="text-sm text-[#2c2420] font-mono border border-[#e8e0d6] rounded-lg px-3 py-2 bg-[#f8f6f2]">
                {user.username}
              </p>
            </div>
          )}
        </div>

        {/* Signature */}
        <div className="border-t border-[#e8e0d6] pt-4">
          <p className="text-xs font-semibold text-[#9d8d81] uppercase tracking-wider mb-3">Assinatura Pessoal</p>
          {sigData ? (
            <div className="flex flex-col items-center gap-2">
              <div className="w-full border border-[#e8e0d6] rounded-xl px-4 py-3 bg-[#fafaf9] flex items-center justify-center">
                <img src={sigData} alt="Assinatura" className="max-h-16 max-w-full" />
              </div>
              {saved && (
                <p className="text-xs text-green-600 flex items-center gap-1">
                  <Check className="w-3 h-3" /> Salva com sucesso!
                </p>
              )}
              <button
                onClick={() => setSigModalOpen(true)}
                className="text-xs text-[#9d8d81] hover:text-[#8b6914] underline transition-colors"
              >
                Alterar assinatura
              </button>
            </div>
          ) : (
            <button
              onClick={() => setSigModalOpen(true)}
              className="w-full flex items-center justify-center gap-2 py-3 border border-dashed border-[#c8a84b] text-[#8b6914] rounded-xl hover:bg-[#fdf9f0] transition-colors text-sm font-medium"
            >
              <PenLine className="w-4 h-4" />
              Adicionar Assinatura
            </button>
          )}
        </div>
      </div>

      {/* Canvas modal */}
      {sigModalOpen && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center bg-[#1a1410]/80 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h4 className="text-base font-semibold text-[#2c2420]">Assinatura Pessoal</h4>
              <button onClick={() => setSigModalOpen(false)} className="text-[#9d8d81] hover:text-[#2c2420]">
                <X className="w-5 h-5" />
              </button>
            </div>
            <p className="text-xs text-[#9d8d81] mb-3">Assine no campo abaixo com o mouse ou dedo.</p>
            <canvas
              ref={canvasRef}
              width={420}
              height={160}
              className="w-full border border-[#e8e0d6] rounded-xl bg-[#fafaf9] cursor-crosshair touch-none"
            />
            <div className="flex gap-2 mt-4">
              <button
                onClick={() => canvasRef.current?.getContext('2d')?.clearRect(0, 0, 420, 160)}
                className="flex-1 py-2 border border-[#e8e0d6] text-[#9d8d81] rounded-lg text-sm hover:bg-[#f8f6f2] transition-colors"
              >
                Limpar
              </button>
              <button
                onClick={() => setSigModalOpen(false)}
                className="flex-1 py-2 border border-[#e8e0d6] text-[#9d8d81] rounded-lg text-sm hover:bg-[#f8f6f2] transition-colors"
              >
                Cancelar
              </button>
              <button
                onClick={confirmSig}
                className="flex-1 py-2 bg-[#8b6914] text-white rounded-lg text-sm font-medium hover:bg-[#7a5c10] transition-colors"
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
