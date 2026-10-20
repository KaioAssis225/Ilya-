import { createContext, useContext } from 'react'
import type { LocaleValue } from '../contexts/LocaleContext'

export const LocaleContext = createContext<LocaleValue | null>(null)

export function useLocale() {
  const context = useContext(LocaleContext)
  if (!context) throw new Error('useLocale deve ser usado dentro de LocaleProvider')
  return context
}
