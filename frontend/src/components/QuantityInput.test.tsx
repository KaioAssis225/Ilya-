import { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { QuantityInput } from './QuantityInput'

function Harness({ initial, allowDecimal, max, onCommit }: {
  initial: number
  allowDecimal: boolean
  max?: number | null
  onCommit?: (value: number) => void
}) {
  const [value, setValue] = useState(initial)
  return (
    <>
      <QuantityInput
        value={value}
        allowDecimal={allowDecimal}
        max={max}
        ariaLabel="M² — Tapete"
        onCommit={(next) => { onCommit?.(next); setValue(next) }}
      />
      <output data-testid="gravado">{value}</output>
    </>
  )
}

describe('QuantityInput', () => {
  it('deixa apagar o número e digitar outro (antes voltava ao valor antigo)', () => {
    const onCommit = vi.fn()
    render(<Harness initial={5.02} allowDecimal onCommit={onCommit} />)
    const input = screen.getByLabelText('M² — Tapete') as HTMLInputElement

    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: '' } })
    expect(input.value).toBe('')
    expect(onCommit).not.toHaveBeenCalled()
    expect(screen.getByTestId('gravado').textContent).toBe('5.02')

    fireEvent.change(input, { target: { value: '7.5' } })
    expect(onCommit).toHaveBeenLastCalledWith(7.5)
    expect(screen.getByTestId('gravado').textContent).toBe('7.5')
  })

  it('ao sair do campo vazio, volta a mostrar o valor gravado', () => {
    render(<Harness initial={3} allowDecimal />)
    const input = screen.getByLabelText('M² — Tapete') as HTMLInputElement

    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: '' } })
    fireEvent.blur(input)
    expect(input.value).toBe('3')
  })

  it('setinhas andam em número inteiro: 5,02 sobe para 6 e desce para 5', () => {
    const onCommit = vi.fn()
    render(<Harness initial={5.02} allowDecimal onCommit={onCommit} />)
    const input = screen.getByLabelText('M² — Tapete') as HTMLInputElement

    fireEvent.keyDown(input, { key: 'ArrowUp' })
    expect(onCommit).toHaveBeenLastCalledWith(6)
    expect(input.value).toBe('6')

    fireEvent.keyDown(input, { key: 'ArrowDown' })
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    expect(onCommit).toHaveBeenLastCalledWith(4)

    // Partindo de valor quebrado, descer vai para o inteiro de baixo.
    fireEvent.change(input, { target: { value: '5.02' } })
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    expect(onCommit).toHaveBeenLastCalledWith(5)
  })

  it('setinha não passa do máximo nem desce abaixo de 1', () => {
    const onCommit = vi.fn()
    render(<Harness initial={10} allowDecimal max={10} onCommit={onCommit} />)
    const input = screen.getByLabelText('M² — Tapete') as HTMLInputElement

    fireEvent.keyDown(input, { key: 'ArrowUp' })
    expect(onCommit).toHaveBeenLastCalledWith(10)

    fireEvent.change(input, { target: { value: '1' } })
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    expect(onCommit).toHaveBeenLastCalledWith(1)
  })

  it('produto comum arredonda para inteiro o que for digitado', () => {
    const onCommit = vi.fn()
    render(<Harness initial={2} allowDecimal={false} onCommit={onCommit} />)
    const input = screen.getByLabelText('M² — Tapete') as HTMLInputElement

    fireEvent.change(input, { target: { value: '2.7' } })
    expect(onCommit).toHaveBeenLastCalledWith(3)
  })
})
