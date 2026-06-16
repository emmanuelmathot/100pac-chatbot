# Modèle de données — `data/pac.zarr`

> **Sources (ADEME, ouvertes)** — mesures :
> <https://data.ademe.fr/datasets/pac-campagne-de-mesure-100-pacs> ·
> rapport :
> <https://librairie.ademe.fr/batiment/8617-mesure-des-performances-de-100-pac-air-eau-et-eau-eau-installees-en-maisons-individuelles.html>
> Reproduction : voir le [README](../README.md#sources-de-données-ademe-ouvertes).

Modèle xarray/Zarr (v3) construit par [`backend/scripts/ingest-data`](../backend/scripts/ingest-data)
(module `chatbot.data.ingest`) à partir des fichiers de référence (métadonnées,
dictionnaire) et d'un répertoire de journaux `log_<id>.csv` (un par logement). Couvre
les **100 logements** instrumentés, avec séries temporelles au pas 1 min.

Les journaux ont des **schémas hétérogènes** (un logement mesure l'ECS, un autre des
sous-circuits de chauffage, un autre la géothermie...) : l'ingestion prend l'**union**
des canaux (~48) et chaque logement remplit ce qu'il possède (`NaN` ailleurs). La grille
temporelle est l'**union** des plages (les logements ne couvrent pas tous la même période ;
hors couverture d'un logement → `NaN`).

L'ingestion est **économe en mémoire** : le store est initialisé en lazy (dask) puis écrit
**logement par logement** (region writes), sans jamais charger les 100 ensemble.

## Groupes

| Groupe | Dimensions | Contenu |
|--------|-----------|---------|
| `fleet` | `logement` (100) | Caractéristiques statiques par logement (métadonnées + config installation). |
| `raw` | `logement × time` | Mesures au pas **1 minute** (UTC). |
| `hourly` | `logement × time` | Agrégats horaires. |
| `daily` | `logement × time` | Agrégats journaliers. |
| `monthly` | `logement × time` | Agrégats mensuels. |

Tous les groupes partagent la dimension `logement` (100), indexée par l'identifiant
de logement (ex. `"002026"`).

### Agrégation des compteurs hétérogènes

Pour l'énergie thermique, l'ingestion choisit par logement : compteur de chauffage
**agrégé** `cc_chauffage_calo` s'il existe, sinon **somme des sous-circuits**
(`cc_chauffage_{pl,rad,r1,rdc,reseau}_calo`) ; plus l'ECS (`cc_ecs_*`) et le compteur
commun chauffage+ECS (`cc_ch_ecs_*`) quand les usages ne sont pas séparés. L'électricité
totale somme `pac` + appoints (`resistance`, `resistance_chauffage`, `resistance_ecs`).

## Coordonnées statiques (`fleet`)

47 attributs, dont les plus structurants :

- `type_source_froide` — **`air/eau` (90)** vs **`eau/eau` / géothermie (10)** : classification clé du parc.
- `type_pac`, `configuration_frigorifique`, `fluide_frigorigene`, `emetteurs`.
- `departement`, `altitude`, `surface_shab`, `tbase`, `deperditions_du_logement`.
- `scop_declare_{basse,moyenne,haute}_temperature` — SCOP constructeur (référence de comparaison).
- `puissance_thermique_a_tbase_{35,45,55}c`.
- `inst_*` — configuration d'installation (ballons, circuits, V3V) et drapeaux
  **« appoint joule inclus dans la mesure thermique »** (chauffage / ECS / commune).

## Variables temporelles

Canaux bruts (unités du dictionnaire) + dérivés :

| Variable | Grandeur | Unité | Agrégation |
|----------|----------|-------|------------|
| `pac` | Puissance électrique PAC | W | moyenne |
| `resistance_chauffage`, `resistance_ecs` | Puissance appoint élec | W | moyenne |
| `cc_chauffage_calo`, `cc_ecs_calo` | Énergie thermique (calories) | Wh | somme |
| `cc_chauffage_frig`, `cc_ecs_frig` | Énergie thermique (frigories) | Wh | somme |
| `t_*`, `h_amb_sejour`, `t_meteo` | Température / hygrométrie | °C / %HR | moyenne |
| `elec_power_w` | Puissance élec totale (PAC + appoints) | W | moyenne |
| `elec_energy_wh` | Énergie élec (= P/60 par minute) | Wh | somme |
| `thermal_calo_wh`, `thermal_frig_wh` | Énergie thermique fournie / extraite | Wh | somme |
| `thermal_net_wh` | Énergie thermique utile nette (calo − frig) | Wh | somme |
| `cop` *(groupes agrégés)* | COP de période = `thermal_net_wh / elec_energy_wh` | - | — |

### Convention énergétique (important)

Les compteurs `cc_*` sont des **incréments d'énergie par minute (Wh)**, *non*
cumulatifs (vérifié : la colonne n'est pas monotone). Sur une période :

```
énergie élec (Wh)      = Σ P_W / 60
énergie thermique (Wh) = Σ (calo − frig)
COP                    = énergie thermique utile / énergie élec
```

⚠️ **COP / SCOP** : le `cop` stocké est un indicateur brut sur la période. Le
**SCOP pertinent se calcule sur la saison de chauffe** (en été, `net = calo − frig`
devient négatif car la PAC produit des frigories — froid/dégivrage — sans usage
chauffage). Exemple `002026` : COP de saison de chauffe (oct→avr) ≈ **2.26**, vs
SCOP déclaré 4.43 — écart réel typique mis en évidence par l'audit. Le drapeau
`inst_appoint_joule_inclus_dans_mesure_thermique_*` indique si l'appoint joule est
déjà compté dans la mesure thermique, à prendre en compte logement par logement.

## Stockage

Zarr v3 avec **sharding par logement** : chunks internes `(1 logement, 1 jour)`
regroupés en `shards = (1 logement, tout le temps)` → **1 fichier de shard par
logement et par variable**. Ce choix permet des **écritures par région indépendantes**
(un logement à la fois, sans amplification ni conflit) tout en bornant le nombre de
fichiers. Compression Blosc par défaut.

Ordre de grandeur (jeu complet 100 logements) : dimension `time` ≈ **733 020** pas
(grille globale 2023-09 → 2025-02), ~54 variables, store ≈ **650 Mo**.

## Échelle du parc — résultats indicatifs

COP réel moyen de saison de chauffe (via `fleet_performance` / outil
`compare_fleet_performance`) :

| Type | n | COP réel moyen | SCOP déclaré moyen |
|------|---|----------------|--------------------|
| air/eau | 90 | ≈ 3,56 | 4,39 |
| eau/eau (géothermie) | 10 | ≈ 4,03 | 5,02 |

La géothermie surperforme l'aérothermie ; les deux restent sous le SCOP constructeur —
constat central de l'audit.
