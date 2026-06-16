"""Accès lazy au modèle Zarr pour les tools de l'agent.

Conformément aux principes directeurs, les données ne transitent pas par le LLM :
ces helpers ouvrent le store en lecture seule et **ne renvoient que des résultats
compacts** (scalaires, petites tables, dictionnaires agrégés). Aucun déversement
des séries 1 min complètes.
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd
import xarray as xr

from chatbot import paths

RESOLUTIONS = ("raw", "hourly", "daily", "monthly")


def _check_store() -> None:
    if not paths.ZARR_PATH.exists():
        raise FileNotFoundError(
            f"Modèle Zarr absent ({paths.ZARR_PATH}). "
            "Lancez `scripts/ingest-data` pour le générer."
        )


@lru_cache(maxsize=None)
def open_group(group: str) -> xr.Dataset:
    """Ouvre un groupe du store (``fleet``, ``raw``, ``hourly``...) en lazy + cache."""
    _check_store()
    return xr.open_zarr(paths.ZARR_PATH, group=group)


def fleet() -> xr.Dataset:
    """Caractéristiques statiques des 100 logements (dim ``logement``)."""
    return open_group("fleet")


def measurements(resolution: str = "daily") -> xr.Dataset:
    """Mesures à la résolution demandée (``raw``/``hourly``/``daily``/``monthly``)."""
    if resolution not in RESOLUTIONS:
        raise ValueError(f"résolution inconnue {resolution!r}, attendu {RESOLUTIONS}")
    return open_group(resolution)


def fleet_dataframe() -> pd.DataFrame:
    """Table statique du parc en DataFrame (index = logement)."""
    return fleet().to_dataframe()


def available_logements() -> list[str]:
    """Identifiants des logements dont on possède les séries temporelles."""
    return [str(v) for v in measurements("daily").logement.values]


def select_logements(**criteria: object) -> list[str]:
    """Identifiants de logements satisfaisant des critères d'égalité sur le parc.

    Exemple : ``select_logements(type_source_froide="eau/eau")`` -> liste des PAC
    géothermiques. Les valeurs sont comparées en chaîne (insensible aux espaces).
    """
    df = fleet_dataframe()
    mask = pd.Series(True, index=df.index)
    for key, value in criteria.items():
        if key not in df.columns:
            raise KeyError(f"attribut inconnu {key!r}")
        mask &= df[key].astype(str).str.strip() == str(value).strip()
    return [str(i) for i in df.index[mask]]


def list_variables(resolution: str = "daily") -> dict[str, dict]:
    """Variables disponibles -> leurs attributs (nom, grandeur, unité, agrégation)."""
    ds = measurements(resolution)
    return {str(v): dict(ds[v].attrs) for v in ds.data_vars}
