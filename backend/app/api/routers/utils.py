import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from app.core.http_client import external_http_client
from app.core.limiter import limiter

router = APIRouter(prefix="/api/v1/utils", tags=["utils"])

_VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
_PORTUGAL_POSTAL_URL = "https://api.zippopotam.us/pt/{postal_code}"


@router.get("/cep/{cep}")
@limiter.limit("60/minute")
async def lookup_cep(request: Request, response: Response, cep: str):
    """Proxy de consulta de CEP — esconde o IP do cliente final do ViaCEP."""
    clean = "".join(c for c in cep if c.isdigit())
    if len(clean) != 8:
        raise HTTPException(status_code=422, detail="CEP deve ter 8 dígitos.")
    try:
        r = await external_http_client.get(_VIACEP_URL.format(cep=clean))
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


@router.get("/postal-code/{postal_code}")
@limiter.limit("60/minute")
async def lookup_portugal_postal_code(request: Request, response: Response, postal_code: str):
    """Consulta código postal português e devolve campos compatíveis com o cadastro."""
    clean = "".join(c for c in postal_code if c.isdigit())
    if len(clean) != 7:
        raise HTTPException(status_code=422, detail="Código postal deve ter 7 dígitos.")
    formatted = f"{clean[:4]}-{clean[4:]}"
    try:
        r = await external_http_client.get(_PORTUGAL_POSTAL_URL.format(postal_code=formatted))
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Código postal não encontrado.")
        raise HTTPException(status_code=502, detail="Serviço de código postal indisponível.")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Serviço de código postal indisponível.")
    place = (data.get("places") or [{}])[0]
    return {
        "logradouro": "",
        "bairro": "",
        "localidade": place.get("place name", ""),
        "uf": "--",
        "regiao": place.get("state", ""),
    }
