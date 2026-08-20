import type { ClientCreate } from '../types'

// Normalização e tradução de erro compartilhadas pelos formulários de pessoa
// (cliente e representante), usados tanto na tela de Cadastro quanto no
// cadastro rápido dentro do Orçamento. Ficavam só na tela de Cadastro: o
// atalho do Orçamento mandava `email: ''` cru e a API recusava com 422,
// porque e-mail é opcional (`EmailStr | None`) e "" não é e-mail válido.

/** Campos vazios viram `null` — a API distingue "não informado" de inválido. */
export function normalizePersonPayload(form: ClientCreate): ClientCreate {
  return {
    ...form,
    name: form.name.trim(),
    phone: form.phone.trim(),
    email: form.email?.trim() || null,
    cpf_cnpj: form.cpf_cnpj?.trim() || null,
    tax_id: form.tax_id?.trim() || null,
    country: form.country?.trim().toUpperCase(),
    region: form.region?.trim() || null,
    cep: form.cep.trim(),
    numero: form.numero?.trim() || null,
    address: form.address.trim(),
    city: form.city.trim(),
    state: form.state.trim().toUpperCase(),
  }
}

// Traduz erros de validação da API (422 do FastAPI vem como array em `detail`)
// para uma mensagem única e amigável em português.
const FIELD_LABEL: Record<string, string> = {
  name: 'Nome', phone: 'Telefone', email: 'E-mail', cpf_cnpj: 'CPF/CNPJ', cep: 'CEP',
  numero: 'Número', address: 'Endereço', city: 'Cidade', state: 'Estado (UF)',
  country: 'País', region: 'Região', tax_id: 'VAT / Tax ID',
}

export function parseApiError(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    const msgs = detail.map((d: { loc?: (string | number)[]; msg?: string }) => {
      const field = d.loc?.[d.loc.length - 1]
      const label = typeof field === 'string' ? (FIELD_LABEL[field] ?? field) : ''
      if (field === 'email') return 'E-mail inválido. Informe um e-mail válido (ex: nome@dominio.com).'
      if (field === 'state') return 'Selecione o estado (UF).'
      return label ? `${label}: ${d.msg ?? 'valor inválido'}` : (d.msg ?? 'Dados inválidos.')
    })
    return Array.from(new Set(msgs)).join(' ')
  }
  return 'Não foi possível salvar. Verifique os dados e tente novamente.'
}
