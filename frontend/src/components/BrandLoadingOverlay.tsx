import type { CSSProperties } from 'react'

// Overlay de carregamento assinatura ILYA (halo pulsante + wordmark com sweep
// + subtítulo + linha de progresso). Antes duplicado em cinco telas, cada uma
// com hexadecimais e durações próprias. As cores vêm dos tokens de ouro, então
// Portugal recebe o Jade automaticamente. `prefers-reduced-motion` é tratado
// pela regra global de index.css (animações viram estado final estático).

interface BrandLoadingOverlayProps {
  label: string
  /** Duração da linha de progresso, em segundos. */
  progressDuration?: number
  className?: string
  style?: CSSProperties
}

const WORDMARK_STYLE: CSSProperties = {
  backgroundImage:
    'linear-gradient(90deg, var(--color-gold-800) 0%, var(--color-gold) 25%, var(--color-gold-highlight) 50%, var(--color-gold) 75%, var(--color-gold-800) 100%)',
  backgroundSize: '200% auto',
  WebkitBackgroundClip: 'text',
  WebkitTextFillColor: 'transparent',
  backgroundClip: 'text',
  animation: 'lightSweep 2.4s linear infinite',
}

export function BrandLoadingOverlay({ label, progressDuration = 3, className = '', style }: BrandLoadingOverlayProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`fixed inset-0 z-loading flex flex-col items-center justify-center bg-bg/90 backdrop-blur-sm ${className}`}
      style={style}
    >
      <div
        aria-hidden="true"
        className="absolute w-[520px] max-w-[140vw] h-[520px] max-h-[140vw] rounded-full pointer-events-none"
        style={{
          background: 'radial-gradient(circle, color-mix(in srgb, var(--color-gold) 18%, transparent) 0%, transparent 68%)',
          animation: 'pulseRadial 2.2s ease-in-out infinite',
        }}
      />
      <p
        aria-hidden="true"
        className="relative font-display text-[50px] sm:text-[80px] leading-none tracking-[0.35em] font-light select-none"
        style={WORDMARK_STYLE}
      >
        ILYA
      </p>
      <p
        className="mt-5 text-[11px] tracking-[0.55em] uppercase font-semibold text-gold"
        style={{ animation: 'fadeInOut 1.8s ease-in-out infinite' }}
      >
        {label}
      </p>
      <div aria-hidden="true" className="mt-9 w-52 h-px bg-gold/25 overflow-hidden rounded-full">
        <div
          className="h-full rounded-full"
          style={{
            background: 'linear-gradient(90deg, var(--color-gold-800), var(--color-gold-highlight), var(--color-gold-800))',
            animation: `progressLine ${progressDuration}s linear forwards`,
          }}
        />
      </div>
    </div>
  )
}
