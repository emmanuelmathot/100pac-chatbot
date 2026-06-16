# 🔥 Chatbot 100PAC

Chatbot **agentic** répondant à des questions sur l'audit énergétique ADEME/Enertech
de **100 pompes à chaleur** (90 air/eau + 10 géothermiques) en résidentiel individuel —
à partir du **rapport** d'audit et des **mesures** terrain.

Le LLM (Mistral, via LangGraph) **orchestre** des outils déterministes ; il ne calcule
ni n'invente jamais de chiffres. Voir les [principes directeurs](docs/devlog.md) (d'après
Development Seed, [EGU26-19885](https://meetingorganizer.copernicus.org/EGU26/EGU26-19885.html)).

## Architecture

- **Données → Zarr** ([docs/data-model.md](docs/data-model.md)) : modèle xarray
  `logement × time` (100 logements, séries 1 min), agrégats horaires/journaliers/mensuels,
  COP/SCOP. Sharding Zarr v3 (1 fichier/jour).
- **Rapport → RAG** : extraction PyMuPDF + index vectoriel Chroma (`mistral-embed`),
  citations section/page.
- **Agent** : outils `search_report`, `describe_fleet`, `compute_performance`,
  `query_measurement`, `plot_measurement`, `run_data_analysis` (analyse par code en bac
  à sable). API FastAPI (stream NDJSON) + UI Streamlit.

## Démarrage rapide

```bash
cd backend
cp .env.example .env          # renseigner MISTRAL_API_KEY
scripts/install               # uv sync + install editable
scripts/ingest-data           # construit data/pac.zarr (lit les xlsx)
scripts/build-index           # construit l'index vectoriel du rapport

scripts/api                   # terminal 1 — API   http://localhost:8000
scripts/chat                  # terminal 2 — UI    http://localhost:8501
```

## Qualité

```bash
scripts/test      # tests unitaires (pytest)
scripts/lint      # ruff + mypy
scripts/validate  # questions de référence (LLM live) — voir docs/validation.md
```

## Déploiement

Chart Helm dans [helm/](helm/) (Deployments api+chat, services, ingress TLS, secret, PVC).
CI/CD GitHub Actions dans [.github/workflows/](.github/workflows/). Voir
[helm/README.md](helm/README.md) pour le provisionnement des artefacts et le déploiement.

## Journal

Avancement détaillé : [docs/devlog.md](docs/devlog.md).
