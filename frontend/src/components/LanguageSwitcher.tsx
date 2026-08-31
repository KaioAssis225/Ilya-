import { Languages } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { useLocale } from '../hooks/useLocale'

export function LanguageSwitcher() {
  const { user } = useAuth()
  const { locale, setLocale, t } = useLocale()
  if (user?.active_market !== 'EU') return null

  return (
    <div className="inline-flex h-9 items-center rounded-lg border border-line bg-white p-0.5" role="group" aria-label={t('language')}>
      <Languages className="mx-1.5 h-3.5 w-3.5 text-muted" aria-hidden="true" />
      {(['pt-PT', 'en-GB'] as const).map(option => (
        <button
          key={option}
          type="button"
          onClick={() => setLocale(option)}
          aria-pressed={locale === option}
          className={`min-h-8 rounded-md px-2 text-[11px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold/40 ${
            locale === option ? 'bg-gold text-white' : 'text-muted hover:bg-bg-2 hover:text-ink'
          }`}
        >
          {option === 'pt-PT' ? 'PT' : 'EN'}
        </button>
      ))}
    </div>
  )
}
