# Plan — Chatbot agentic 100PAC

## Context

Le projet (décrit dans [bootstrap.md](bootstrap.md)) consiste à construire un **chatbot agentic** qui répond à des
questions sur l'audit énergétique ADEME/Enertech de 100 pompes à chaleur (90 air/eau + 10 géothermiques) en résidentiel
individuel. Trois sources :

- **Le rapport** [docs/Performance-PAC-Rapport-final.pdf](docs/Performance-PAC-Rapport-final.pdf) — 245 pages,
  ADEME/Enertech, Sept. 2025 (texte, tableaux, graphiques).
- **Les métadonnées** [data/PAC 2025 - Métadonnées.xlsx](data/PAC%202025%20-%20M%C3%A9tadonn%C3%A9es.xlsx) — matrice
  **22 attributs × 100 logements** (colonnes `Log. 001026 … Log. 100016`). Attributs statiques par logement : `Département`,
  `Altitude`, `Type d'habitation`, `Surface SHAB`, `Tbase`, `Déperditions`, `Type PAC`, **`Type source froide`
  (air/eau vs géothermique — la classification clé)**, `Configuration frigorifique`, `Fluide frigorigène`, résistances,
  `Émetteurs`, `Puissance thermique à Tbase`, **`SCOP déclaré` (basse/moyenne/haute T°)**, etc. → fournit la dimension
  `logement` et ses caractéristiques.
- **La description des données brutes**
  [data/PAC 2025 - Description des données brutes.xlsx](data/PAC%202025%20-%20Description%20des%20donn%C3%A9es%20brutes.xlsx)
  — matrice **catégories × 100 logements** (`Installation`, `Suivi thermique`, `Suivi température`…) : pour chaque
  logement, présence/configuration de chaque canal (bouteille de découplage, ballon tampon, position ballon ECS, nb
  circuits radiateurs/planchers, V3V, **appoint joule inclus ou non dans la mesure thermique**…). Documente le **sens et
  les unités des canaux bruts** et la disponibilité capteur par logement — indispensable pour interpréter correctement
  les séries et calculer les COP.
- **Le dictionnaire des données**
  [data/PAC 2025 - Dictionnaire des données.xlsx](data/PAC%202025%20-%20Dictionnaire%20des%20donn%C3%A9es.xlsx) —
  table de référence canonique des ~50 canaux : `libellé → Nom, Grandeur physique, Unité`. Confirme la sémantique :
  `pac` = *Ensemble PAC, **puissance électrique (W)*** ; `resistance_*` = appoints électriques (W) ; `cc_*_calo` /
  `cc_*_frig` = compteurs de chaleur **calories/frigories, énergie thermique (Wh)** ; températures °C, humidité %HR.
  → source des `attrs` (unité, grandeur) de chaque variable du Zarr.
- **Les mesures** [data/log_002026.xlsx](data/log_002026.xlsx) — série temporelle **1 min sur ~1 an** (527 040 lignes,
  pour le logement `002026`), 15 colonnes : `time, t_amb_sejour, h_amb_sejour, t_chauffage_depart, t_chauffage_retour,
  t_ecs_depart, t_ecs_retour, resistance_chauffage, resistance_ecs, cc_chauffage_frig, cc_chauffage_calo, cc_ecs_frig,
  cc_ecs_calo, pac, t_meteo`. Ces canaux permettent de calculer COP/SCOP réels (énergie calorifique livrée `cc_*_calo` /
  énergie électrique `pac` + `resistance_*`). Le fichier ne contient le détail temporel que pour 1 logement ; le modèle
  reste dimensionné pour les 100.

Un squelette est fourni dans [chatbot skeleton/](chatbot%20skeleton/) : **LangGraph** (`create_react_agent`) +
**Mistral** (`mistral-small-latest`) + **FastAPI** (stream NDJSON `/chat`) + **Streamlit** + **Helm/K8s**. Il contient un
tool d'exemple (`get_a_picture_of_a_cool_cat`) qui montre le pattern à suivre.

**Objectif de cette itération** : data → Zarr, extraction rapport → RAG vectoriel local, agent + tools, API + UI,
tests/validation, **le tout fonctionnel en local**. Helm/CD préparés mais déploiement K8s effectif reporté.

**Décisions actées** : LLM = **Mistral** (inchangé) · Rapport = **RAG vectoriel local** (Chroma + embeddings
`mistral-embed`, reste dans l'écosystème Mistral, pas de clé supplémentaire) · Pas de déploiement K8s dans cette phase.

---

## Principes directeurs (agentic)

Conformément aux principes Development Seed pour les systèmes agentic scientifiques « production grade »
([EGU26-19885](https://meetingorganizer.copernicus.org/EGU26/EGU26-19885.html), *Making Scientific Data Accessible with
LLMs while Preserving Authority and Reliability*). Ces principes contraignent toute la conception ci-dessous :

1. **Le LLM orchestre, il ne calcule pas.** Le modèle choisit et enchaîne des tools bien définis ; il ne produit jamais
   de chiffres « de tête ». Tout résultat numérique provient d'un tool déterministe.
2. **Les données ne transitent pas par le modèle.** Les tools s'exécutent côté serveur sur le Zarr et **ne renvoient au
   contexte que des résultats compacts** (scalaires, petits tableaux agrégés, références d'artefacts/plots) — jamais les
   527k lignes brutes. Le contexte du LLM reste petit et borné quelle que soit la taille des données.
3. **Analyse par code, reproductible.** Pour les requêtes non triviales, le tool privilégié génère/exécute du **code
   xarray/pandas paramétré** dans un environnement restreint (Dataset ouvert en lecture seule) ; le code exécuté est
   **persisté** (provenance) et la sortie est résumée avant retour. Transformations auditables et rejouables.
4. **Sourcing transparent.** Chaque réponse cite ses sources : pour le rapport → page/section ; pour les données → la
   requête exécutée (variable, période, filtre logement, code). Vérifiabilité avant fluidité.
5. **Pas d'hallucination.** Si aucun tool ne couvre la question, l'agent le dit explicitement (cf. esprit du
   `SYSTEM_PROMPT` du squelette).

---

## Architecture cible

```
100PAC/ (nouveau dépôt git dédié)
├── data/log_002026.xlsx                       (séries temporelles, non versionnée si volumineuse)
├── data/PAC 2025 - Métadonnées.xlsx           (attributs statiques × 100 logements)
├── data/PAC 2025 - Description des données brutes.xlsx  (config installation × logement)
├── data/PAC 2025 - Dictionnaire des données.xlsx        (canaux → nom/grandeur/unité)
├── data/pac.zarr/                 (modèle de données xarray/Zarr, généré)
├── docs/Performance-PAC-Rapport-final.pdf
├── docs/devlog.md                 (journal de bord requis par bootstrap.md)
├── docs/data-model.md             (description du modèle Zarr)
├── backend/                       (ex-"chatbot skeleton/backend", espace retiré)
│   ├── src/chatbot/
│   │   ├── data/                  (NOUVEAU : ingestion + accès Zarr)
│   │   ├── rag/                   (NOUVEAU : extraction PDF + index vectoriel)
│   │   ├── tools/                 (data tools + report retrieval tool)
│   │   ├── agent/                 (agent.py, state.py étendus)
│   │   ├── llm.py, settings/, api/, chat/
│   └── store/chroma/             (index vectoriel persistant, généré)
└── helm/                          (ex-"chatbot skeleton/helm")
```

L'agent ReAct reçoit deux familles de tools : **report_search** (RAG sur le PDF) et **data tools** (requêtes/agrégats
sur le Zarr). Le LLM décide quel tool appeler selon la question.

---

## Phase 0 — Restructuration & dépôt git

- Le dossier `100PAC` n'est **pas** un dépôt git autonome (il vit dans le repo home-dir). Créer un dépôt dédié :
  `git init` à la racine `100PAC`, `.gitignore` (exclure `data/*.xlsx` volumineux, `data/pac.zarr/`, `backend/store/`,
  `.env`, `.venv`).
- Renommer `chatbot skeleton/` → déplacer `backend/` et `helm/` à la racine du projet (supprimer l'espace dans le chemin
  qui casse les scripts/Docker).
- Créer [docs/devlog.md](docs/devlog.md) (journal daté des étapes) — exigé par bootstrap.md.
- Commit initial du squelette + restructuration.

## Phase 1 — Préparation des données → Zarr

**Objectif** : un modèle xarray **multi-dimensionnel `logement × time`** stocké en Zarr, **dimensionné pour les 100
logements** et alimenté par les 4 fichiers source. La dimension `logement` porte de **riches coordonnées statiques**
(les 2 matrices de métadonnées) ; les variables temporelles (canaux mesurés) sont peuplées pour le(s) logement(s)
disponible(s) (ici `002026`), `NaN` ailleurs. C'est cette structure qui permet de répondre à « performance moyenne des
PAC air/eau » par sélection `xarray` sur la coord `type_source_froide`.

**Schéma du Dataset** :
- **Dimensions** : `logement` (100, coord = `["001026", …, "100016"]`), `time` (grille 1 min).
- **Coordonnées statiques par logement** (dim `logement`), issues de `Métadonnées.xlsx` + `Description des données
  brutes.xlsx` : `departement`, `altitude`, `type_habitation`, `surface_shab`, `tbase`, `deperditions`, `type_pac`,
  **`type_source_froide`** (air/eau | géothermique), `config_frigorifique`, `fluide`, `scop_declare_*`,
  `puissance_tbase`, présence appoints, config installation (ballon ECS, circuits, V3V, **appoint joule inclus dans la
  mesure thermique**…). → classification et filtrage.
- **Variables temporelles** (dims `logement × time`) : les canaux du dictionnaire (`pac`, `resistance_*`, `cc_*_calo`,
  `cc_*_frig`, températures, humidités…), chacune avec `attrs` `unit`/`grandeur` **issus du dictionnaire**.

**Implémentation** :
- Deps backend (`pyproject.toml`) : `pandas`, `xarray`, `zarr`, `openpyxl`, `numcodecs`.
- Script [backend/scripts/ingest-data](backend/scripts/ingest-data) + module `backend/src/chatbot/data/ingest.py` :
  1. Charger le **dictionnaire** (libellé→unité/grandeur) et les **2 matrices de métadonnées** (transposer : attribut en
     colonne, logement en index) → table statique des 100 logements + typage/parse des valeurs.
  2. Lire le(s) `log_*.xlsx` (lecture `read_only`/chunks ; 527k lignes). Parser `time` (tz `+02`/`+01`), trier,
     dédupliquer, réindexer sur grille 1 min régulière.
  3. Construire l'`xarray.Dataset` : coord `logement` (100) avec toutes les coords statiques ; variables temporelles
     `(logement, time)` peuplées pour `002026`. Attacher `attrs` (unité, grandeur, source) par variable.
  4. **Dérivés** stockés comme variables : énergie élec = ∫(`pac`+`resistance_*`) dt, énergie thermique nette =
     `cc_*_calo` − `cc_*_frig` ; **agrégats ré-échantillonnés** (`/raw`, `/hourly`, `/daily`, `/monthly`) en groupes Zarr
     séparés pour des requêtes rapides sans scanner 527k points.
  5. Écrire `data/pac.zarr` (**Zarr v3, `zarr>=3`**) avec **sharding** : chunks internes fins sur `time` (p. ex.
     horaire) **regroupés en un shard par jour** (`shards`/`chunks` du codec de sharding v3) → évite l'explosion du
     nombre de fichiers (1 fichier/jour au lieu de centaines de chunks), compression Blosc. Chunk aussi sur `logement`
     (1 logement/chunk) pour des lectures filtrées efficaces.
- Documenter dans [docs/data-model.md](docs/data-model.md) (dimensions, coords, variables, unités, conventions COP/SCOP).

**Sémantique des canaux — résolue par le dictionnaire** : `pac` = puissance électrique PAC (W), `resistance_*` = appoints
élec (W), `cc_*_calo`/`cc_*_frig` = énergie thermique cumulée (Wh, calories/frigories). Donc sur une période :
`COP = Σ ΔWh_thermique / Σ (W_élec × Δt)`. ⚠️ Seule subtilité à confirmer côté rapport (§2.3) / `Description des données
brutes` : le sens cumulatif des compteurs `cc_*` et si l'appoint joule est déjà inclus dans la mesure thermique selon le
logement (drapeau présent dans la description) — à gérer logement par logement dans la formule.

## Phase 2 — Extraction du rapport → RAG vectoriel

- Ajouter deps : `langchain-chroma` (ou `chromadb`), `pypdf`/`pymupdf` (extraction texte+layout), `langchain-mistralai`
  fournit déjà `MistralAIEmbeddings` (`mistral-embed`).
- Module `backend/src/chatbot/rag/extract.py` : extraire texte page par page (PyMuPDF pour préserver tableaux/structure),
  conserver les métadonnées (n° page, section) pour citer les sources.
- Module `backend/src/chatbot/rag/index.py` + script [backend/scripts/build-index](backend/scripts/build-index) :
  chunking (RecursiveCharacterTextSplitter, ~1000 tokens, overlap), embeddings `mistral-embed`, persistance Chroma dans
  `backend/store/chroma/`. Index construit **offline** (one-shot), pas au runtime.
- Le store est généré, pas versionné (régénérable via le script).

## Phase 3 — Agent : tools, LLM, state

Suivre le pattern exact du squelette (`@tool(...)`, docstring = description, `Command(update=...)`, ajout à la liste dans
`create_agent()`). **Tous les tools respectent les Principes directeurs** : exécution côté serveur, retour compact
(scalaires / petits tableaux / références), citation systématique. Aucun tool ne déverse de données brutes dans le
contexte.

- **report_search tool** (`tools/report.py`) : requête → retrieval Chroma (top-k) → renvoie passages **avec citations
  page/section**. Docstring orientant le LLM ("questions sur le rapport, méthodologie, conclusions, comparaison
  européenne…").
- **data tools paramétrés** (`tools/data.py`), sur `chatbot/data/access.py` (ouverture lazy read-only du Zarr) — couvrent
  les requêtes courantes de façon déterministe et sûre :
  - `list_logements` / `describe_fleet` : explorer les coords statiques (combien de PAC air/eau vs géothermiques, par
    département, SCOP déclaré moyen…) — questions « parc », sans série temporelle.
  - `query_measurements` : agrégat d'une variable sur période/résolution, **avec filtre sur les coords logement**
    (ex. `type_source_froide == "géothermique"`) → moyenne/min/max/somme (scalaire ou petite série déjà agrégée).
  - `compute_performance` : COP/SCOP réel sur une période (énergie thermique / électrique), par logement ou agrégé sur un
    sous-ensemble filtré ; comparable au `scop_declare_*`.
  - `plot_timeseries` : graphe (matplotlib → PNG base64) stocké en state, rendu dans l'UI (réutilise `Base64Image` de
    [state.py](chatbot%20skeleton/backend/src/chatbot/agent/state.py)) — c'est l'**artefact** (image) qui sort, pas les points.
- **analyse-par-code** (`tools/analyze.py`) — *cœur du principe « analyse par code reproductible »* : tool
  `run_data_analysis(code)` où le LLM génère du **code xarray/pandas** exécuté dans un **environnement restreint**
  (Dataset `ds` ouvert read-only, pas d'I/O réseau/fichier, builtins limités, timeout). Seul le **résultat résumé** (scalaire,
  `DataFrame.describe()`, ou artefact) revient au contexte ; le **code exécuté est persisté** (state + log) comme trace de
  provenance et rejouable. Couvre les questions non prévues par les tools paramétrés sans élargir le contexte.
- Étendre `AgentState` ([state.py]) : champ image/plot, résultats tabulaires compacts, **et `provenance`** (code exécuté +
  requêtes + citations rapport) pour transparence/audit.
- `SYSTEM_PROMPT` ([agent.py]) : rôle = analyste PAC qui **orchestre des tools** ; interdit de produire des chiffres hors
  tool ; impose de citer source (page rapport / requête data) ; dit explicitement quand l'info est absente. Garder Mistral
  dans [llm.py] (passer à `mistral-large-latest` si l'orchestration multi-tool / la génération de code est insuffisante).

## Phase 4 — API & UI

- L'endpoint `/chat` (stream NDJSON) et l'UI Streamlit existants fonctionnent déjà avec le pattern state/messages/image —
  vérifier qu'ils rendent correctement les nouveaux graphes et résultats data (le rendu base64 image existe déjà dans
  [chat/app.py]). Ajouter l'affichage des tableaux, **des citations rapport (page/section) et de la provenance**
  (code/requête exécutés) — exigé par le principe de sourcing transparent.
- `.env` : `MISTRAL_API_KEY` (déjà prévu).

## Phase 5 — Tests & validation

- Tests unitaires (pytest, pattern `tests/conftest.py` existant) : ingestion (schéma Zarr, dérivés), accès data
  (agrégats déterministes), formules COP sur échantillon connu, RAG (retrieval renvoie des passages pertinents).
- Test d'intégration API : `/health` (existant) + `/chat` sur questions de référence.
- **Validation métier** : jeu de questions de référence (ex. « COP moyen de la PAC sur la saison de chauffe ? »,
  « Quels enseignements pour les PAC géothermiques ? », « consommation ECS vs chauffage ? ») avec réponses attendues
  croisées au rapport — comme demandé par bootstrap.md (comparaison aux analystes humains).
- **Vérifier les Principes directeurs** : chaque réponse chiffrée porte une source (citation page ou requête/code),
  l'`analyze` tool s'exécute en bac à sable (pas d'I/O, timeout), et **aucune donnée brute volumineuse ne remonte au
  contexte** (inspecter les tool messages).
- `scripts/lint` (ruff + mypy) doit passer.

## Phase 6 — Préparation déploiement (sans déployer)

- Adapter le chart Helm ([helm/chatbot/](chatbot%20skeleton/helm/chatbot/)) : volume persistant pour `data/pac.zarr` et
  `store/chroma/` (ou build dans l'image / init-container), `example.values.yaml` (hosts, registry, ressources),
  secret `MISTRAL_API_KEY`.
- Mettre à jour le `Dockerfile` (copier data/index ou étape de build d'index).
- (Stretch) workflow GitHub Actions de CD. **Pas de `helm upgrade` réel** dans cette phase.

---

## Fichiers clés à créer / modifier

- Créer : `backend/src/chatbot/data/{ingest,metadata,access}.py` (`metadata.py` = chargement dictionnaire + 2 matrices),
  `backend/src/chatbot/rag/{extract,index}.py`,
  `backend/src/chatbot/tools/{report,data,analyze}.py` (`analyze.py` = exécution code restreinte + provenance),
  scripts `ingest-data` / `build-index`, `docs/devlog.md`,
  `docs/data-model.md`, `.gitignore`.
- Modifier : `backend/pyproject.toml` (deps), `backend/src/chatbot/agent/agent.py` (tools + prompt),
  `agent/state.py` (state étendu), `tools/__init__.py`, `helm/...`, `Dockerfile`.
- Réutiliser : pattern tool de `tools/cat.py`, `Base64Image` de `agent/state.py`, le stream NDJSON de `api/app.py`, le
  rendu image de `chat/app.py`, `settings/__init__.py` (env), scripts `install`/`api`/`chat`/`test`/`lint`.

## Vérification end-to-end

1. `scripts/install` puis `scripts/ingest-data` → `data/pac.zarr` créé ; inspecter avec `xarray.open_zarr` (dims/vars).
2. `scripts/build-index` → `store/chroma/` peuplé ; test retrieval manuel.
3. `scripts/test` + `scripts/lint` verts.
4. `scripts/api` (terminal 1) + `scripts/chat` (terminal 2, :8501) ; poser les questions de référence et vérifier :
   réponse rapport avec citation, agrégat data correct, COP plausible, graphe affiché.
5. Comparer les réponses chiffrées aux valeurs du rapport (cohérence).

## Questions ouvertes (à lever en cours de route)

- Sens cumulatif exact des compteurs `cc_*` et gestion de l'« appoint joule inclus dans la mesure thermique » par
  logement (drapeau dans `Description des données brutes`) → affine la formule COP/SCOP.
- Le détail temporel n'est fourni que pour `002026` : confirmer que les séries des 99 autres logements seront fournies
  plus tard (le modèle reste dimensionné 100 et n'aura qu'à être réalimenté).
- `mistral-small` suffisant pour l'orchestration multi-tool, ou passer à `mistral-large` ?
