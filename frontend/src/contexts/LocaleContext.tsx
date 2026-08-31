import { createContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useAuth } from '../hooks/useAuth'

export type AppLocale = 'pt-PT' | 'en-GB'

const messages = {
  'pt-PT': {
    products: 'Produtos', quote: 'Novo orçamento', orders: 'Pedidos', registrations: 'Cadastros',
    admin: 'Administração', logout: 'Sair', notifications: 'Notificações', noNotifications: 'Sem notificações.',
    mainNavigation: 'Navegação principal', skipContent: 'Saltar para o conteúdo',
    catalogTitle: 'Catálogo de produtos', catalogSubtitle: 'Selecione um produto para adicionar ao orçamento',
    searchProducts: 'Pesquisar produtos', searchPlaceholder: 'Pesquisar por código ou designação…', clearSearch: 'Limpar pesquisa',
    allGroups: 'Todos os grupos', allSubgroups: 'Todos os subgrupos', clear: 'Limpar',
    noProducts: 'Nenhum produto encontrado.', loadingCatalog: 'A carregar o catálogo…', clearFilters: 'Limpar filtros',
    language: 'Idioma', portuguese: 'Português', english: 'English', environment: 'Ambiente',
  },
  'en-GB': {
    products: 'Products', quote: 'New quote', orders: 'Orders', registrations: 'Records',
    admin: 'Admin', logout: 'Sign out', notifications: 'Notifications', noNotifications: 'No notifications.',
    mainNavigation: 'Main navigation', skipContent: 'Skip to content',
    catalogTitle: 'Product catalogue', catalogSubtitle: 'Select a product to add it to the quote',
    searchProducts: 'Search products', searchPlaceholder: 'Search by code or product name…', clearSearch: 'Clear search',
    allGroups: 'All groups', allSubgroups: 'All subgroups', clear: 'Clear',
    noProducts: 'No products found.', loadingCatalog: 'Loading catalogue…', clearFilters: 'Clear filters',
    language: 'Language', portuguese: 'Português', english: 'English', environment: 'Environment',
  },
} as const

export type MessageKey = keyof typeof messages['pt-PT']

interface LocaleValue {
  locale: AppLocale
  setLocale: (locale: AppLocale) => void
  t: (key: MessageKey) => string
}

export const LocaleContext = createContext<LocaleValue | null>(null)

export function LocaleProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const storageKey = user ? `ilya-locale:${user.id}:EU` : 'ilya-locale:EU'
  const [locale, setLocaleState] = useState<AppLocale>(() => {
    if (user?.active_market !== 'EU') return 'pt-PT'
    const stored = localStorage.getItem(storageKey)
    return stored === 'en-GB' ? 'en-GB' : 'pt-PT'
  })

  useEffect(() => {
    document.documentElement.lang = user?.active_market === 'EU' ? locale : 'pt-BR'
  }, [locale, user?.active_market])

  const value = useMemo<LocaleValue>(() => ({
    locale,
    setLocale(next) {
      if (user?.active_market !== 'EU') return
      localStorage.setItem(storageKey, next)
      setLocaleState(next)
    },
    t: (key) => messages[locale][key],
  }), [locale, storageKey, user?.active_market])

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
}
