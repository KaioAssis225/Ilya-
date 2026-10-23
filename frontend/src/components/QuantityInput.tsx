import { useEffect, useRef, useState, type KeyboardEvent } from 'react'

interface QuantityInputProps {
  id?: string
  value: number
  /** Recebe só números válidos (≥ minValue). O chamador normaliza e limita. */
  onCommit: (value: number) => void
  /** Tapete (m²) aceita casas decimais digitadas à mão; o resto só inteiros. */
  allowDecimal: boolean
  max?: number | null
  ariaLabel: string
  className?: string
}

/**
 * Campo de quantidade que deixa apagar e redigitar.
 *
 * O carrinho só aceita números válidos, então um `<input value={qty}>`
 * controlado direto pelo carrinho voltava ao número antigo assim que o campo
 * ficava vazio. Aqui o texto digitado vive num rascunho; o carrinho só recebe
 * o valor quando ele é válido, e ao sair do campo o rascunho volta a mostrar o
 * valor gravado.
 *
 * Setinhas (as do campo e ↑/↓ do teclado) andam sempre em número inteiro:
 * de 5,02 sobem para 6 e descem para 5. Número quebrado em m² só digitando.
 */
export function QuantityInput({ id, value, onCommit, allowDecimal, max, ariaLabel, className = '' }: QuantityInputProps) {
  const [draft, setDraft] = useState(String(value))
  const focusedRef = useRef(false)
  const minValue = allowDecimal ? 0.01 : 1

  useEffect(() => {
    if (!focusedRef.current) setDraft(String(value))
  }, [value])

  function commitRaw(raw: string) {
    if (raw.trim() === '') return
    const parsed = Number(raw.replace(',', '.'))
    if (!Number.isFinite(parsed) || parsed < minValue) return
    onCommit(allowDecimal ? parsed : Math.round(parsed))
  }

  function stepWhole(direction: 1 | -1) {
    const current = Number(draft.replace(',', '.'))
    const base = Number.isFinite(current) && draft.trim() !== '' ? current : value
    let next = direction > 0 ? Math.floor(base) + 1 : Math.ceil(base) - 1
    if (next < 1) next = Math.max(1, Math.min(base, 1))
    if (max != null && next > max) next = max
    setDraft(String(next))
    onCommit(next)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
      event.preventDefault()
      stepWhole(event.key === 'ArrowUp' ? 1 : -1)
    }
  }

  return (
    <input
      id={id}
      type="number"
      // min/step inteiros fazem as setinhas do navegador pararem só em inteiros;
      // o valor quebrado digitado à mão continua aceito pelo commitRaw.
      min={1}
      step={1}
      max={max ?? undefined}
      inputMode={allowDecimal ? 'decimal' : 'numeric'}
      aria-label={ariaLabel}
      className={className}
      value={draft}
      onFocus={() => { focusedRef.current = true }}
      onBlur={() => {
        focusedRef.current = false
        setDraft(String(value))
      }}
      onKeyDown={handleKeyDown}
      onChange={(event) => {
        // "5," no meio da digitação vira badInput com value "" — ignora para
        // não apagar o que a pessoa está escrevendo.
        if (event.target.validity?.badInput) return
        setDraft(event.target.value)
        commitRaw(event.target.value)
      }}
    />
  )
}
