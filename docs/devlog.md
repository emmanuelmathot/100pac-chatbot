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
