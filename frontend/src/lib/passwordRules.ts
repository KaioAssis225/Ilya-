// Espelho da política do servidor (`validate_password_strength` em
// backend/app/core/security.py). O backend continua sendo a fronteira real —
// isto existe só para o usuário ver as regras e conferir, em tempo real, se a
// senha que ele está digitando passa. Se a política mudar lá, mude aqui também.

export interface PasswordRule {
  id: string
  label: string
  test: (password: string) => boolean
}

export const PASSWORD_RULES: PasswordRule[] = [
  { id: 'length', label: 'De 8 a 128 caracteres', test: (p) => p.length >= 8 && p.length <= 128 },
  { id: 'upper', label: 'Pelo menos 1 letra maiúscula (A–Z)', test: (p) => /[A-Z]/.test(p) },
  { id: 'lower', label: 'Pelo menos 1 letra minúscula (a–z)', test: (p) => /[a-z]/.test(p) },
  { id: 'digit', label: 'Pelo menos 1 número (0–9)', test: (p) => /[0-9]/.test(p) },
]

export function isPasswordValid(password: string): boolean {
  return PASSWORD_RULES.every((rule) => rule.test(password))
}

/** Primeira regra não cumprida — vira a mensagem de erro no submit. */
export function firstUnmetRule(password: string): PasswordRule | undefined {
  return PASSWORD_RULES.find((rule) => !rule.test(password))
}

export interface PasswordStrength {
  /** 1 a 4 — quantos segmentos da barra acender. */
  level: 1 | 2 | 3 | 4
  label: string
}

/** A força só sobe depois que a senha cumpre TODAS as regras obrigatórias;
 *  daí em diante o que agrega é comprimento e símbolo. */
export function passwordStrength(password: string): PasswordStrength | null {
  if (!password) return null

  const met = PASSWORD_RULES.filter((rule) => rule.test(password)).length
  if (met < PASSWORD_RULES.length) {
    return { level: 1, label: 'Não atende às regras' }
  }

  const bonus = (password.length >= 12 ? 1 : 0) + (/[^A-Za-z0-9]/.test(password) ? 1 : 0)
  if (bonus === 0) return { level: 2, label: 'Média' }
  if (bonus === 1) return { level: 3, label: 'Boa' }
  return { level: 4, label: 'Forte' }
}
