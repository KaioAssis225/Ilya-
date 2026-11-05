import { Plus, Trash2 } from 'lucide-react'
import { useCadastroText } from '../hooks/useCadastroText'
import type { ClientContactData } from '../types'

const MAX_CONTACTS = 20

/**
 * Contatos adicionais da ficha do cliente: cada linha tem nome, telefone e
 * e-mail. O contato principal continua nos campos da própria ficha.
 */
export function ClientContactsEditor({ contacts, onChange }: {
  contacts: ClientContactData[]
  onChange: (next: ClientContactData[]) => void
}) {
  const tx = useCadastroText()

  function update(index: number, patch: Partial<ClientContactData>) {
    onChange(contacts.map((contact, i) => (i === index ? { ...contact, ...patch } : contact)))
  }

  return (
    <div className="col-span-2 flex flex-col gap-2">
      {contacts.length > 0 && (
        <span className="text-xs text-muted">{tx('Contatos adicionais')}</span>
      )}
      {contacts.map((contact, index) => (
        <div
          key={index}
          role="group"
          aria-label={tx('Contato adicional {n}', { n: index + 1 })}
          className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_1fr_auto] gap-2 items-end rounded-lg border border-line p-2"
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
