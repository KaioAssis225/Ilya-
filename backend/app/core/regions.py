"""Mapeamento UF -> região do IBGE. O cliente só cadastra o estado (`state`);
a região do dashboard é sempre derivada dele, não é um campo próprio."""

STATE_TO_REGION: dict[str, str] = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte", "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste", "PB": "Nordeste",
    "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste", "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste", "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "RS": "Sul", "SC": "Sul",
}

REGIONS: list[str] = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"]


def region_for_state(uf: str | None) -> str | None:
    if not uf:
        return None
    return STATE_TO_REGION.get(uf.strip().upper())
