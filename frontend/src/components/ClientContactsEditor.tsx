import type { ReactNode } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { useCadastroText } from '../hooks/useCadastroText'
import type { ClientContactData } from '../types'

const MAX_CONTACTS = 20
const ROW_GRID = 'grid grid-cols-1 sm:grid-cols-[1fr_1fr_1fr_auto] gap-2 items-end'

/**
 * Seção "Contatos" da ficha do cliente. A primeira linha (`primary`) é o contato
 * principal, que continua gravado nas colunas do próprio cliente e por isso não
 * pode ser removida; as linhas seguintes são os contatos adicionais, cada uma
 * com nome, telefone e e-mail.
 */
export function ClientContactsEditor({ contacts, onChange, primary, hasPrimaryName = false }: {
  contacts: ClientContactData[]
  onChange: (next: ClientContactData[]) => void
  /** Campos do contato principal (nome no EU, telefone e e-mail). */
  primary?: ReactNode
  /** Sem nome no contato principal (Brasil), o telefone alinha com os adicionais. */
  hasPrimaryName?: boolean
}) {
  const tx = useCadastroText()

  function update(index: number, patch: Partial<ClientContactData>) {
    onChange(contacts.map((contact, i) => (i === index ? { ...contact, ...patch } : contact)))
  }

  return (
    <div className="col-span-2 flex flex-col gap-2">
      <span className="text-xs text-muted">{tx('Contatos')}</span>
      {primary && (
        <div
          role="group"
          aria-label={tx('Contato principal')}
          className={`${ROW_GRID} rounded-lg border border-line p-2`}
        >
          {!hasPrimaryName && <div className="hidden sm:block" aria-hidden="true" />}
          {primary}
          <span className="hidden sm:block w-9" aria-hidden="true" />
        </div>
      )}
      {contacts.map((contact, index) => (
        <div
          key={index}
          role="group"
          aria-label={tx('Contato adicional {n}', { n: index + 1 })}
          className={`${ROW_GRID} rounded-lg border border-line p-2`}
        >
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted">{tx('Nome do contato *')}</span>
            <input
              className="input"
              value={contact.name}
              maxLength={255}
              onChange={(e) => update(index, { name: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted">{tx('Telefone do contato')}</span>
            <input
              className="input"
              value={contact.phone ?? ''}
              maxLength={20}
              onChange={(e) => update(index, { phone: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted">{tx('E-mail do contato')}</span>
            <input
              className="input"
              type="email"
              value={contact.email ?? ''}
              onChange={(e) => update(index, { email: e.target.value })}
            />
          </label>
          <button
            type="button"
            aria-label={tx('Remover contato {n}', { n: index + 1 })}
            onClick={() => onChange(contacts.filter((_, i) => i !== index))}
            className="w-11 h-11 sm:w-9 sm:h-9 flex items-center justify-center text-muted hover:text-danger transition-colors"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      ))}
      {contacts.length < MAX_CONTACTS && (
        <button
          type="button"
          onClick={() => onChange([...contacts, { name: '', phone: '', email: '' }])}
          className="self-start inline-flex items-center gap-1 text-xs font-semibold text-gold hover:underline min-h-9"
        >
          <Plus className="w-3.5 h-3.5" /> {tx('Adicionar contato')}
        </button>
      )}
    </div>
  )
}
