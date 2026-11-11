"""Login único com o Estoque Brasil: emissor da autorização (handoff).

`POST /api/v1/stock/handoff` devolve um JWT ES256 de 60 s que o Estoque troca
pela própria sessão. O Ilya só decide se a pessoa *pode* entrar; o papel dentro
do Estoque é decidido lá.

Ordem das checagens (todas no servidor):
  401 sem sessão válida / `auth_version` divergente / conta inativa
  403 (genérico) sem `has_stock_access`, sem vínculo BR ativo, papel
      `cliente`/`benchmark_readonly`, ou troca de senha pendente
  503 chave de assinatura não configurada (o link "Estoque" some)
  429 limite por usuário
A negativa é auditada com o motivo interno; o corpo da resposta nunca o revela.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_authenticated_user, get_db_session
from app.core.config import settings
from app.core.limiter import limiter
from app.core.privacy_audit import record_privacy_event
from app.core.stock_access import stock_access_denial
from app.core.stock_handoff import (
    LIFETIME_SECONDS,
    HandoffSigner,
    get_signer,
    issue_assertion,
)
from app.models.user import User

logger = logging.getLogger("ilya.stock_handoff")
router = APIRouter(prefix="/api/v1/stock", tags=["stock"])

_GENERIC_FORBIDDEN = "Acesso ao Estoque não autorizado."


class HandoffResponse(BaseModel):
    assertion: str
    expires_in: int = LIFETIME_SECONDS


class StockLinkResponse(BaseModel):
    origin: str


def _denial_reason(user: User) -> str | None:
    if user.must_change_password:
        return "must_change_password"
    if not user.has_stock_access:
        return "no_stock_access"
    return stock_access_denial(user)


async def _authorize(
    db: AsyncSession,
    request: Request,
    user: User,
    *,
    audit_denial: bool,
) -> HandoffSigner:
    reason = _denial_reason(user)
    if reason is not None:
        if audit_denial:
            record_privacy_event(
                db,
                actor_user_id=user.id,
                subject_type="user",
                subject_id=user.id,
                action="stock_handoff_denied",
                request=request,
                context={"reason": reason},
            )
            await db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, _GENERIC_FORBIDDEN)
    signer = get_signer()
    if signer is None:
        # Sem detalhe: nem a chave nem a origem aparecem em log ou resposta.
        logger.warning("Handoff do Estoque solicitado, mas o emissor não está configurado.")
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Integração com o Estoque indisponível."
        )
    return signer


@router.post("/handoff", response_model=HandoffResponse)
@limiter.limit(settings.RATE_LIMIT_STOCK_HANDOFF)
async def issue_handoff(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_authenticated_user),
) -> HandoffResponse:
    signer = await _authorize(db, request, user, audit_denial=True)
    assertion, jti = issue_assertion(user, signer)
    # Auditoria: quem pediu, quando, resultado. O token NUNCA é gravado; o jti
    # (identificador aleatório de uso único) permite correlacionar com o Estoque.
    record_privacy_event(
        db,
        actor_user_id=user.id,
        subject_type="user",
        subject_id=user.id,
        action="stock_handoff_issued",
        request=request,
        context={"kid": signer.kid, "jti": jti},
    )
    await db.commit()
    response.headers["Cache-Control"] = "no-store"
    return HandoffResponse(assertion=assertion)


@router.get("/link", response_model=StockLinkResponse)
async def stock_link(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_authenticated_user),
) -> StockLinkResponse:
    """Origem do frontend do Estoque, para o `window.open` e o `postMessage`.

    Vem do servidor (`STOCK_APP_ORIGIN`) para haver uma única fonte; só quem
    passa nas mesmas regras do handoff a recebe.
    """
    signer = await _authorize(db, request, user, audit_denial=False)
    response.headers["Cache-Control"] = "no-store"
    return StockLinkResponse(origin=signer.origin)
