"""Embedded font registration for deterministic vector PDF figures."""

from __future__ import annotations

from pathlib import Path

import reportlab
from reportlab import rl_config
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


PDF_FONT_REGULAR = "CAPMEVera"
PDF_FONT_BOLD = "CAPMEVera-Bold"
PDF_FONT_ITALIC = "CAPMEVera-Italic"


def register_pdf_fonts() -> None:
    """Register ReportLab's bundled Vera fonts so figures embed every font."""

    font_dir = Path(reportlab.__file__).resolve().parent / "fonts"
    fonts = {
        PDF_FONT_REGULAR: font_dir / "Vera.ttf",
        PDF_FONT_BOLD: font_dir / "VeraBd.ttf",
        PDF_FONT_ITALIC: font_dir / "VeraIt.ttf",
    }
    for name, path in fonts.items():
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(path)))
    rl_config.canvas_basefontname = PDF_FONT_REGULAR
