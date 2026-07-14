"""Gera o PDF operacional a partir de docs/GUIA_INFRA_OPERACOES.md."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "GUIA_INFRA_OPERACOES.md"
DEFAULT_OUTPUT = Path(
    r"C:\Users\matheus.cardoso\Documents\Programador\Projeto Ilya\Alto Comando\Auditoria\guia_infra_operacoes.pdf"
)
GOLD = colors.HexColor("#8B6914")
DARK = colors.HexColor("#2C2420")
MUTED = colors.HexColor("#6B5D52")
LIGHT = colors.HexColor("#F8F6F2")


def inline_markup(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    return escaped


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "IlyaTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=23, leading=28, textColor=GOLD, spaceAfter=12,
        ),
        "subtitle": ParagraphStyle(
            "IlyaSubtitle", parent=base["Normal"], fontSize=11,
            textColor=MUTED, alignment=TA_CENTER, spaceAfter=16,
        ),
        "h2": ParagraphStyle(
            "IlyaH2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=15, leading=19, textColor=DARK, spaceBefore=15,
            spaceAfter=8, borderColor=GOLD, borderWidth=0,
        ),
        "h3": ParagraphStyle(
            "IlyaH3", parent=base["Heading3"], fontName="Helvetica-Bold",
            fontSize=11.5, leading=15, textColor=GOLD, spaceBefore=10,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "IlyaBody", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9.4, leading=13.5, textColor=DARK, spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "IlyaBullet", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9.2, leading=13, textColor=DARK, leftIndent=16,
            firstLineIndent=-8, spaceAfter=4,
        ),
        "code": ParagraphStyle(
            "IlyaCode", parent=base["Code"], fontName="Courier",
            fontSize=7.8, leading=11, textColor=DARK, backColor=LIGHT,
            borderColor=colors.HexColor("#E8E0D6"), borderWidth=0.5,
            borderPadding=7, leftIndent=4, rightIndent=4, spaceBefore=4,
            spaceAfter=9,
        ),
    }


def parse_markdown(text: str):
    style = styles()
    story = []
    lines = text.splitlines()
    index = 0
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            story.append(Paragraph(inline_markup(" ".join(paragraph)), style["body"]))
            paragraph.clear()

    while index < len(lines):
        line = lines[index].rstrip()
        if line.startswith("```"):
            flush_paragraph()
            index += 1
            code: list[str] = []
            while index < len(lines) and not lines[index].startswith("```"):
                code.append(lines[index])
                index += 1
            story.append(Preformatted("\n".join(code), style["code"] ))
        elif line.startswith("# "):
            flush_paragraph()
            story.append(Spacer(1, 2.8 * cm))
            story.append(Paragraph(inline_markup(line[2:]), style["title"]))
            story.append(Paragraph("Projeto Ilya - continuidade, backup e recuperação", style["subtitle"]))
            story.append(Spacer(1, 0.5 * cm))
        elif line.startswith("### "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[4:]), style["h3"]))
        elif line.startswith("## "):
            flush_paragraph()
            story.append(Paragraph(inline_markup(line[3:]), style["h2"]))
        elif re.match(r"^[-*] ", line):
            flush_paragraph()
            story.append(Paragraph("• " + inline_markup(line[2:]), style["bullet"]))
        elif re.match(r"^\d+\. ", line):
            flush_paragraph()
            number, content = line.split(". ", 1)
            story.append(Paragraph(f"{number}. " + inline_markup(content), style["bullet"]))
        elif not line:
            flush_paragraph()
        else:
            paragraph.append(line)
        index += 1
    flush_paragraph()
    return story


def page_decor(canvas, document) -> None:
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(0.7)
    canvas.line(1.8 * cm, height - 1.25 * cm, width - 1.8 * cm, height - 1.25 * cm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(1.8 * cm, 0.9 * cm, "Projeto Ilya - Guia de infraestrutura e operações")
    canvas.drawRightString(width - 1.8 * cm, 0.9 * cm, f"Página {document.page}")
    canvas.restoreState()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    document = SimpleDocTemplate(
        str(args.output), pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        topMargin=1.7 * cm, bottomMargin=1.5 * cm,
        title="Guia de Infraestrutura e Operações - Projeto Ilya",
        author="Codex",
    )
    document.build(parse_markdown(SOURCE.read_text(encoding="utf-8")),
                   onFirstPage=page_decor, onLaterPages=page_decor)
    print(f"PDF gerado: {args.output}")


if __name__ == "__main__":
    main()
