import httpx
from fastapi import APIRouter, HTTPException, Request, Response

from app.core.http_client import external_http_client, external_request
from app.core.observability import external_fallback, external_invalid
from app.core.limiter import limiter

router = APIRouter(prefix="/api/v1/utils", tags=["utils"])

_VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
# GeoAPI.pt (dados CTT/INE) devolve a rua ("Artéria") do código postal; o
# zippopotam só tem localidade/distrito e fica como reserva se o GeoAPI cair.
_PORTUGAL_GEOAPI_URL = "https://json.geoapi.pt/cp/{postal_code}"
_PORTUGAL_POSTAL_URL = "https://api.zippopotam.us/pt/{postal_code}"


@router.get("/cep/{cep}")
@limiter.limit("60/minute")
async def lookup_cep(request: Request, response: Response, cep: str):
    """Proxy de consulta de CEP — esconde o IP do cliente final do ViaCEP."""
    clean = "".join(c for c in cep if c.isdigit())
    if len(clean) != 8:
        raise HTTPException(status_code=422, detail="CEP deve ter 8 dígitos.")
    try:
        r = await external_request("GET", _VIACEP_URL.format(cep=clean), dependency="viacep", client=external_http_client)
        r.raise_for_status()
        data = r.json()
    except ValueError:
        external_invalid("viacep")
        raise HTTPException(status_code=502, detail="Serviço de CEP indisponível.")
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
    return await lookup_portugal_address(f"{clean[:4]}-{clean[4:]}")


def portugal_address_from_geoapi(data: dict) -> dict:
    """Converte a resposta do GeoAPI.pt para os campos do cadastro."""
    partes = data.get("partes") or []
    street = next((p.get("Artéria", "").strip() for p in partes if p.get("Artéria")), "")
    if not street:
        street = next(iter(data.get("ruas") or []), "")
    return {
        "logradouro": street,
        "bairro": "",
        "localidade": data.get("Localidade") or data.get("Concelho") or "",
        "uf": "--",
        "regiao": data.get("Distrito", ""),
    }


async def lookup_portugal_address(formatted: str) -> dict:
    """GeoAPI.pt primeiro (traz a rua); zippopotam como reserva (só localidade)."""
    not_found = False
    try:
        r = await external_request("GET", _PORTUGAL_GEOAPI_URL.format(postal_code=formatted), dependency="geoapi", client=external_http_client)
        if r.status_code == 404:
            not_found = True
        else:
            r.raise_for_status()
            address = portugal_address_from_geoapi(r.json())
            if address["localidade"]:
                return address
    except ValueError:
        external_invalid("geoapi")
    except httpx.HTTPError:
        pass
    external_fallback("geoapi")

    try:
        r = await external_request("GET", _PORTUGAL_POSTAL_URL.format(postal_code=formatted), dependency="zippopotam", client=external_http_client)
        r.raise_for_status()
        data = r.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404 or not_found:
            raise HTTPException(status_code=404, detail="Código postal não encontrado.")
        raise HTTPException(status_code=502, detail="Serviço de código postal indisponível.")
    except ValueError:
        external_invalid("zippopotam")
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
