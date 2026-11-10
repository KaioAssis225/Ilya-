"""Galeria de fotos do produto: único ponto que muda `product_photos`.

Invariante: com fotos, exatamente uma é principal e `products.photo_path` é o
caminho dela; sem fotos, `photo_path` é NULL. Quem lê só `photo_path` (PDF,
orçamento, conjuntos, sincronização EU, backup) continua enxergando a principal.

As funções esperam o produto já carregado com `FOR UPDATE` e `photos` fresco
(ver `_photo_editable_product` no router). Elas não fazem commit nem mexem em
arquivo: quem chama grava/apaga o arquivo e faz o commit.

Janela de deploy: a API anterior só conhece `photo_path`. Se ela gravou uma foto
nova depois da migration, `_heal` promove esse caminho a principal antes de
qualquer mutação. A principal antiga fica na galeria (pode apontar para um
arquivo já apagado; é removível pelo gerenciador).
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product, ProductPhoto

MAX_PRODUCT_PHOTOS = 10


def _ordered(product: Product) -> list[ProductPhoto]:
    return sorted(product.photos, key=lambda photo: (photo.position, str(photo.id)))


def _primary(product: Product) -> ProductPhoto | None:
    return next((photo for photo in product.photos if photo.is_primary), None)


def _find(product: Product, photo_id: uuid.UUID) -> ProductPhoto:
    photo = next((item for item in product.photos if item.id == photo_id), None)
    if photo is None:
        raise HTTPException(status_code=404, detail="Foto não encontrada.")
    return photo


async def _sync(db: AsyncSession, product: Product) -> None:
    """Renumera 0..N-1, garante uma principal e espelha em `photo_path`."""
    ordered = _ordered(product)
    for index, photo in enumerate(ordered):
        if photo.position != index:
            photo.position = index
    primary = _primary(product)
    if primary is None and ordered:
        primary = ordered[0]
        primary.is_primary = True
    product.photo_path = primary.photo_path if primary else None
    await db.flush()


async def _heal(db: AsyncSession, product: Product) -> None:
    path = product.photo_path
    if not path:
        return
    primary = _primary(product)
    if primary is not None and primary.photo_path == path:
        return
    if primary is not None:
        primary.is_primary = False
        await db.flush()  # índice parcial: nunca duas principais, nem de passagem
    existing = next((photo for photo in product.photos if photo.photo_path == path), None)
    if existing is not None:
        existing.is_primary = True
    else:
        for photo in product.photos:
            photo.position += 1
        product.photos.append(ProductPhoto(photo_path=path, position=0, is_primary=True))
    await db.flush()


async def prepare(db: AsyncSession, product: Product, *, require_capacity: bool = False) -> None:
    await _heal(db, product)
    if require_capacity and len(product.photos) >= MAX_PRODUCT_PHOTOS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Limite de {MAX_PRODUCT_PHOTOS} fotos por produto.",
        )


async def add_photo(db: AsyncSession, product: Product, path: str) -> ProductPhoto:
    """Acrescenta ao fim; a primeira foto do produto vira a principal."""
    await prepare(db, product, require_capacity=True)
    photo = ProductPhoto(
        photo_path=path, position=len(product.photos), is_primary=not product.photos
    )
    product.photos.append(photo)
    await _sync(db, product)
    return photo


async def remove_photo(db: AsyncSession, product: Product, photo_id: uuid.UUID) -> str:
    """Remove a foto e devolve o caminho (o arquivo é decisão de quem chama).
    Removendo a principal, a próxima da ordem vira principal."""
    await _heal(db, product)
    photo = _find(product, photo_id)
    path, was_primary = photo.photo_path, photo.is_primary
    product.photos.remove(photo)
    await db.flush()  # a principal antiga sai antes de promover a próxima
    if was_primary and product.photos:
        _ordered(product)[0].is_primary = True
    await _sync(db, product)
    return path


async def replace_primary(db: AsyncSession, product: Product, new_path: str) -> str | None:
    """Comportamento legado do upload: a nova vira a principal, no lugar da
    antiga, que sai da galeria. Devolve o caminho antigo (ou None)."""
    await _heal(db, product)
    primary = _primary(product)
    old_path, position = None, 0
    if primary is not None:
        old_path, position = primary.photo_path, primary.position
        product.photos.remove(primary)
        await db.flush()
    product.photos.append(ProductPhoto(photo_path=new_path, position=position, is_primary=True))
    await _sync(db, product)
    return old_path


async def remove_primary(db: AsyncSession, product: Product) -> str | None:
    await _heal(db, product)
    primary = _primary(product)
    if primary is None:
        return None
    return await remove_photo(db, product, primary.id)


async def set_primary(db: AsyncSession, product: Product, photo_id: uuid.UUID) -> None:
    await _heal(db, product)
    photo = _find(product, photo_id)
    if photo.is_primary:
        return
    current = _primary(product)
    if current is not None:
        current.is_primary = False
        await db.flush()
    photo.is_primary = True
    await _sync(db, product)


async def reorder(db: AsyncSession, product: Product, photo_ids: list[uuid.UUID]) -> None:
    """Exige o conjunto exato de fotos do produto, sem repetir nem sobrar."""
    await _heal(db, product)
    current = {photo.id for photo in product.photos}
    if len(photo_ids) != len(set(photo_ids)) or set(photo_ids) != current:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A ordem deve listar exatamente as fotos do produto.",
        )
    by_id = {photo.id: photo for photo in product.photos}
    for index, photo_id in enumerate(photo_ids):
        by_id[photo_id].position = index
    await _sync(db, product)
