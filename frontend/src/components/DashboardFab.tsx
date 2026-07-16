import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { LayoutDashboard } from 'lucide-react'

export default function DashboardFab() {
  const navigate = useNavigate()
  const [switching, setSwitching] = useState(false)

  function handleClick() {
    if (switching) return
    setSwitching(true)
    // Wipe de troca de módulo — navega depois do overlay cobrir a tela,
    // para a transição não parecer um recarregamento abrupto de rota.
    setTimeout(() => navigate('/dashboard'), 220)
  }

  return (
    <>
      <button
        onClick={handleClick}
        aria-label="Abrir Dashboard BI"
        title="Dashboard BI"
        className="group fixed bottom-20 md:bottom-6 right-4 md:right-6 z-40 w-14 h-14 rounded-full flex items-center justify-center text-white shadow-lg transition-transform duration-200 active:scale-90 hover:scale-105"
        style={{ background: 'linear-gradient(135deg, #c8952e 0%, #8b6914 100%)' }}
      >
        <span className="absolute inset-0 rounded-full border-2 border-gold pointer-events-none opacity-0 group-hover:opacity-100 group-hover:[animation:fabRing_1.1s_ease-out_infinite]" />
        <LayoutDashboard className="w-6 h-6 relative transition-transform duration-300 group-hover:-rotate-6 group-hover:scale-110" />
      </button>

      {switching && (
        <div
          className="fixed inset-0 z-[110] pointer-events-none origin-left"
          style={{
            background: 'linear-gradient(90deg, #5a4508 0%, #8b6914 50%, #c8952e 100%)',
            animation: 'moduleWipe 0.5s cubic-bezier(0.65, 0, 0.35, 1) forwards',
          }}
        />
      )}
    </>
  )
}
