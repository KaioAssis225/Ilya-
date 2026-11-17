import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EuVatRatePanel from './EuVatRatePanel'
import { formatRate, parseRateInput } from '../lib/euVatRate'

const { apiGet, apiPut, platformGet, platformPut } = vi.hoisted(() => ({
  apiGet: vi.fn(), apiPut: vi.fn(), platformGet: vi.fn(), platformPut: vi.fn(),
}))

vi.mock('../lib/api', () => ({ default: { get: apiGet, put: apiPut } }))
vi.mock('../lib/platformApi', () => ({ default: { get: platformGet, put: platformPut } }))

const VIEW = {
  market: 'EU' as const,
  vat_rate: '23.00',
  can_edit: true,
  history: [{ changed_at: '2026-11-17T10:00:00Z', old_rate: '22.00', new_rate: '23.00', changed_by: 'Ana Admin' }],
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

describe('regras do campo de IVA', () => {
  it('formata a taxa sem zeros inúteis', () => {
    expect(formatRate('23.00')).toBe('23%')
    expect(formatRate('7.50')).toBe('7,5%')
    expect(formatRate(null)).toBe('—')
  })

  it('aceita 0 a 100 com até duas casas e recusa o resto', () => {
    expect(parseRateInput('23')).toBe(23)
    expect(parseRateInput('7,25')).toBe(7.25)
    expect(parseRateInput('0')).toBe(0)
    expect(parseRateInput('100')).toBe(100)
    for (const bad of ['', 'abc', '-1', '100,01', '23,123', '101']) expect(parseRateInput(bad)).toBeNull()
  })
})

describe('EuVatRatePanel', () => {
  it('mostra a taxa atual, o histórico e salva a nova taxa pelo servidor', async () => {
    apiGet.mockResolvedValue({ data: VIEW })
    apiPut.mockResolvedValue({ data: { ...VIEW, vat_rate: '21.50' } })
    render(<EuVatRatePanel scope="market" />)

    expect(await screen.findByTestId('eu-vat-current')).toHaveTextContent('23%')
    expect(screen.getByText('Ana Admin')).toBeInTheDocument()
    expect(apiGet).toHaveBeenCalledWith('/markets/EU/vat-rate')

    const input = screen.getByLabelText('Taxa de IVA (%)')
    const save = screen.getByRole('button', { name: 'Salvar' })
    expect(save).toBeDisabled()
    fireEvent.change(input, { target: { value: '21,5' } })
    expect(save).toBeEnabled()
    fireEvent.click(save)

    await waitFor(() => expect(apiPut).toHaveBeenCalledWith('/markets/EU/vat-rate', { vat_rate: 21.5 }))
    expect(await screen.findByTestId('eu-vat-current')).toHaveTextContent('21,5%')
    expect(screen.getByRole('status')).toHaveTextContent('Taxa de IVA salva.')
  })

  it('não deixa salvar valor inválido', async () => {
    apiGet.mockResolvedValue({ data: VIEW })
    render(<EuVatRatePanel scope="market" />)
    await screen.findByTestId('eu-vat-current')

    fireEvent.change(screen.getByLabelText('Taxa de IVA (%)'), { target: { value: '120' } })

    expect(screen.getByRole('button', { name: 'Salvar' })).toBeDisabled()
    expect(apiPut).not.toHaveBeenCalled()
  })

  it('quem não é admin só vê a taxa, sem campo nem botão', async () => {
    apiGet.mockResolvedValue({ data: { ...VIEW, can_edit: false, history: [] } })
    render(<EuVatRatePanel scope="market" />)

    expect(await screen.findByTestId('eu-vat-current')).toHaveTextContent('23%')
    expect(screen.queryByLabelText('Taxa de IVA (%)')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Salvar' })).not.toBeInTheDocument()
  })

  it('na Plataforma usa a rota da plataforma', async () => {
    platformGet.mockResolvedValue({ data: VIEW })
    render(<EuVatRatePanel scope="platform" />)

    await screen.findByTestId('eu-vat-current')
    expect(platformGet).toHaveBeenCalledWith('/markets/EU/vat-rate/platform')
    expect(apiGet).not.toHaveBeenCalled()
  })

  it('mostra o erro do servidor quando o salvamento falha', async () => {
    apiGet.mockResolvedValue({ data: VIEW })
    apiPut.mockRejectedValue({ response: { data: { detail: 'Somente o administrador do mercado europeu altera a taxa de IVA.' } } })
    render(<EuVatRatePanel scope="market" />)
    await screen.findByTestId('eu-vat-current')

    fireEvent.change(screen.getByLabelText('Taxa de IVA (%)'), { target: { value: '5' } })
    fireEvent.click(screen.getByRole('button', { name: 'Salvar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Somente o administrador')
  })
})
