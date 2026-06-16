"""Extraction du texte du rapport PDF, page par page, avec section d'appartenance.

Chaque page est associée à la section du sommaire (table des matières PDF) qui la
précède, afin que le RAG puisse **citer la source** (section + numéro de page) dans
ses réponses — conformément au principe de sourcing transparent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import fitz  # PyMuPDF

from chatbot import paths


@dataclass(frozen=True)
class Page:
    """Une page extraite du rapport."""

    page: int  # numéro de page 1-based (tel qu'affiché dans le PDF)
    section: str  # titre de section englobant (heuristique)
    text: str


# Sous-section pointée : "1.2", "3.1.4 Titre..." (au moins un niveau).
_SUBSECTION = re.compile(r"^\d+\.\d+(?:\.\d+){0,2}\.?\s+\S")
# Section de premier niveau : "1. DESCRIPTION..." (numéro, point, majuscule).
_TOPLEVEL = re.compile(r"^\d+\.\s+[A-ZÀ-Ÿ]")


def _heading_in(text: str) -> str | None:
    """Retourne le dernier titre de section plausible trouvé dans une page.

    Le rapport n'expose pas de signets PDF ; on détecte les en-têtes numérotés
    (``1.2.2 ...``, ``1. TITRE``) et les titres en capitales (≥4 lettres), en
    gardant le dernier de la page pour qu'il s'applique aux pages suivantes.
    """
    found: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not (6 <= len(line) <= 90):
            continue
        is_numbered = bool(_SUBSECTION.match(line) or _TOPLEVEL.match(line))
        # Titre majuscule (≥4 lettres), sans point final.
        letters = [c for c in line if c.isalpha()]
        is_upper = (
            len(letters) >= 4 and all(c.isupper() for c in letters) and line[-1] != "."
        )
        if is_numbered or is_upper:
            found = re.sub(r"\s+", " ", line)
    return found


def extract_pages(pdf_path=None, *, min_chars: int = 40) -> list[Page]:
    """Extrait les pages non vides du rapport (texte + section + n° de page)."""
    pdf_path = pdf_path or paths.REPORT_PDF
    doc = fitz.open(pdf_path)
    pages: list[Page] = []
    current = ""
    for i in range(doc.page_count):
        text = doc[i].get_text("text").strip()
        if len(text) < min_chars:
            continue  # pages de garde / images sans texte
        heading = _heading_in(text)
        section = heading or current
        if heading:
            current = heading
        pages.append(Page(page=i + 1, section=section, text=text))
    doc.close()
    return pages
