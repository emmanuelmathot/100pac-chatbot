"""Tests d'extraction et de rendu des figures du rapport (PDF committé)."""

import base64

from chatbot.rag import figures


def test_extract_figures_finds_numbered_captions():
    figs = figures.extract_figures()
    assert len(figs) > 100  # le rapport contient des centaines de figures/tableaux
    # Numéros uniques par type, pages valides, légendes non vides.
    assert all(f.page >= 1 and f.number >= 1 and f.caption for f in figs)
    assert {f.kind for f in figs} <= {
        "Figure",
        "Tableau",
        "Graphique",
        "Illustration",
        "Carte",
    }
    keys = [(f.kind, f.number) for f in figs]
    assert len(keys) == len(set(keys))  # dédupliqué


def test_render_page_returns_png():
    data = figures.render_page_png(13)  # page contenant des figures
    raw = base64.b64decode(data)
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"  # signature PNG
