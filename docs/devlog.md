# Devlog — Chatbot agentic 100PAC

Journal de bord du projet. Voir le plan d'ensemble dans
[../bootstrap.md](../bootstrap.md) et le modèle de données dans [data-model.md](data-model.md).

## Principes directeurs

Système agentic « production grade » (cf. Development Seed, EGU26-19885) :

1. Le LLM **orchestre** des tools déterministes, il ne calcule pas.
2. Les **données ne transitent pas** par le contexte du modèle (tools → résultats compacts).
3. **Analyse par code** reproductible et tracée (provenance).
4. **Sourcing transparent** (citations rapport / requêtes data).
5. Pas d'hallucination : dire quand l'info est absente.

---

## 2026-06-16 — Phase 0 : restructuration & dépôt

- Création du dépôt git dédié `100pac-chatbot` (remote `github.com/emmanuelmathot/100pac-chatbot`).
- Remontée du contenu de `chatbot skeleton/` à la racine (suppression de l'espace dans le chemin qui cassait
  scripts/Docker) : `backend/`, `helm/`, `.github/`, `.vscode/`, `README.md`, `.gitignore`.
- `.gitignore` étendu : `data/*.xlsx`, `data/pac.zarr/`, `backend/store/` (données lourdes / artefacts régénérables).
- Sources de données identifiées et comprises (4 fichiers) :
  - `log_002026.xlsx` — séries 1 min, ~527k lignes, logement `002026`.
  - `Métadonnées.xlsx` — 22 attributs × 100 logements (dont `type_source_froide` air/eau vs géothermie, SCOP déclaré).
  - `Description des données brutes.xlsx` — config installation par logement (appoint joule inclus, ballons, circuits…).
  - `Dictionnaire des données.xlsx` — canaux → grandeur/unité (`pac`=W élec, `cc_*`=Wh thermique).

## 2026-06-16 — Phase 1 : modèle de données Zarr

- Modules `chatbot.data.{metadata,ingest,access}` + `chatbot.paths` + script `scripts/ingest-data`.
- Sources comprises et vérifiées empiriquement :
  - Dictionnaire : `pac`/`resistance_*` = **puissance (W)** ; `cc_*` = **énergie/minute (Wh)**.
  - Compteurs `cc_*` **non cumulatifs** (74 124 décroissances sur l'année) → agrégation par **somme**.
  - Parc : **90 air/eau + 10 eau/eau (géothermie)**, conforme au descriptif.
- `data/pac.zarr` (Zarr v3) généré : groupe `fleet` (100 logements × 47 attributs statiques) + groupes
  `raw`/`hourly`/`daily`/`monthly` (logement × time), peuplés pour `002026` (527 040 pas de 1 min).
- **Sharding** : chunks `(1 logement, 1 jour)`, shards `(tous logements, 1 jour)` → 1 fichier/jour/variable
  (~367), store 32 Mo.
- Dérivés : `elec_power_w`, `elec_energy_wh`, `thermal_{calo,frig,net}_wh`, `cop` de période.
- Sanity check `002026` : COP saison de chauffe (oct→avr) ≈ **2.26** vs SCOP déclaré 4.43 (écart réel typique).
  Voir [data-model.md](data-model.md) pour les conventions énergétiques et le caveat COP/SCOP estival.
- lint (ruff) + mypy verts.

## 2026-06-16 — Phase 2 : RAG du rapport

- Modules `chatbot.rag.{extract,index}` + script `scripts/build-index`.
- `extract` : PyMuPDF, 234 pages non vides extraites. Le PDF n'a pas de signets ;
  détection heuristique des en-têtes (sous-sections `1.2.2`, titres `N. TITRE`, capitales)
  reportée de page en page → **citations section + page** (92 sections distinctes).
- `index` : découpage `RecursiveCharacterTextSplitter` (1200/200) → **564 fragments**,
  embeddings `mistral-embed`, persistance Chroma dans `backend/store/` (gitignoré, régénérable).
- Recherche sémantique testée : passages pertinents renvoyés avec leur source.
- Clé Mistral fournie par l'utilisateur → `backend/.env` (gitignoré, jamais committé).
- lint + mypy verts.

## 2026-06-16 — Phase 3 : agent, tools, state

- `chatbot.data.analytics` : logique métier pure (fleet_summary, performance COP/SCOP,
  aggregate, timeseries_png) — testable hors LangChain.
- Tools (pattern `@tool` + `Command`) :
  - `search_report` (RAG, citations section/page → state `citations`).
  - `describe_fleet`, `compute_performance`, `query_measurement` (résultats JSON compacts).
  - `plot_measurement` (PNG base64 → state `plot`, rendu image dans l'UI).
  - `run_data_analysis` : **analyse par code** en environnement restreint (datasets read-only,
    builtins limités, pas d'import/IO), code persisté en `provenance`.
- `AgentState` étendu : `plot`, `citations`, `provenance`. Tool d'exemple `cat.py` supprimé.
- `SYSTEM_PROMPT` : rôle analyste PAC, orchestration only, citations obligatoires, COP de saison.
- **Test E2E (Mistral)** : « combien de géothermiques ? » → describe_fleet → 10 ;
  « COP réel saison 002026 vs déclaré ? » → compute_performance → 2.26 vs 4.43. ✓
- lint + mypy verts.

## 2026-06-16 — Phase 4 : API & UI

- L'UI Streamlit rend déjà génériquement les `state_change` ; libellés localisés FR
  (Graphe / Citations du rapport / Traçabilité), titres mis à jour (API + UI).
- **Test API NDJSON** (uvicorn) bout en bout :
  - `/health` OK.
  - Question graphe → `plot_measurement` → `state_change.plot` (image/png 90k) + `provenance` → réponse.
  - Question rapport → `search_report` → `state_change.citations` (page+section) → réponse synthétique.
- lint complet (ruff check + format) + mypy (24 fichiers) verts.

## 2026-06-16 — Phase 5 : tests & validation

- Tests unitaires déterministes (store Zarr synthétique en fixture, sans LLM) :
  ingestion (énergies), analytics (COP, filtre saison, filtrage parc), métadonnées,
  bac à sable du tool d'analyse (import/open bloqués). **17 tests verts.**
- Harnais `scripts/validate` (LLM live) sur 5 questions de référence : **5/5** déclenchent
  l'outil attendu, réponses cohérentes (10 géothermiques, COP 2.26 vs 4.43, 5530 kWh/an...).
- Affinages issus de la validation :
  - prompt : `heating_season_only` réservé au COP ; énergie totale sur période complète.
  - `compute_performance` renvoie `period_effective` (vraies bornes) → plus de dates inventées.
- [validation.md](validation.md) documente le dispositif et la conformité aux principes.
- Bruit des warnings Zarr v3 filtré dans la config pytest.

## 2026-06-16 — Phase 6 : préparation déploiement (sans déployer)

- Constat : le chart Helm n'avait **aucun Deployment** (gap Task 1) → ajout de
  `templates/deployment.yaml` (api FastAPI + chat Streamlit) et `templates/pvc.yaml`.
- `chatbot.paths` : chemins surchargeables par env (`PAC_ZARR_PATH`, `PAC_CHROMA_DIR`,
  `PAC_REPORT_PDF`) pour montage PVC en conteneur.
- `example.values.yaml` : hôtes 100pac, image chat, bloc `data`/`persistence` (PVC).
- Dockerfile : `CMD` corrigé sur `chatbot.api.app:app` (package installé).
- CI (`.github/workflows/ci.yml`) : ruff + mypy + pytest (clé factice). CD
  (`cd.yml`, workflow_dispatch) : build/push image + `helm upgrade` optionnel.
- `helm/README.md` : procédure de déploiement + provisionnement des artefacts sur le PVC.
- README racine réécrit (projet 100PAC). `helm lint` + `helm template` OK (PVC et emptyDir).
- **Aucun déploiement effectif** (conforme à la portée retenue).

## 2026-06-16 — Jeu complet des 100 logements

- Réception des **100 journaux** `log_<id>.csv` (4,4 Go). Ingestion réécrite en
  **streaming** (dask init lazy + region writes par logement) → mémoire bornée.
  - Schémas **hétérogènes** gérés (union de 48 canaux, sous-circuits, ECS, géothermie) ;
    grille temporelle globale 2023-09 → 2025-02 (~733 020 pas) ; hors couverture → NaN.
  - Sharding **par logement** (1 fichier/logement/variable) pour des écritures indépendantes.
  - Bascule CSV-only (suppression de l'ingestion xlsx du seul `002026`).
- Correctif : `089034` (zéro de tête mangé par Excel dans les métadonnées) → `_logement_id`
  zéro-pad à 6 + patch de la coord `fleet`. Jointure parc/mesures complète (100/100).
- Nouvel outil **`compare_fleet_performance`** (+ `analytics.fleet_performance`) : COP réel
  moyen par `type_source_froide`. Prompt agent mis à jour (100 logements instrumentés).
- **Résultats parc** (saison de chauffe) : air/eau **COP 3,56** (déclaré 4,39),
  géothermie **COP 4,03** (déclaré 5,02). Validé E2E via l'agent.
- Store ≈ 650 Mo. Tests (18) + lint + mypy verts.

## 2026-06-16 — Extraction des figures du rapport

- `chatbot.rag.figures` : repérage des légendes numérotées (« Figure N : … »,
  « Tableau N : … ») → 235 figures/tableaux uniques (page + légende) ; rendu de page
  en PNG (PyMuPDF), adapté aux **graphiques vectoriels** (vs extraction d'image intégrée).
- Index dédié des légendes (collection Chroma `rapport_figures`) construit par
  `build-index` ; `search_figures(query)` pour la recherche sémantique.
- Outil **`show_report_figure(query)`** : retrouve la figure, rend sa page, l'affiche
  (state `plot`) avec citation « Figure N (p. X) ». Branché à l'agent + prompt.
- Validé E2E : « montre la figure du COP saisonnier de chauffage » → Figure 73 p.93.
- Tests `test_figures` (PDF committé, sans clé). 20 tests + lint + mypy verts.

## 2026-06-16 — Graphes agrégés sur le parc

- Constat (retour utilisateur) : `run_data_analysis` ne sait pas tracer (renvoie du texte)
  et son bac à sable bloque les `import` (`ImportError: __import__ not found`) ; aucun outil
  ne traçait une **série agrégée sur tout le parc** (ex. COP moyen journalier de l'ensemble).
- `analytics.fleet_metric_series` / `fleet_metric_png` : série temporelle agrégée sur le parc.
  `metric="cop"` = Σ thermique net / Σ élec (ratio des sommes) ; autre métrique agrégée
  (somme énergies, moyenne sinon). `group_by` **libre** (tout attribut du parc) → une courbe
  par groupe (air/eau vs géothermie...).
- Outil **`plot_fleet_metric`** (paramètres : metric, resolution, group_by, heating_season_only,
  période) branché à l'agent. Validé E2E : « COP moyen du parc par mois, air/eau vs géothermie ».
- `group_by` rendu explicitement paramétrable aussi dans `compare_fleet_performance` (docstrings).
- Message d'erreur du bac à sable amélioré (imports interdits → orienter vers les tools de tracé).
- 22 tests + lint + mypy verts.
