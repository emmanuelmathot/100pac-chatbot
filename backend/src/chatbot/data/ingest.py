"""Ingestion des sources vers un modèle xarray/Zarr ``logement × time``.

Construit ``data/pac.zarr`` (Zarr v3) avec :

- un groupe ``fleet`` : dimension ``logement`` (100), coordonnées statiques issues
  des fichiers de métadonnées (type de source froide, SCOP déclaré, config...) ;
- des groupes de mesures ``raw`` / ``hourly`` / ``daily`` / ``monthly`` :
  dimensions ``logement × time``, peuplés pour les logements dont on possède le
  journal 1 min (ici ``002026``).

Sémantique des canaux (cf. dictionnaire) : ``pac`` et ``resistance_*`` sont des
**puissances électriques (W)** échantillonnées à la minute ; ``cc_*_calo`` /
``cc_*_frig`` sont des **incréments d'énergie thermique par minute (Wh)** — vérifié
empiriquement non monotones. D'où, sur une période :

    énergie élec (Wh) = Σ (P_W) / 60
    énergie thermique utile (Wh) = Σ (calo − frig)
    COP = énergie thermique utile / énergie élec
"""

from __future__ import annotations

import shutil

import numpy as np
import pandas as pd
import xarray as xr

from chatbot import paths
from chatbot.data import metadata

# Pas d'échantillonnage des journaux (1 minute).
STEP = pd.Timedelta(minutes=1)
MINUTES_PER_DAY = 1440

# Canaux du journal traités comme puissances (W) -> agrégés en MOYENNE.
POWER_CHANNELS = {"pac", "resistance_chauffage", "resistance_ecs"}
# Canaux du journal traités comme énergies par minute (Wh) -> agrégés en SOMME.
ENERGY_CHANNELS = {
    "cc_chauffage_calo",
    "cc_chauffage_frig",
    "cc_ecs_calo",
    "cc_ecs_frig",
}
# Tout le reste (températures, hygrométrie) -> MOYENNE.


def _read_log(path) -> pd.DataFrame:
    """Lit un journal 1 min, met le temps en UTC, réindexe sur grille régulière."""
    df = pd.read_excel(path, engine="openpyxl")
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = (
        df.dropna(subset=["time"])
        .drop_duplicates(subset=["time"], keep="first")
        .set_index("time")
        .sort_index()
    )
    # Grille 1 min régulière en UTC (les trous deviennent NaN).
    grid = pd.date_range(df.index.min(), df.index.max(), freq=STEP, tz="UTC")
    df = df.reindex(grid)
    df.index.name = "time"
    return df.astype("float32")


def _add_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les variables dérivées (énergies électrique et thermique)."""

    def col(name: str) -> pd.Series:
        """Série du canal, ou série de zéros si absent du journal."""
        if name in df.columns:
            return df[name].fillna(0.0)
        return pd.Series(0.0, index=df.index, dtype="float32")

    df["elec_power_w"] = (
        col("pac") + col("resistance_chauffage") + col("resistance_ecs")
    )
    # Énergie électrique par pas de 1 min : P(W) * (1/60) h = Wh.
    df["elec_energy_wh"] = df["elec_power_w"] / 60.0
    calo = col("cc_chauffage_calo") + col("cc_ecs_calo")
    frig = col("cc_chauffage_frig") + col("cc_ecs_frig")
    df["thermal_calo_wh"] = calo
    df["thermal_frig_wh"] = frig
    df["thermal_net_wh"] = calo - frig
    return df


# Classement agrégation par variable dérivée.
_SUM_DERIVED = {
    "elec_energy_wh",
    "thermal_calo_wh",
    "thermal_frig_wh",
    "thermal_net_wh",
}
_MEAN_DERIVED = {"elec_power_w"}


def _agg_kind(var: str) -> str:
    """Retourne ``"sum"`` ou ``"mean"`` selon la nature physique de la variable."""
    if var in ENERGY_CHANNELS or var in _SUM_DERIVED:
        return "sum"
    return "mean"


def _channel_attrs(var: str, dictionary: dict[str, metadata.ChannelMeta]) -> dict:
    """Attributs (unité, grandeur, nom) d'une variable, depuis le dictionnaire."""
    meta = dictionary.get(var)
    if meta is not None:
        return {"long_name": meta.name, "quantity": meta.quantity, "units": meta.unit}
    # Dérivés non présents au dictionnaire.
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


def _to_dataset(df: pd.DataFrame, logement: str, dictionary) -> xr.Dataset:
    """DataFrame (index time) -> Dataset (dims ``logement × time``) avec attrs."""
    data_vars = {}
    for col in df.columns:
        values = df[col].to_numpy(dtype="float32")[np.newaxis, :]  # (1, T)
        da = xr.DataArray(
            values,
            dims=("logement", "time"),
            attrs={**_channel_attrs(col, dictionary), "aggregation": _agg_kind(col)},
        )
        data_vars[col] = da
    ds = xr.Dataset(
        data_vars,
        coords={"logement": [logement], "time": df.index.values},
    )
    return ds


def _resample(ds: xr.Dataset, freq: str) -> xr.Dataset:
    """Ré-échantillonne en respectant l'agrégation par variable, + COP de période."""
    sum_vars = [str(v) for v in ds.data_vars if _agg_kind(str(v)) == "sum"]
    mean_vars = [str(v) for v in ds.data_vars if _agg_kind(str(v)) == "mean"]
    summed = ds[sum_vars].resample(time=freq).sum() if sum_vars else None
    meaned = ds[mean_vars].resample(time=freq).mean() if mean_vars else None
    out = xr.merge([d for d in (summed, meaned) if d is not None])
    for v in ds.data_vars:
        out[v].attrs = dict(ds[v].attrs)
    # COP de période = énergie thermique utile / énergie électrique (où élec > 0).
    elec = out["elec_energy_wh"]
    cop = xr.where(elec > 0, out["thermal_net_wh"] / elec, np.nan)
    cop.attrs = {
        "long_name": "COP réel de la période",
        "quantity": "ratio",
        "units": "-",
    }
    out["cop"] = cop
    return out


def _fleet_dataset(fleet: pd.DataFrame) -> xr.Dataset:
    """Table statique des 100 logements -> Dataset (dim ``logement``)."""
    data_vars = {}
    for col in fleet.columns:
        series = fleet[col]
        # Numérique si toute la colonne l'est, sinon chaîne (NaN -> "").
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().sum() >= series.notna().sum() and series.notna().any():
            values = numeric.to_numpy(dtype="float64")
        else:
            values = series.fillna("").astype(str).to_numpy()
        data_vars[col] = xr.DataArray(values, dims=("logement",))
    return xr.Dataset(data_vars, coords={"logement": fleet.index.to_numpy()})


def _encoding(ds: xr.Dataset, *, shard_time: bool) -> dict:
    """Encodage Zarr v3 : sharding ``1 fichier/jour`` pour les groupes minute."""
    enc: dict[str, dict] = {}
    n_log = ds.sizes["logement"]
    for raw_var in ds.data_vars:
        var = str(raw_var)
        if shard_time and "time" in ds[var].dims:
            t = ds.sizes["time"]
            chunk_t = min(MINUTES_PER_DAY, t)
            enc[var] = {
                "chunks": (1, chunk_t),
                "shards": (n_log, chunk_t),  # un shard = tous logements × 1 jour
            }
    return enc


def build(log_paths: list | None = None) -> None:
    """Construit ``data/pac.zarr`` à partir des sources."""
    dictionary = metadata.load_dictionary()
    fleet = metadata.load_fleet_metadata()

    if paths.ZARR_PATH.exists():
        shutil.rmtree(paths.ZARR_PATH)

    # 1) Groupe statique du parc (100 logements).
    fleet_ds = _fleet_dataset(fleet)
    fleet_ds.attrs["description"] = (
        "Caractéristiques statiques des 100 logements instrumentés"
    )
    fleet_ds.to_zarr(paths.ZARR_PATH, group="fleet", mode="w", zarr_format=3)
    print(
        f"[fleet] {fleet_ds.sizes['logement']} logements, {len(fleet_ds.data_vars)} attributs"
    )

    # 2) Mesures : un Dataset raw par logement disponible, concaténé sur ``logement``.
    log_paths = log_paths or [paths.LOG_XLSX]
    datasets = []
    for p in log_paths:
        logement = str(p.stem).replace("log_", "")
        print(f"[raw] lecture {p.name} (logement {logement})...")
        df = _add_derived(_read_log(p))
        datasets.append(_to_dataset(df, logement, dictionary))
    raw = xr.concat(datasets, dim="logement") if len(datasets) > 1 else datasets[0]
    raw.attrs["description"] = "Mesures 1 min (UTC)"
    raw.to_zarr(
        paths.ZARR_PATH,
        group="raw",
        mode="a",
        zarr_format=3,
        encoding=_encoding(raw, shard_time=True),
    )
    print(
        f"[raw] {raw.sizes['logement']} logement(s) × {raw.sizes['time']} pas de 1 min"
    )

    # 3) Agrégats ré-échantillonnés.
    for group, freq in [("hourly", "1h"), ("daily", "1D"), ("monthly", "1MS")]:
        agg = _resample(raw, freq)
        agg.attrs["description"] = f"Agrégats {group}"
        agg.to_zarr(paths.ZARR_PATH, group=group, mode="a", zarr_format=3)
        print(f"[{group}] {agg.sizes['time']} pas")

    print(f"\n✓ Modèle écrit dans {paths.ZARR_PATH}")


if __name__ == "__main__":
    build()
