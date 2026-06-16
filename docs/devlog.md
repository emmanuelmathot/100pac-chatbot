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
