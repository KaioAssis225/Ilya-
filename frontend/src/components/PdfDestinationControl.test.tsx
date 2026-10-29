import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LocaleContext } from '../hooks/useLocale'
import { PdfDestinationControl } from './PdfDestinationControl'

const pdfDestination = vi.hoisted(() => ({
  supported: true,
  folderName: null as string | null,
  pick: vi.fn(),
  clear: vi.fn(),
}))

vi.mock('../lib/pdfDestination', () => ({
  isFolderPickerSupported: () => pdfDestination.supported,
  loadDestinationFolderName: async () => pdfDestination.folderName,
  pickDestinationFolder: pdfDestination.pick,
  clearDestinationFolder: pdfDestination.clear,
}))

function renderControl(locale: 'pt-PT' | 'en-GB' = 'pt-PT') {
  return render(
    <LocaleContext.Provider value={{ locale, setLocale: () => undefined, t: key => key }}>
      <PdfDestinationControl userKey="user-1" />
    </LocaleContext.Provider>,
  )
}

describe('PdfDestinationControl', () => {
  beforeEach(() => {
    pdfDestination.supported = true
    pdfDestination.folderName = null
    pdfDestination.pick.mockReset()
    pdfDestination.clear.mockReset()
  })

  it('sem pasta escolhida mostra Downloads (padrão) e oferece escolher', async () => {
    renderControl()

    expect(screen.getByText('Downloads (padrão)')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Escolher pasta' })).toBeEnabled()
    expect(screen.queryByRole('button', { name: 'Usar Downloads' })).not.toBeInTheDocument()
  })

  it('escolher uma pasta mostra o nome e passa a oferecer Alterar e Usar Downloads', async () => {
    pdfDestination.pick.mockResolvedValue({ status: 'chosen', folderName: 'Orçamentos 2026' })
    renderControl()

    fireEvent.click(await screen.findByRole('button', { name: 'Escolher pasta' }))

    expect(await screen.findByText('Orçamentos 2026')).toBeInTheDocument()
    expect(pdfDestination.pick).toHaveBeenCalledWith('user-1')
    expect(screen.getByRole('button', { name: 'Alterar' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Usar Downloads' })).toBeInTheDocument()
  })

  it('lembra a pasta guardada e Usar Downloads volta ao padrão', async () => {
    pdfDestination.folderName = 'Pasta guardada'
    pdfDestination.clear.mockResolvedValue(true)
    renderControl()

    expect(await screen.findByText('Pasta guardada')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Usar Downloads' }))

    await waitFor(() => expect(screen.getByText('Downloads (padrão)')).toBeInTheDocument())
    expect(pdfDestination.clear).toHaveBeenCalledWith('user-1')
  })

  it('cancelar o seletor não muda nada; falha ao guardar avisa', async () => {
    pdfDestination.pick.mockResolvedValueOnce({ status: 'cancelled' })
    renderControl()

    fireEvent.click(await screen.findByRole('button', { name: 'Escolher pasta' }))
    await waitFor(() => expect(pdfDestination.pick).toHaveBeenCalledTimes(1))
    expect(screen.getByText('Downloads (padrão)')).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()

    pdfDestination.pick.mockResolvedValueOnce({ status: 'error' })
    fireEvent.click(screen.getByRole('button', { name: 'Escolher pasta' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Não foi possível guardar a pasta neste navegador.')
  })

  it('navegador sem suporte: controle desabilitado com a dica visível', () => {
    pdfDestination.supported = false
    renderControl()

    expect(screen.getByRole('button', { name: 'Escolher pasta' })).toBeDisabled()
    expect(screen.getByText('Disponível no Chrome/Edge no computador')).toBeInTheDocument()
    expect(screen.getByText('Downloads (padrão)')).toBeInTheDocument()
  })

  it('em inglês usa os textos en-GB', async () => {
    renderControl('en-GB')

    expect(screen.getByText('Save folder:')).toBeInTheDocument()
    expect(screen.getByText('Downloads (default)')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Choose folder' })).toBeInTheDocument()
  })
})
