"""Chemins canoniques du projet, dérivés de l'emplacement du package.

Centralise la localisation des données brutes, du modèle Zarr généré, du rapport
PDF et de l'index vectoriel pour que tous les modules (ingestion, RAG, tools) y
réfèrent de façon cohérente.
"""

from pathlib import Path

# .../backend/src/chatbot/paths.py -> parents: [0]=chatbot [1]=src [2]=backend
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

DATA_DIR = REPO_ROOT / "data"
DOCS_DIR = REPO_ROOT / "docs"

# Modèle de données généré (Phase 1)
ZARR_PATH = DATA_DIR / "pac.zarr"

# Index vectoriel généré (Phase 2)
STORE_DIR = BACKEND_DIR / "store"
CHROMA_DIR = STORE_DIR / "chroma"

# Sources brutes
LOG_XLSX = DATA_DIR / "log_002026.xlsx"
DICTIONARY_XLSX = DATA_DIR / "PAC 2025 - Dictionnaire des données.xlsx"
METADATA_XLSX = DATA_DIR / "PAC 2025 - Métadonnées.xlsx"
DESCRIPTION_XLSX = DATA_DIR / "PAC 2025 - Description des données brutes.xlsx"

# Rapport d'audit
REPORT_PDF = DOCS_DIR / "Performance-PAC-Rapport-final.pdf"
