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

## Sources de données (ADEME, ouvertes)

Le projet s'appuie sur des données publiques de la campagne ADEME/Enertech :

- **Jeu de mesures** (100 journaux `log_<id>.csv` au pas 1 min + fichiers de référence
  métadonnées/dictionnaire) :
  <https://data.ademe.fr/datasets/pac-campagne-de-mesure-100-pacs>
- **Rapport d'audit** (PDF, 245 p.) :
  <https://librairie.ademe.fr/batiment/8617-mesure-des-performances-de-100-pac-air-eau-et-eau-eau-installees-en-maisons-individuelles.html>

### Reproduire

1. Télécharger le rapport → `docs/Performance-PAC-Rapport-final.pdf`.
2. Télécharger le jeu de mesures ; placer les `PAC 2025 - *.xlsx` (métadonnées,
   dictionnaire, description) dans `data/` et les journaux `log_*.csv` dans un dossier
   (ex. `data/` ou un répertoire dédié).
3. Lancer l'ingestion (cf. ci-dessous) en pointant sur le dossier des journaux.

Ces fichiers sont volumineux et **non versionnés** (cf. `.gitignore`).

## Démarrage rapide

```bash
cd backend
cp .env.example .env          # renseigner MISTRAL_API_KEY
scripts/install               # uv sync + install editable

# Ingestion des journaux 1 min -> data/pac.zarr (CSV par logement).
# Par défaut lit data/ ; sinon préciser le dossier ou PAC_LOGS_DIR.
scripts/ingest-data /chemin/vers/les/log_csv
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

- **Docker Compose / NAS** (le plus simple) : [`docker-compose.yml`](docker-compose.yml)
  lance l'API + l'UI depuis la même image, artefacts montés en volumes. Guide :
  [docs/deploy-nas.md](docs/deploy-nas.md). Image publiée sur GHCR par le workflow
  [docker-publish.yml](.github/workflows/docker-publish.yml). Exposition HTTPS via
  Traefik (provider fichier) : [deploy/traefik/](deploy/traefik/).
- **Kubernetes / Helm** : chart dans [helm/](helm/) (Deployments api+chat, services,
  ingress TLS, secret, PVC) — voir [helm/README.md](helm/README.md).
- **CI** : ruff + mypy + pytest ([ci.yml](.github/workflows/ci.yml)).

## Documentation

- [docs/rag-explained.md](docs/rag-explained.md) — **le RAG expliqué simplement**
  (tokenisation, embeddings, Chroma, inférence) pour novices.
- [docs/data-model.md](docs/data-model.md) — modèle de données Zarr.
- [docs/validation.md](docs/validation.md) — tests & validation métier.
- [docs/deploy-nas.md](docs/deploy-nas.md) — déploiement Docker/NAS.

## Journal

Avancement détaillé : [docs/devlog.md](docs/devlog.md).
