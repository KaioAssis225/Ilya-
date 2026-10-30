import re
import base64
import io
import uuid

import pytest
from PIL import Image

# Ambientes sem as dependências de renderização (ex.: imagem de teste antiga) pulam o módulo.
PdfReader = pytest.importorskip("pypdf").PdfReader
pytest.importorskip("playwright")

from app.services.pdf_renderer import (
    PdfRendererUnavailable,
    PdfRenderFailed,
    PlaywrightPdfRenderer,
)


pytestmark = [pytest.mark.pdf_render, pytest.mark.asyncio]


def _make_item(
    *,
    product_code: str = "PROD-001",
    description: str = "Poltrona Ilya",
    qty: float = 1,
    unit_price: float = 1000.0,
    discount: float = 0.0,
    ipi_rate: float = 0.0,
    ipi_value: float = 0.0,
    tax_label: str = "IPI",
    currency: str = "BRL",
    largura: float = 80.0,
    profundidade: float = 85.0,
    altura: float = 75.0,
    is_circular: bool = False,
    sold_by_area: bool = False,
    area_width_m: float | None = None,
    area_depth_m: float | None = None,
    area_pieces: int = 1,
    opt_categories: dict | None = None,
    optional_choices: list | None = None,
    observacao: str | None = None,
    comment: str | None = None,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "order_id": "00000000-0000-0000-0000-000000000001",
        "product_code": product_code,
        "description": description,
        "sold_by_area": sold_by_area,
        "area_width_m": area_width_m,
        "area_depth_m": area_depth_m,
        "area_pieces": area_pieces,
        "is_circular": is_circular,
        "altura": altura,
        "largura": largura,
        "profundidade": profundidade,
        "opt_categories": opt_categories or {},
        "optional_choices": optional_choices or [],
        "qty": qty,
        "unit_price": unit_price,
        "discount": discount,
        "ipi_rate": ipi_rate,
        "ipi_value": ipi_value,
        "tax_label": tax_label,
        "currency": currency,
        "observacao": observacao,
        "comment": comment,
        "created_at": "2026-10-29T12:00:00Z",
        "updated_at": "2026-10-29T12:00:00Z",
    }


def _make_snapshot(
    *,
    market_code: str = "BR",
    currency: str = "BRL",
    locale: str = "pt-BR",
    code: str = "PED-2026-0001",
    orc_id: str = "ORC-2026-0001",
    client_name: str = "Casa Jardim Ltda",
    total_value: float = 1000.0,
    total_ipi: float = 0.0,
    total_with_ipi: float = 1000.0,
    items: list[dict] | None = None,
    products: list[dict] | None = None,
    category_labels: dict[str, str] | None = None,
) -> dict:
    order_items = items or [
        _make_item(
            currency=currency,
            tax_label="IVA" if market_code == "EU" else "IPI",
        )
    ]
    product_entries = (
        products
        if products is not None
        else [
            {
                "product_code": item["product_code"],
                "type": "Poltrona",
                "is_set": False,
                "components": [],
                "photo_path": None,
                "thumbnail_url": None,
                "photo_url": None,
            }
            for item in order_items
        ]
    )
    return {
        "schema_version": 2,
        "locale": locale,
        "order": {
            "id": "00000000-0000-0000-0000-000000000001",
            "code": code,
            "orc_id": orc_id,
            "market_code": market_code,
            "price_list_code": "lojista",
            "currency": currency,
            "locale": locale,
            "client_id": "00000000-0000-0000-0000-000000000002",
            "rep_id": "00000000-0000-0000-0000-000000000003",
            "total_value": total_value,
            "total_ipi": total_ipi,
            "total_with_ipi": total_with_ipi,
            "is_finalized": True,
            "is_cancelled": False,
            "document_version": 1,
            "supersedes_order_id": None,
            "revision_number": 1,
            "finalized_at": "2026-10-29T12:00:00Z",
            "cancelled_at": None,
            "external_code": None,
            "notes": "Entrega combinada em horário comercial.",
            "items": order_items,
            "created_at": "2026-10-29T12:00:00Z",
            "updated_at": "2026-10-29T12:00:00Z",
        },
        "client": {
            "id": "00000000-0000-0000-0000-000000000002",
            "name": client_name,
            "phone": "+55 11 99999-0000",
            "email": "cliente@example.com",
            "cpf_cnpj": "12345678000195" if market_code == "BR" else None,
            "cep": "01310-100" if market_code == "BR" else "4000-100",
            "numero": "100",
            "address": "Av. Paulista",
            "city": "São Paulo" if market_code == "BR" else "Porto",
            "state": "SP" if market_code == "BR" else "--",
            "country": "BR" if market_code == "BR" else "PT",
            "region": None if market_code == "BR" else "Porto",
            "tax_id": None if market_code == "BR" else "PT501234567",
            "market_code": market_code,
            "price_profile": "lojista",
            "max_discount": 15.0,
            "rep_id": "00000000-0000-0000-0000-000000000003",
            "created_at": "2026-10-29T12:00:00Z",
            "updated_at": "2026-10-29T12:00:00Z",
            "last_activity_at": "2026-10-29T12:00:00Z",
        },
        "representative": {
            "id": "00000000-0000-0000-0000-000000000003",
            "name": "Representante Sul",
            "phone": "+55 11 98888-0000",
            "email": "rep@example.com",
            "cpf_cnpj": None,
            "cep": "01310-200",
            "numero": "200",
            "address": "Rua Augusta",
            "city": "São Paulo",
            "state": "SP" if market_code == "BR" else "--",
            "country": "BR" if market_code == "BR" else "PT",
            "region": None,
            "tax_id": None,
            "market_code": market_code,
            "max_discount": 30.0,
            "created_at": "2026-10-29T12:00:00Z",
            "updated_at": "2026-10-29T12:00:00Z",
            "relationship_ended_at": None,
        },
        "products": product_entries,
        "category_labels": category_labels or {},
    }


def _normalize_ws(text: str) -> str:
    return " ".join(text.split())


def _count_pdf_images(reader: PdfReader) -> int:
    count = 0
    for page in reader.pages:
        resources = page.get("/Resources") or {}
        if hasattr(resources, "get_object"):
            resources = resources.get_object()
        xobjects = resources.get("/XObject") or {}
        if hasattr(xobjects, "get_object"):
            xobjects = xobjects.get_object()
        for ref in xobjects.values():
            obj = ref.get_object() if hasattr(ref, "get_object") else ref
            if isinstance(obj, dict) and obj.get("/Subtype") == "/Image":
                count += 1
    return count


async def _render(snapshot: dict) -> tuple[bytes, PdfReader, list[str], str]:
    renderer = PlaywrightPdfRenderer()
    try:
        pdf_bytes = await renderer.render(snapshot)
    except PdfRendererUnavailable as exc:
        pytest.skip(f"Playwright/Chromium indisponível neste ambiente: {exc}")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    full_text = _normalize_ws("\n".join(pages_text))
    return pdf_bytes, reader, pages_text, full_text


async def test_render_br_simple_order():
    item = _make_item(
        product_code="POL-BR-01",
        description="Poltrona Veranda",
        qty=2,
        unit_price=1250.0,
        ipi_rate=5.0,
        ipi_value=125.0,
        tax_label="IPI",
        currency="BRL",
    )
    snapshot = _make_snapshot(
        market_code="BR",
        currency="BRL",
        locale="pt-BR",
        code="PED-2026-0101",
        client_name="Casa Jardim Ltda",
        total_value=2500.0,
        total_ipi=125.0,
        total_with_ipi=2625.0,
        items=[item],
    )

    pdf_bytes, reader, _, full_text = await _render(snapshot)

    assert pdf_bytes.startswith(b"%PDF")
    assert len(reader.pages) == 1
    assert "PED-2026-0101" in full_text
    assert "Casa Jardim Ltda" in full_text
    assert "R$ 2.625,00" in full_text
    assert "IPI" in full_text
    assert "CONFIRMAÇÃO DE PEDIDO" in full_text


async def test_render_eu_pt_pt_order():
    item = _make_item(
        product_code="MES-EU-01",
        description="Mesa Douro",
        qty=1,
        unit_price=2000.0,
        ipi_rate=23.0,
        ipi_value=460.0,
        tax_label="IVA",
        currency="EUR",
    )
    snapshot = _make_snapshot(
        market_code="EU",
        currency="EUR",
        locale="pt-PT",
        code="PED-EU-0202",
        client_name="Ateliê Atlântico Lda",
        total_value=2000.0,
        total_ipi=460.0,
        total_with_ipi=2460.0,
        items=[item],
    )

    _, _, _, full_text = await _render(snapshot)

    assert "PED-EU-0202" in full_text
    assert "IVA:" in full_text
    assert "EMPRESA" in full_text
    assert "IBTW LIVING LDA" in full_text
    assert "NIF: 519635698" in full_text
    assert "4595-542 Seroa, Paços de Ferreira, Portugal" in full_text
    assert "FATURAR A" in full_text


async def test_render_eu_en_gb_order():
    item = _make_item(
        product_code="SOF-EU-02",
        description="Modular Outdoor Sofa",
        qty=1,
        unit_price=3000.0,
        ipi_rate=23.0,
        ipi_value=690.0,
        tax_label="IVA",
        currency="EUR",
    )
    snapshot = _make_snapshot(
        market_code="EU",
        currency="EUR",
        locale="en-GB",
        code="PED-EU-0303",
        client_name="Studio Thames Ltd",
        total_value=3000.0,
        total_ipi=690.0,
        total_with_ipi=3690.0,
        items=[item],
    )

    _, _, _, full_text = await _render(snapshot)

    assert "ORDER CONFIRMATION" in full_text
    assert "COMPANY" in full_text
    assert "BILL TO" in full_text
    assert "PRODUCT" in full_text
    assert "BASE PRICE" in full_text
    assert "DISCOUNT (%)" in full_text
    assert "NET UNIT PRICE" in full_text
    assert "SUBTOTAL" in full_text
    assert "Total items:" in full_text
    assert "GRAND TOTAL:" in full_text
    assert "VAT:" in full_text
    assert re.search(r"Page \d+/\d+", full_text)


async def test_render_long_order_pagination():
    items = [
        _make_item(
            product_code=f"SKU-{idx:03d}",
            description=(
                f"Item longo {idx:03d} — Poltrona de área externa com estrutura "
                "em alumínio termolacado e acabamento artesanal resistente ao tempo"
            ),
            qty=1,
            unit_price=500.0,
        )
        for idx in range(1, 61)
    ]
    snapshot = _make_snapshot(
        code="PED-LONGO-60",
        total_value=30000.0,
        total_with_ipi=30000.0,
        items=items,
    )

    _, reader, pages_text, full_text = await _render(snapshot)

    total_pages = len(reader.pages)
    assert total_pages > 1
    for idx in range(1, 61):
        assert f"SKU-{idx:03d}" in full_text
    for page_num, page_text in enumerate(pages_text, start=1):
        assert f"Página {page_num}/{total_pages}" in _normalize_ws(page_text)


async def test_render_product_images_and_missing_photo_placeholder():
    buf = io.BytesIO()
    Image.new("RGB", (48, 48), (190, 120, 50)).save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")

    items = [
        _make_item(product_code="PROD-FOTO", description="Mesa com Foto"),
        _make_item(product_code="PROD-SEMFOTO", description="Mesa sem Foto"),
    ]
    products = [
        {
            "product_code": "PROD-FOTO",
            "type": "Mesa",
            "is_set": False,
            "components": [],
            "photo_path": None,
            "thumbnail_url": data_url,
            "photo_url": None,
        },
        {
            "product_code": "PROD-SEMFOTO",
            "type": "Mesa",
            "is_set": False,
            "components": [],
            "photo_path": None,
            "thumbnail_url": None,
            "photo_url": None,
        },
    ]
    snapshot = _make_snapshot(
        market_code="BR",
        items=items,
        products=products,
        total_value=2000.0,
        total_with_ipi=2000.0,
    )

    _, reader, _, full_text = await _render(snapshot)

    assert _count_pdf_images(reader) == 1
    assert "sem foto" in full_text


async def test_render_item_discount():
    item = _make_item(
        product_code="PROD-DESC",
        description="Chaise com Desconto",
        qty=1,
        unit_price=2000.0,
        discount=15.0,
    )
    snapshot = _make_snapshot(
        market_code="BR",
        items=[item],
        total_value=1700.0,
        total_with_ipi=1700.0,
    )

    _, _, _, full_text = await _render(snapshot)

    for label in ("PREÇO-BASE", "DESCONTO (%)", "VALOR C/ DESC.", "SUBTOTAL"):
        assert label in full_text
    assert "15%" in full_text
    assert "- R$ 300,00" in full_text
    assert "R$ 2.000,00" in full_text
    assert "R$ 1.700,00" in full_text


async def test_render_area_rug_with_dimensions_and_multiple_pieces():
    item = _make_item(
        product_code="TAP-001",
        description="Tapete Kilim Sob Medida",
        sold_by_area=True,
        area_width_m=2.5,
        area_depth_m=3.0,
        area_pieces=2,
        qty=15.0,
        unit_price=400.0,
        largura=0.0,
        profundidade=0.0,
        altura=0.0,
    )
    snapshot = _make_snapshot(
        market_code="BR",
        locale="pt-BR",
        items=[item],
        total_value=6000.0,
        total_with_ipi=6000.0,
    )

    _, _, _, full_text = await _render(snapshot)

    assert "Dimensões: 2,5 × 3 m = 7,5 m² × 2 peças = 15 m²" in full_text
    assert "15 m²" in full_text
    assert "2 peças" in full_text


async def test_render_set_product_components_and_optionals_without_parent_dimensions():
    item = _make_item(
        product_code="CONJ-01",
        description="Conjunto Living Ilya",
        largura=999.0,
        profundidade=888.0,
        altura=777.0,
        qty=1,
        unit_price=8500.0,
    )
    products = [
        {
            "product_code": "CONJ-01",
            "type": "Conjunto",
            "is_set": True,
            "components": [
                {
                    "id": str(uuid.uuid4()),
                    "description": "Módulo Lateral",
                    "is_circular": False,
                    "largura": 1.2,
                    "profundidade": 0.85,
                    "altura": 0.75,
                    "qty": 2,
                    "optionals": [
                        {
                            "id": str(uuid.uuid4()),
                            "category": "corda_nautica",
                            "color_name": "Terracota",
                            "brand": "ILYA",
                            "photo_url": None,
                        }
                    ],
                }
            ],
            "photo_path": None,
            "thumbnail_url": None,
            "photo_url": None,
        }
    ]
    snapshot = _make_snapshot(
        market_code="BR",
        locale="pt-BR",
        items=[item],
        products=products,
        category_labels={"corda_nautica": "Corda Náutica"},
        total_value=8500.0,
        total_with_ipi=8500.0,
    )

    _, _, _, full_text = await _render(snapshot)

    assert "2x Módulo Lateral (L 1,20 × P 0,85 × A 0,75 m) - Corda Náutica: Terracota" in full_text
    assert "999,00" not in full_text
    assert "888,00" not in full_text
    assert "Dimensões:" not in full_text


async def test_render_is_deterministic_across_runs():
    snapshot = _make_snapshot(code="PED-DETERMINISTICO")

    _, reader1, pages1, text1 = await _render(snapshot)
    _, reader2, pages2, text2 = await _render(snapshot)

    assert len(reader1.pages) == len(reader2.pages)
    assert pages1 == pages2
    assert text1 == text2


async def test_render_rejects_snapshot_v1():
    snapshot = _make_snapshot()
    snapshot["schema_version"] = 1

    renderer = PlaywrightPdfRenderer()
    with pytest.raises(PdfRenderFailed) as caught:
        await renderer.render(snapshot)

    assert caught.value.code == "unsupported_snapshot"
