import { Check, X } from 'lucide-react'
import { PASSWORD_RULES, passwordStrength } from '../lib/passwordRules'

// Verificador de senha: mostra as regras exigidas pelo servidor e marca, letra
// a letra, quais já foram cumpridas — assim o usuário confere na hora se a
// senha escolhida vai ser aceita, em vez de descobrir só no submit.

const BAR_TONE: Record<number, string> = {
  1: 'bg-red-500',
  2: 'bg-amber-500',
  3: 'bg-olive',
  4: 'bg-olive',
}

const TEXT_TONE: Record<number, string> = {
  1: 'text-red-700',
  2: 'text-amber-700',
  3: 'text-olive',
  4: 'text-olive',
}

export default function PasswordStrength({
  password,
  confirm,
}: {
  password: string
  /** Quando informado, acrescenta a conferência "as duas senhas coincidem". */
  confirm?: string
}) {
  const strength = passwordStrength(password)

  return (
    <div className="rounded-xl border border-line bg-bg px-3.5 py-3 space-y-2.5">
      <div className="flex items-center justify-between gap-3">
        <span className="text-[11px] font-semibold text-muted uppercase tracking-wider">
          Regras da senha
        </span>
        {strength && (
          <span className={`text-[11px] font-semibold ${TEXT_TONE[strength.level]}`}>
            {strength.label}
          </span>
        )}
      </div>

      <div className="flex gap-1" aria-hidden="true">
        {[1, 2, 3, 4].map((segment) => (
          <div
            key={segment}
            className={`h-1 flex-1 rounded-full transition-colors ${
              strength && segment <= strength.level ? BAR_TONE[strength.level] : 'bg-line'
            }`}
          />
        ))}
      </div>

      <ul className="space-y-1" aria-live="polite">
        {PASSWORD_RULES.map((rule) => {
          const ok = rule.test(password)
          return (
            <li key={rule.id} className="flex items-center gap-2">
              {ok
                ? <Check className="w-3.5 h-3.5 text-olive flex-shrink-0" aria-hidden="true" />
                : <X className="w-3.5 h-3.5 text-muted-3 flex-shrink-0" aria-hidden="true" />}
              <span className={`text-xs ${ok ? 'text-olive' : 'text-muted-2'}`}>
                {rule.label}
                <span className="sr-only">{ok ? ' — cumprido' : ' — pendente'}</span>
              </span>
            </li>
          )
        })}
        {confirm !== undefined && (
          <li className="flex items-center gap-2">
            {password.length > 0 && password === confirm
              ? <Check className="w-3.5 h-3.5 text-olive flex-shrink-0" aria-hidden="true" />
              : <X className="w-3.5 h-3.5 text-muted-3 flex-shrink-0" aria-hidden="true" />}
            <span className={`text-xs ${password.length > 0 && password === confirm ? 'text-olive' : 'text-muted-2'}`}>
              As duas senhas coincidem
            </span>
          </li>
        )}
      </ul>
    </div>
  )
}
