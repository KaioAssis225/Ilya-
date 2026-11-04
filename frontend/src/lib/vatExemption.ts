/** Motivos de isenção de IVA do orçamento EU (códigos AT/Moloni).
 *  Espelha `backend/app/core/vat_exemption.py`; o servidor valida o código e
 *  devolve o texto do documento em `vat_exemption_label`. */
export interface VatExemptionReason {
  code: string
  pt: string
  en: string
}

export const VAT_EXEMPTION_REASONS: readonly VatExemptionReason[] = [
  { code: 'M16', pt: 'Isento nos termos do artigo 14.º do RITI (transmissão intracomunitária)', en: 'Exempt under Article 14 of the RITI (intra-Community supply)' },
  { code: 'M05', pt: 'Isento nos termos do artigo 14.º do CIVA (exportação)', en: 'Exempt under Article 14 of the CIVA (export)' },
  { code: 'M07', pt: 'Isento nos termos do artigo 9.º do CIVA', en: 'Exempt under Article 9 of the CIVA' },
  { code: 'M99', pt: 'Não sujeito; não tributado', en: 'Not subject to VAT; not taxed' },
]

export function vatExemptionText(code: string | null | undefined, english: boolean): string | null {
  const reason = VAT_EXEMPTION_REASONS.find(candidate => candidate.code === code)
  return reason ? (english ? reason.en : reason.pt) : null
}

/** Quem pode marcar "Sem IVA" (o servidor confere de novo): admin, operador
 *  interno e representante; conta de cliente nunca. */
export function canSetVatExemption(role: string | undefined): boolean {
  return role === 'admin' || role === 'representante' || role === 'vendedor'
}
