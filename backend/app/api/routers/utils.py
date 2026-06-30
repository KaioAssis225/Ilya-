import httpx
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/utils", tags=["utils"])

_VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"


@router.get("/cep/{cep}")
async def lookup_cep(cep: str):
    """Proxy de consulta de CEP — esconde o IP do cliente final do ViaCEP."""
    clean = "".join(c for c in cep if c.isdigit())
    if len(clean) != 8:
        raise HTTPException(status_code=422, detail="CEP deve ter 8 dígitos.")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(_VIACEP_URL.format(cep=clean))
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Serviço de CEP indisponível.")
    if data.get("erro"):
        raise HTTPException(status_code=404, detail="CEP não encontrado.")
    return {
        "logradouro": data.get("logradouro", ""),
        "bairro": data.get("bairro", ""),
        "localidade": data.get("localidade", ""),
        "uf": data.get("uf", ""),
    }
