"""Motivos de isenção de IVA do orçamento EU (códigos AT/Moloni).

Fatura em Portugal sem IVA exige o código do motivo (`exemption_reason` no
Moloni). A lista é fixa: o orçamento só aceita um destes códigos e o texto sai
no PDF e no histórico. Para liberar outro motivo, acrescente-o aqui e em
`frontend/src/lib/vatExemption.ts`.
"""
from typing import Literal, Optional

VatExemptionCode = Literal["M16", "M05", "M07", "M99"]

# código -> (pt-PT, en-GB)
VAT_EXEMPTION_REASONS: dict[str, tuple[str, str]] = {
    "M16": (
        "Isento nos termos do artigo 14.º do RITI (transmissão intracomunitária)",
        "Exempt under Article 14 of the RITI (intra-Community supply)",
    ),
    "M05": (
        "Isento nos termos do artigo 14.º do CIVA (exportação)",
        "Exempt under Article 14 of the CIVA (export)",
    ),
    "M07": (
        "Isento nos termos do artigo 9.º do CIVA",
        "Exempt under Article 9 of the CIVA",
    ),
    "M99": (
        "Não sujeito; não tributado",
        "Not subject to VAT; not taxed",
    ),
}


def vat_exemption_label(code: Optional[str], locale: Optional[str]) -> Optional[str]:
    """Texto do motivo no idioma do documento (en-GB em inglês, resto em pt-PT)."""
    reason = VAT_EXEMPTION_REASONS.get(code or "")
    if reason is None:
        return None
    return reason[1] if locale == "en-GB" else reason[0]
