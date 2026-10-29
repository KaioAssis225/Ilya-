"""Porta do gerador de PDF e implementação real via Playwright/Chromium."""
import asyncio
import base64
import copy
import logging
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import settings
from app.core.uploads import (
    _local_key_from_path,
    _object_key_from_reference,
    _read_local_upload,
    _thumbnail_key_for_original,
    read_object_upload,
)


logger = logging.getLogger("ilya.pdf_renderer")
_RENDER_SEMAPHORE = asyncio.Semaphore(1)
_BUNDLE_PATH = Path(__file__).resolve().parent.parent / "pdf_bundle" / "pdf-render.js"


class PdfRenderer(Protocol):
    async def render(self, snapshot: dict) -> bytes: ...


class PdfRendererUnavailable(Exception):
    pass


class PdfRenderFailed(Exception):
    def __init__(self, code: str = "render_failed") -> None:
        super().__init__(code)
        self.code = code


class _UnavailableRenderer:
    async def render(self, snapshot: dict) -> bytes:
        raise PdfRendererUnavailable("renderer_unavailable")


@lru_cache(maxsize=1)
def _load_pdf_bundle() -> str:
    return _BUNDLE_PATH.read_text(encoding="utf-8")


async def _read_thumbnail_data_url(photo_path: str) -> str:
    object_key = _object_key_from_reference(photo_path)
    if object_key:
        thumbnail_key = _thumbnail_key_for_original(object_key)
        if not thumbnail_key:
            raise FileNotFoundError("thumbnail_key_unavailable")
        content, content_type = await read_object_upload(thumbnail_key)
    else:
        local_key = _local_key_from_path(photo_path)
        if not local_key:
            raise FileNotFoundError("local_key_unavailable")
        content, content_type = await asyncio.to_thread(_read_local_upload, local_key)
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


async def _prepare_payload(snapshot: dict) -> dict:
    payload = copy.deepcopy(snapshot)
    products = payload.get("products")
    if not isinstance(products, list):
        return payload

    missing_photos = 0
    for product in products:
        if not isinstance(product, dict):
            continue
        photo_path = product.pop("photo_path", None)
        if not photo_path:
            continue
        try:
            product["thumbnail_url"] = await _read_thumbnail_data_url(photo_path)
        except Exception:
            product["thumbnail_url"] = None
            missing_photos += 1

    if missing_photos > 0:
        logger.warning(
            "Fotos ausentes ao renderizar PDF do pedido: count=%s",
            missing_photos,
        )
    return payload


class PlaywrightPdfRenderer:
    async def render(self, snapshot: dict) -> bytes:
        if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 2:
            raise PdfRenderFailed("unsupported_snapshot")

        try:
            bundle_script = await asyncio.to_thread(_load_pdf_bundle)
        except OSError as exc:
            raise PdfRendererUnavailable("renderer_unavailable") from exc

        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise PdfRendererUnavailable("renderer_unavailable") from exc

        payload = await _prepare_payload(snapshot)

        async with _RENDER_SEMAPHORE:
            try:
                async with async_playwright() as pw:
                    try:
                        browser = await pw.chromium.launch(
                            args=[
                                "--no-sandbox",
                                "--disable-dev-shm-usage",
                                "--disable-gpu",
                            ]
                        )
                    except Exception as exc:
                        raise PdfRendererUnavailable("renderer_unavailable") from exc

                    try:
                        page = await browser.new_page()

                        async def _block_external_requests(route) -> None:
                            url = route.request.url
                            if url.startswith(("data:", "about:", "blob:")):
                                await route.continue_()
                            else:
                                await route.abort()

                        await page.route("**/*", _block_external_requests)
                        await page.set_content("<!doctype html><html><body></body></html>")
                        await page.add_script_tag(content=bundle_script)
                        base64_pdf = await asyncio.wait_for(
                            page.evaluate(
                                "s => window.ilyaRenderOrderPdf(s)", payload
                            ),
                            timeout=settings.ORDER_EMAIL_PDF_TIMEOUT_SECONDS,
                        )
                    except Exception:
                        raise PdfRenderFailed("render_failed") from None
                    finally:
                        try:
                            await browser.close()
                        except Exception:
                            pass
            except (PdfRendererUnavailable, PdfRenderFailed):
                raise
            except Exception as exc:
                raise PdfRendererUnavailable("renderer_unavailable") from exc

        if not isinstance(base64_pdf, str) or not base64_pdf:
            raise PdfRenderFailed("render_failed")
        try:
            pdf_bytes = base64.b64decode(base64_pdf, validate=True)
        except Exception:
            raise PdfRenderFailed("render_failed") from None
        if not pdf_bytes.startswith(b"%PDF"):
            raise PdfRenderFailed("render_failed")
        return pdf_bytes


def get_pdf_renderer() -> PdfRenderer:
    if settings.ORDER_EMAIL_PDF_RENDERER == "playwright":
        return PlaywrightPdfRenderer()
    return _UnavailableRenderer()
