"""Ingestion des journaux par logement vers un modèle xarray/Zarr ``logement × time``.

Construit ``data/pac.zarr`` (Zarr v3) à partir d'un répertoire de journaux
``log_<id>.csv``, un par logement. Les schémas de colonnes diffèrent
d'un logement à l'autre (sous-circuits, ECS, géothermie) : on prend l'**union** des
canaux, chaque logement remplit ce qu'il possède (NaN ailleurs).

**Mémoire** : les journaux (100 × ~40 Mo) ne sont jamais chargés ensemble. Le store
est initialisé en lazy (dask) puis **écrit logement par logement (region writes)**, de
sorte que seul un logement est en mémoire à la fois.

Sémantique (cf. dictionnaire) : ``pac`` / ``resistance*`` = puissances (W) ;
``cc_*`` = incréments d'énergie thermique par minute (Wh, non cumulatifs). D'où, sur
une période : énergie élec = Σ P/60 ; énergie thermique utile = Σ (calo − frig).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import dask.array as da
import numpy as np
import pandas as pd
import xarray as xr

from chatbot import paths
from chatbot.data import metadata

STEP = pd.Timedelta(minutes=1)
MINUTES_PER_DAY = 1440

# Canaux électriques (puissance W) entrant dans la consommation totale.
ELEC_CHANNELS = ["pac", "resistance", "resistance_chauffage", "resistance_ecs"]
# Compteurs de chaleur "chauffage" : compteur agrégé sinon somme des sous-circuits.
CHAUFFAGE_SUB = ["pl", "rad", "r1", "rdc", "reseau"]

_SUM_DERIVED = {
    "elec_energy_wh",
    "thermal_calo_wh",
    "thermal_frig_wh",
    "thermal_net_wh",
}


def _agg_kind(var: str) -> str:
    """Somme pour les énergies (compteurs ``cc_*`` et dérivés), moyenne sinon."""
    if var.startswith("cc_") or var in _SUM_DERIVED:
        return "sum"
    return "mean"


# ---------------------------------------------------------------------------
# Découverte et lecture des journaux
# ---------------------------------------------------------------------------
def discover_logs(source: Path | None = None) -> list[tuple[str, Path]]:
    """Liste triée ``(logement_id, chemin)`` des journaux ``log_<id>.csv``."""
    source = Path(source) if source else paths.LOGS_DIR
    files = sorted(source.glob("log_*.csv"))
    return [(p.stem.replace("log_", ""), p) for p in files]


def _first_last_time(path: Path) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Premier et dernier horodatage d'un CSV (journaux chronologiques)."""
    with open(path, "rb") as f:
        f.readline()  # en-tête
        first = f.readline().split(b",", 1)[0]
        f.seek(0, 2)
        size = f.tell()
        block = min(4096, size)
        f.seek(size - block)
        last_line = f.read().splitlines()[-1]
        last = last_line.split(b",", 1)[0]
    # Naïf UTC (Zarr v3 n'encode pas les datetimes tz-aware).
    t0 = pd.to_datetime(first.decode(), utc=True).tz_convert(None)
    t1 = pd.to_datetime(last.decode(), utc=True).tz_convert(None)
    return t0, t1


def _read_one(path: Path, grid: pd.DatetimeIndex) -> pd.DataFrame:
    """Lit un journal CSV, met le temps en UTC, réindexe sur la grille globale."""
    df = pd.read_csv(path)
    # Temps en UTC naïf (cohérent avec la grille globale, encodable en Zarr v3).
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_convert(None)
    df = (
        df.dropna(subset=["time"])
        .drop_duplicates(subset=["time"], keep="first")
        .set_index("time")
        .sort_index()
    )
    df = df.apply(pd.to_numeric, errors="coerce").astype("float32")
    return df.reindex(grid)


def _scan(logs: list[tuple[str, Path]]) -> tuple[list[str], pd.Timestamp, pd.Timestamp]:
    """Union des canaux et fenêtre temporelle globale sur l'ensemble des journaux."""
    channels: set[str] = set()
    tmin = tmax = None
    for _, path in logs:
        header = pd.read_csv(path, nrows=0)
        channels.update(c for c in header.columns if c != "time")
        t0, t1 = _first_last_time(path)
        tmin = t0 if tmin is None else min(tmin, t0)
        tmax = t1 if tmax is None else max(tmax, t1)
    return sorted(channels), tmin, tmax


# ---------------------------------------------------------------------------
# Variables dérivées
# ---------------------------------------------------------------------------
def _add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les variables dérivées (énergies électrique et thermique).

    Gère l'hétérogénéité : appoint commun ``resistance`` ou séparé, compteur de
    chauffage agrégé ou par sous-circuit, ECS séparée ou compteur commun.
    """

    def col(name: str) -> pd.Series:
        if name in df.columns:
            return df[name].fillna(0.0)
        return pd.Series(0.0, index=df.index, dtype="float32")

    def heat(kind: str) -> pd.Series:
        """Chaleur (``calo``/``frig``) : agrégé chauffage + sous-circuits + ECS + commun."""
        if f"cc_chauffage_{kind}" in df.columns:
            chauffage = col(f"cc_chauffage_{kind}")
        else:
            chauffage = sum(
                (col(f"cc_chauffage_{s}_{kind}") for s in CHAUFFAGE_SUB),
                start=pd.Series(0.0, index=df.index, dtype="float32"),
            )
        ecs = col(f"cc_ecs_{kind}")
        combined = col(f"cc_ch_ecs_{kind}")  # usages non séparés
        return chauffage + ecs + combined

    df["elec_power_w"] = sum(
        (col(c) for c in ELEC_CHANNELS),
        start=pd.Series(0.0, index=df.index, dtype="float32"),
    )
    df["elec_energy_wh"] = df["elec_power_w"] / 60.0
    calo = heat("calo")
    frig = heat("frig")
    df["thermal_calo_wh"] = calo
    df["thermal_frig_wh"] = frig
    df["thermal_net_wh"] = calo - frig
    return df


def _channel_attrs(var: str, dictionary: dict[str, metadata.ChannelMeta]) -> dict:
    meta = dictionary.get(var)
    if meta is not None:
        return {"long_name": meta.name, "quantity": meta.quantity, "units": meta.unit}
    derived = {
        "elec_power_w": (
            "Puissance électrique totale (PAC + appoints)",
            "Puissance électrique",
            "W",
        ),
        "elec_energy_wh": ("Énergie électrique consommée", "Energie électrique", "Wh"),
        "thermal_calo_wh": (
            "Énergie thermique fournie (calories)",
            "Energie thermique",
            "Wh",
        ),
        "thermal_frig_wh": (
            "Énergie thermique extraite (frigories)",
            "Energie thermique",
            "Wh",
        ),
        "thermal_net_wh": (
            "Énergie thermique utile nette (calo − frig)",
            "Energie thermique",
            "Wh",
        ),
    }
    if var in derived:
        name, qty, unit = derived[var]
        return {"long_name": name, "quantity": qty, "units": unit}
    return {}


# Variables dérivées toujours présentes (calculées pour chaque logement).
DERIVED_VARS = [
    "elec_power_w",
    "elec_energy_wh",
    "thermal_calo_wh",
    "thermal_frig_wh",
    "thermal_net_wh",
]


# ---------------------------------------------------------------------------
# Initialisation lazy + écritures par région
# ---------------------------------------------------------------------------
def _init_group(
    group: str,
    logement_ids: list[str],
    time_index: pd.DatetimeIndex,
    variables: list[str],
    dictionary: dict[str, metadata.ChannelMeta],
    *,
    shard: bool,
) -> None:
    """Crée le schéma (lazy, NaN) d'un groupe de mesures, prêt aux region writes."""
    n_log, n_t = len(logement_ids), len(time_index)
    chunk_t = min(MINUTES_PER_DAY, n_t)
    # Un shard par logement couvrant tout le temps (chunks journaliers internes).
    shard_t = ((n_t + chunk_t - 1) // chunk_t) * chunk_t
    # Les chunks dask du template s'alignent sur l'unité d'écriture (shard si sharding).
    dask_chunks = (1, shard_t) if shard else (1, chunk_t)
    data_vars = {}
    encoding = {}
    for var in variables:
        arr = da.full((n_log, n_t), np.nan, dtype="float32", chunks=dask_chunks)
        data_vars[var] = xr.DataArray(
            arr,
            dims=("logement", "time"),
            attrs={**_channel_attrs(var, dictionary), "aggregation": _agg_kind(var)},
        )
        if shard:
            # Écritures indépendantes par logement, pas d'amplification, fichiers bornés.
            encoding[var] = {"chunks": (1, chunk_t), "shards": (1, shard_t)}
    ds = xr.Dataset(data_vars, coords={"logement": logement_ids, "time": time_index})
    ds.to_zarr(
        paths.ZARR_PATH,
        group=group,
        mode="a",
        compute=False,
        zarr_format=3,
        encoding=encoding or None,
    )


def _row_dataset(df: pd.DataFrame, variables: list[str]) -> xr.Dataset:
    """DataFrame (index time) d'un logement -> Dataset (1, T) pour region write."""
    data_vars = {}
    for var in variables:
        series = df[var] if var in df.columns else pd.Series(np.nan, index=df.index)
        data_vars[var] = (
            ("logement", "time"),
            series.to_numpy(dtype="float32")[None, :],
        )
    return xr.Dataset(data_vars)


def _resample_row(
    df_valid: pd.DataFrame, freq: str, variables: list[str]
) -> pd.DataFrame:
    """Ré-échantillonne le journal valide d'un logement (somme énergies, moyenne sinon)."""
    sum_cols = [c for c in df_valid.columns if _agg_kind(c) == "sum"]
    mean_cols = [c for c in df_valid.columns if _agg_kind(c) == "mean"]
    res = df_valid.resample(freq)
    out = pd.concat([res[sum_cols].sum(min_count=1), res[mean_cols].mean()], axis=1)
    out["cop"] = np.where(
        out["elec_energy_wh"] > 0, out["thermal_net_wh"] / out["elec_energy_wh"], np.nan
    )
    return out.reindex(columns=variables)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def _fleet_dataset(fleet: pd.DataFrame) -> xr.Dataset:
    data_vars = {}
    for col in fleet.columns:
        series = fleet[col]
        numeric = pd.to_numeric(series, errors="coerce")
        if series.notna().any() and numeric.notna().sum() >= series.notna().sum():
            values = numeric.to_numpy(dtype="float64")
        else:
            values = series.fillna("").astype(str).to_numpy()
        data_vars[col] = xr.DataArray(values, dims=("logement",))
    return xr.Dataset(data_vars, coords={"logement": fleet.index.to_numpy()})


def build(source: Path | None = None) -> None:
    """Construit ``data/pac.zarr`` à partir d'un répertoire de journaux."""
    dictionary = metadata.load_dictionary()
    fleet = metadata.load_fleet_metadata()
    logs = discover_logs(source)
    if not logs:
        raise FileNotFoundError(
            f"Aucun journal log_*.csv/xlsx dans {source or paths.LOGS_DIR}"
        )

    if paths.ZARR_PATH.exists():
        shutil.rmtree(paths.ZARR_PATH)

    # 1) Parc statique (100 logements).
    _fleet_dataset(fleet).to_zarr(
        paths.ZARR_PATH, group="fleet", mode="w", zarr_format=3
    )
    print(f"[fleet] {len(fleet)} logements, {len(fleet.columns)} attributs")

    # 2) Union des canaux + fenêtre temporelle globale.
    print(f"[scan] {len(logs)} journaux...")
    channels, tmin, tmax = _scan(logs)
    raw_vars = channels + DERIVED_VARS
    grid = pd.date_range(tmin, tmax, freq=STEP, name="time")
    ids = [lid for lid, _ in logs]
    print(
        f"[scan] {len(channels)} canaux, grille {tmin.date()}→{tmax.date()} ({len(grid)} pas)"
    )

    # 3) Schémas lazy (raw minute + agrégats).
    res_specs = {"hourly": "1h", "daily": "1D", "monthly": "1MS"}
    res_grids = {
        g: pd.date_range(
            grid[0].floor("D") if f != "1MS" else grid[0].normalize(),
            grid[-1],
            freq=f,
            name="time",
        )
        for g, f in res_specs.items()
    }
    res_vars = raw_vars + ["cop"]
    _init_group("raw", ids, grid, raw_vars, dictionary, shard=True)
    for g in res_specs:
        _init_group(g, ids, res_grids[g], res_vars, dictionary, shard=False)

    # 4) Écriture logement par logement (region writes).
    for i, (lid, path) in enumerate(logs):
        df = _add_derived(_read_one(path, grid))
        region = {"logement": slice(i, i + 1), "time": slice(0, len(grid))}
        _row_dataset(df, raw_vars).to_zarr(paths.ZARR_PATH, group="raw", region=region)
        # Agrégats : sur la plage réellement couverte, réindexée sur la grille globale.
        valid = df.dropna(how="all")
        for g, f in res_specs.items():
            agg = _resample_row(valid, f, res_vars).reindex(res_grids[g])
            ds = xr.Dataset(
                {
                    v: (("logement", "time"), agg[v].to_numpy(dtype="float32")[None, :])
                    for v in res_vars
                }
            )
            ds.to_zarr(
                paths.ZARR_PATH,
                group=g,
                region={
                    "logement": slice(i, i + 1),
                    "time": slice(0, len(res_grids[g])),
                },
            )
        if (i + 1) % 10 == 0 or i + 1 == len(logs):
            print(f"  [{i + 1}/{len(logs)}] {lid}")

    print(f"\n✓ Modèle écrit dans {paths.ZARR_PATH}")


if __name__ == "__main__":
    import sys

    src = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    build(src)
