import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router'
import { describe, expect, it } from 'vitest'
import DashboardFab from './DashboardFab'
import type { FabShortcut } from './DashboardFab'

function Where() {
  return <output data-testid="where">{useLocation().pathname}</output>
}

function renderFab(shortcuts?: FabShortcut[], mode: 'enter' | 'exit' = 'enter') {
  return render(
    <MemoryRouter initialEntries={['/produtos']}>
      <DashboardFab mode={mode} currentPath="/produtos" shortcuts={shortcuts} />
      <button type="button">Fora do menu</button>
      <Where />
    </MemoryRouter>,
  )
}

const trigger = () => screen.getByRole('button', { name: 'Atalhos rápidos' })

describe('DashboardFab — menu de atalhos em leque', () => {
  it('com os três atalhos, abre um menu com Dashboard, Armazém e Protótipo nessa ordem', async () => {
    renderFab(['dashboard', 'armazem', 'prototipo'])
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')

    await userEvent.click(trigger())

    expect(trigger()).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getAllByRole('menuitem').map(item => item.textContent)).toEqual(['Dashboard', 'Armazém', 'Protótipo'])
  })

  it('Armazém leva ao estoque do showroom e fecha o menu', async () => {
    renderFab(['dashboard', 'armazem', 'prototipo'])
    await userEvent.click(trigger())
    await userEvent.click(screen.getByRole('menuitem', { name: 'Armazém' }))
    expect(screen.getByTestId('where')).toHaveTextContent('/showrooms')
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
  })

  it('Protótipo leva à aba de protótipos', async () => {
    renderFab(['dashboard', 'armazem', 'prototipo'])
    await userEvent.click(trigger())
    await userEvent.click(screen.getByRole('menuitem', { name: 'Protótipo' }))
    expect(screen.getByTestId('where')).toHaveTextContent('/prototipos')
  })

  it('Dashboard guarda a rota de origem e vai para /dashboard', async () => {
    renderFab(['dashboard', 'armazem'])
    await userEvent.click(trigger())
    await userEvent.click(screen.getByRole('menuitem', { name: 'Dashboard' }))
    expect(sessionStorage.getItem('dashboard_return_to')).toBe('/produtos')
    expect(await screen.findByText('/dashboard', { selector: '[data-testid="where"]' })).toBeInTheDocument()
  })

  it('fecha com Esc devolvendo o foco ao botão', async () => {
    renderFab(['dashboard', 'armazem', 'prototipo'])
    await userEvent.click(trigger())
    expect(screen.getByRole('menuitem', { name: 'Dashboard' })).toHaveFocus()
    await userEvent.keyboard('{Escape}')
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
    expect(trigger()).toHaveFocus()
  })

  it('fecha com clique fora', async () => {
    renderFab(['dashboard', 'armazem', 'prototipo'])
    await userEvent.click(trigger())
    await userEvent.click(screen.getByRole('button', { name: 'Fora do menu' }))
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
  })

  it('clicar no ícone do botão (não só no botão) abre e mantém o menu aberto', async () => {
    renderFab(['dashboard', 'armazem', 'prototipo'])
    // O ícone troca por um X ao abrir; o <svg> clicado sai do DOM e isso não
    // pode contar como "clique fora".
    await userEvent.click(trigger().querySelector('svg')!)
    expect(trigger()).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getAllByRole('menuitem')).toHaveLength(3)
  })

  it('clicar de novo no botão fecha o menu', async () => {
    renderFab(['dashboard', 'armazem', 'prototipo'])
    await userEvent.click(trigger())
    await userEvent.click(trigger())
    expect(trigger()).toHaveAttribute('aria-expanded', 'false')
  })

  it('navega pelos itens com as setas', async () => {
    renderFab(['dashboard', 'armazem', 'prototipo'])
    await userEvent.click(trigger())
    await userEvent.keyboard('{ArrowDown}')
    expect(screen.getByRole('menuitem', { name: 'Armazém' })).toHaveFocus()
    await userEvent.keyboard('{ArrowUp}{ArrowUp}')
    expect(screen.getByRole('menuitem', { name: 'Protótipo' })).toHaveFocus()
  })

  it('marca como atual o atalho da página aberta', async () => {
    render(
      <MemoryRouter initialEntries={['/showrooms']}>
        <DashboardFab mode="enter" currentPath="/showrooms" shortcuts={['dashboard', 'armazem']} />
      </MemoryRouter>,
    )
    await userEvent.click(trigger())
    expect(screen.getByRole('menuitem', { name: 'Armazém' })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('menuitem', { name: 'Dashboard' })).not.toHaveAttribute('aria-current')
  })

  it('só com o Dashboard (BR) o botão vai direto, sem menu', async () => {
    renderFab(['dashboard'])
    const button = screen.getByRole('button', { name: 'Abrir Dashboard BI' })
    expect(button).not.toHaveAttribute('aria-expanded')
    expect(button).not.toHaveAttribute('aria-haspopup')
    await userEvent.click(button)
    expect(screen.queryAllByRole('menuitem')).toHaveLength(0)
    expect(await screen.findByText('/dashboard', { selector: '[data-testid="where"]' })).toBeInTheDocument()
  })

  it('sem a prop shortcuts mantém o comportamento antigo (Dashboard direto)', () => {
    renderFab(undefined)
    expect(screen.getByRole('button', { name: 'Abrir Dashboard BI' })).toBeInTheDocument()
  })

  it('com um único atalho que não é o Dashboard, vai direto a ele', async () => {
    renderFab(['prototipo'])
    await userEvent.click(screen.getByRole('button', { name: 'Abrir Protótipos' }))
    expect(screen.getByTestId('where')).toHaveTextContent('/prototipos')
  })

  it('no modo de saída do Dashboard continua sendo um botão de fechar, sem menu', () => {
    renderFab(['dashboard', 'armazem', 'prototipo'], 'exit')
    expect(screen.getByRole('button', { name: 'Fechar Dashboard BI' })).not.toHaveAttribute('aria-expanded')
  })
})
