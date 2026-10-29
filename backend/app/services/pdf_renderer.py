"""Porta do gerador de PDF; a implementação real entra na F3."""
from typing import Protocol


class PdfRenderer(Protocol):
    async def render(self, snapshot: dict) -> bytes: ...


class PdfRendererUnavailable(Exception):
    pass


class _UnavailableRenderer:
    async def render(self, snapshot: dict) -> bytes:
        raise PdfRendererUnavailable("renderer_unavailable")


def get_pdf_renderer() -> PdfRenderer:
    return _UnavailableRenderer()
