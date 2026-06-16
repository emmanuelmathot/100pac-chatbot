"""Fonctions d'analyse déterministes sur le modèle Zarr.

Logique métier pure (sans LangChain) : agrégats, performance COP/SCOP, résumé du
parc, graphes. Les tools de l'agent en sont de fines enveloppes. Tout ici renvoie
des **résultats compacts** (dicts, scalaires, PNG) — jamais les séries 1 min.
"""

from __future__ import annotations

import base64
from io import BytesIO

import numpy as np
import pandas as pd
import xarray as xr

from chatbot.data import access

# Saison de chauffe : mois où le chauffage domine (oct → avr).
HEATING_MONTHS = {10, 11, 12, 1, 2, 3, 4}


def _sel_time(ds: xr.Dataset, start: str | None, end: str | None) -> xr.Dataset:
    """Restreint un Dataset à une fenêtre temporelle [start, end] (dates ISO)."""
    if start or end:
        ds = ds.sel(time=slice(start, end))
    return ds


def fleet_summary() -> dict:
    """Vue d'ensemble du parc des 100 logements (compacte)."""
    df = access.fleet_dataframe()
    by_source = df["type_source_froide"].value_counts().to_dict()
    measured = access.available_logements()
    return {
        "n_logements": int(len(df)),
        "par_type_source_froide": {str(k): int(v) for k, v in by_source.items()},
        "par_type_pac": {
            str(k): int(v) for k, v in df["type_pac"].value_counts().items()
        },
        "scop_declare_basse_temperature_moyen": round(
            float(
                pd.to_numeric(
                    df["scop_declare_basse_temperature"], errors="coerce"
                ).mean()
            ),
            2,
        ),
        "departements": sorted(
            {
                str(int(x))
                for x in pd.to_numeric(df["departement"], errors="coerce").dropna()
            }
        ),
        "logements_avec_mesures": measured,
    }


def aggregate(
    variable: str,
    *,
    logement: str,
    start: str | None = None,
    end: str | None = None,
    resolution: str = "daily",
    how: str = "mean",
) -> dict:
    """Agrège une variable sur une période pour un logement. Résultat scalaire."""
    ds = _sel_time(access.measurements(resolution), start, end)
    if logement not in [str(v) for v in ds.logement.values]:
        raise KeyError(f"pas de mesures pour le logement {logement!r}")
    if how not in ("mean", "sum", "min", "max"):
        raise ValueError(f"agrégation inconnue {how!r}")
    da = ds[variable].sel(logement=logement)
    value = float(getattr(da, how)().values)
    return {
        "variable": variable,
        "logement": logement,
        "resolution": resolution,
        "how": how,
        "period": [start, end],
        "value": round(value, 3),
        "units": ds[variable].attrs.get("units", ""),
    }


def performance(
    logement: str,
    *,
    start: str | None = None,
    end: str | None = None,
    heating_season_only: bool = False,
) -> dict:
    """Bilan énergétique et COP réel d'un logement sur une période.

    Compare au SCOP constructeur déclaré. Si ``heating_season_only``, ne retient
    que les mois de chauffe (oct→avr) — le COP estival n'a pas de sens (frigories).
    """
    daily = _sel_time(access.measurements("daily"), start, end)
    if logement not in [str(v) for v in daily.logement.values]:
        raise KeyError(f"pas de mesures pour le logement {logement!r}")
    d = daily.sel(logement=logement)
    if heating_season_only:
        months = d["time"].dt.month
        d = d.where(months.isin(list(HEATING_MONTHS)), drop=True)

    elec_wh = float(d["elec_energy_wh"].sum())
    calo_wh = float(d["thermal_calo_wh"].sum())
    frig_wh = float(d["thermal_frig_wh"].sum())
    net_wh = float(d["thermal_net_wh"].sum())
    cop = net_wh / elec_wh if elec_wh > 0 else float("nan")

    fleet = access.fleet_dataframe()
    declared = None
    if logement in fleet.index:
        declared = pd.to_numeric(
            pd.Series([fleet.loc[logement, "scop_declare_basse_temperature"]]),
            errors="coerce",
        ).iloc[0]

    return {
        "logement": logement,
        "period": [start, end],
        "heating_season_only": heating_season_only,
        "elec_kwh": round(elec_wh / 1000, 1),
        "thermal_calo_kwh": round(calo_wh / 1000, 1),
        "thermal_frig_kwh": round(frig_wh / 1000, 1),
        "thermal_net_kwh": round(net_wh / 1000, 1),
        "cop_reel": round(cop, 2),
        "scop_declare_basse_temperature": (
            None
            if declared is None or np.isnan(declared)
            else round(float(declared), 2)
        ),
        "n_jours": int(d["time"].size),
    }


def timeseries_png(
    variable: str,
    *,
    logement: str,
    start: str | None = None,
    end: str | None = None,
    resolution: str = "daily",
) -> str:
    """Trace une variable dans le temps -> PNG encodé base64 (artefact compact)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ds = _sel_time(access.measurements(resolution), start, end)
    da = ds[variable].sel(logement=logement)
    times = pd.to_datetime(da["time"].values)

    fig, ax = plt.subplots(figsize=(9, 3.5))
    ax.plot(times, da.values, linewidth=0.8)
    ax.set_title(f"{variable} — logement {logement} ({resolution})")
    ax.set_ylabel(ds[variable].attrs.get("units", ""))
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("utf-8")
