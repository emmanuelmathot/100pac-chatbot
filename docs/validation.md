# Validation

Deux niveaux de validation, conformément au cahier des charges (comparaison aux
résultats des analystes) et aux principes directeurs.

## 1. Tests automatisés (`scripts/test`)

Déterministes, sans LLM ni gros fichiers (store Zarr synthétique en fixture) :

- `test_ingest.py` — sémantique énergétique : `cc_*` sommés, puissances moyennées,
  dérivés `elec_energy_wh = P/60`, `thermal_net = calo − frig`.
- `test_analytics.py` — agrégats (mean/sum), COP de période, **filtre saison de chauffe**
  (les jours d'été sont exclus), filtrage du parc par `type_source_froide`.
- `test_metadata.py` — slugification, dédup, identifiants de logement, coercition FR.
- `test_analyze_tool.py` — le tool d'analyse exécute du code valide **et bloque
  `import` / `open`** (bac à sable), avec provenance enregistrée.
- `test_health.py` — endpoint `/health`.

17 tests, verts.

## 2. Validation métier (`scripts/validate`, LLM live)

L'agent est exécuté sur un jeu de questions de référence ; on vérifie qu'il
**orchestre le bon outil** et produit une réponse cohérente avec le rapport / les
mesures. Résultats observés (logement instrumenté `002026`) :

| Question | Outil attendu | Résultat |
|----------|---------------|----------|
| Combien de PAC géothermiques ? | `describe_fleet` | **10** (eau/eau) sur 100 ✓ |
| COP réel de saison vs SCOP déclaré ? | `compute_performance` | **2,26** vs **4,43** déclaré ✓ |
| Consommation électrique annuelle ? | `compute_performance` | **5 530 kWh** (période complète) ✓ |
| Causes de sous-performance (rapport) ? | `search_report` | synthèse + citations p. ✓ |
| Tracer la température météo ? | `plot_measurement` | graphe PNG affiché ✓ |

5/5 questions déclenchent l'outil attendu.

### Cohérence des chiffres

- SCOP réel de saison de chauffe `002026` ≈ **2,26**, nettement sous le SCOP déclaré
  4,43 — l'écart réel/constructeur est précisément le constat central de l'audit ADEME.
- Bilan annuel : ~5 530 kWh élec, ~9 889 kWh thermiques nets.

### Conformité aux principes directeurs

- **Orchestration** : tout chiffre provient d'un outil déterministe (vérifié via les
  `tool_calls` du flux).
- **Données hors contexte** : les outils renvoient des scalaires / petites tables /
  artefacts ; aucune série 1 min ne remonte au LLM.
- **Provenance / sourcing** : citations rapport (page/section) dans `state.citations` ;
  code et requêtes dans `state.provenance` ; `compute_performance` renvoie la période
  effective réelle (`period_effective`) pour éviter toute date inventée.
- **Bac à sable** : `run_data_analysis` bloque imports et I/O (testé).
