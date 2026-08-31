import { useContext } from 'react'
import { LocaleContext } from '../contexts/LocaleContext'

export function useLocale() {
  const context = useContext(LocaleContext)
  if (!context) throw new Error('useLocale deve ser usado dentro de LocaleProvider')
  return context
}
