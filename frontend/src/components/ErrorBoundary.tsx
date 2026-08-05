import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  // Muda quando a rota muda; ao mudar, o boundary se reseta sozinho para que
  // navegar para outra aba recupere a UI sem exigir F5.
  resetKey?: unknown
}

interface State {
  hasError: boolean
}

/**
 * Captura exceções de render das páginas (ex.: API devolve campo em formato
 * inesperado) e mostra um fallback com "Tentar novamente" em vez de desmontar
 * toda a árvore do app — que deixaria o usuário numa tela branca sem navegação.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary]', error, errorInfo)
  }

  componentDidUpdate(prevProps: Props) {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false })
    }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-[60vh] flex flex-col items-center justify-center p-6 text-center">
          <h2 className="text-lg font-semibold text-ink">Ops! Ocorreu um erro ao carregar esta tela.</h2>
          <p className="text-sm text-muted-2 mt-1 mb-4">Ocorreu uma falha inesperada no processamento dos dados.</p>
          <button onClick={() => this.setState({ hasError: false })} className="btn-primary">
            Tentar novamente
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
