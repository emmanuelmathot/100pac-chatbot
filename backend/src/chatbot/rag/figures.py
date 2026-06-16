"""Extraction et rendu des figures/tableaux du rapport.

Le rapport contient ~480 figures et tableaux numérotés (« Figure 12 : ... »). La
plupart sont des graphiques **vectoriels** : plutôt que d'extraire une image
intégrée (souvent absente), on **rend la page** qui porte la figure, retrouvée par
recherche sémantique sur sa légende. Chaque réponse cite « Figure N (p. X) ».
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass

import fitz  # PyMuPDF

from chatbot import paths

# Légende numérotée en début de ligne : « Figure 12 : ... », « Tableau 3 : ... ».
_CAPTION = re.compile(
    r"^(Figure|Tableau|Graphique|Illustration|Carte)\s+(\d+)\s*[:\.]", re.I
)


@dataclass(frozen=True)
class Figure:
    """Une figure/tableau du rapport, repéré par sa légende."""

    kind: str  # "Figure" | "Tableau" | ...
    number: int
    caption: str  # légende complète (ligne)
    page: int  # page 1-based


def extract_figures(pdf_path=None) -> list[Figure]:
    """Repère toutes les figures/tableaux via leurs légendes (numéro + page)."""
    pdf_path = pdf_path or paths.REPORT_PDF
    doc = fitz.open(pdf_path)
    figures: list[Figure] = []
    seen: set[tuple[str, int]] = set()
    for i in range(doc.page_count):
        for line in doc[i].get_text("text").splitlines():
            s = line.strip()
            m = _CAPTION.match(s)
            if not m:
                continue
            kind, number = m.group(1).title(), int(m.group(2))
            key = (kind, number)
            if (
                key in seen
            ):  # garde la première occurrence (sommaire des illustrations exclu)
                continue
            seen.add(key)
            figures.append(Figure(kind=kind, number=number, caption=s, page=i + 1))
    doc.close()
    return figures


def render_page_png(page_no: int, *, dpi: int = 130, pdf_path=None) -> str:
    """Rend une page (1-based) du rapport en PNG encodé base64."""
    pdf_path = pdf_path or paths.REPORT_PDF
    doc = fitz.open(pdf_path)
    page = doc[page_no - 1]
    pix = page.get_pixmap(dpi=dpi)
    data = pix.tobytes("png")
    doc.close()
    return base64.b64encode(data).decode("utf-8")
