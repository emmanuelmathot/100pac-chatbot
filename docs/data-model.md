# Modèle de données — `data/pac.zarr`

Modèle xarray/Zarr (v3) construit par [`backend/scripts/ingest-data`](../backend/scripts/ingest-data)
(module `chatbot.data.ingest`) à partir des 4 fichiers source. Conçu pour les
**100 logements** instrumentés et alimenté en séries temporelles pour les
logements dont on possède le journal 1 min (actuellement `002026`).

## Groupes

| Groupe | Dimensions | Contenu |
|--------|-----------|---------|
| `fleet` | `logement` (100) | Caractéristiques statiques par logement (métadonnées + config installation). |
| `raw` | `logement × time` | Mesures au pas **1 minute** (UTC). |
| `hourly` | `logement × time` | Agrégats horaires. |
| `daily` | `logement × time` | Agrégats journaliers. |
| `monthly` | `logement × time` | Agrégats mensuels. |

La dimension `logement` du groupe `fleet` couvre les 100 logements ; les groupes
de mesures ne couvrent que les logements disponibles. La jointure se fait par
l'identifiant de logement (ex. `"002026"`).

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

Zarr v3 avec **sharding** : les groupes au pas minute sont découpés en
`chunks = (1 logement, 1 jour)` regroupés en `shards = (tous logements, 1 jour)`
→ **1 fichier de shard par jour et par variable** (≈ 367), ce qui borne le nombre
de fichiers malgré 527 040 pas de temps. Compression Blosc par défaut.
