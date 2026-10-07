import { useCallback, useContext } from 'react'
import { LocaleContext } from '../contexts/LocaleContext'
import { translateCadastro, type CadastroTextVars } from '../lib/cadastroText'

/** Tradutor da tela de Cadastros. Fora de en-GB devolve o texto sem mudança. */
export function useCadastroText() {
  // Fora de um LocaleProvider (componente isolado) vale o português.
  const locale = useContext(LocaleContext)?.locale ?? 'pt-PT'
  return useCallback(
    (pt: string, vars?: CadastroTextVars) => translateCadastro(locale, pt, vars),
    [locale],
  )
}
