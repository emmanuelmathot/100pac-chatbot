import numpy as np
import pandas as pd
import pytest
import xarray as xr
from fastapi.testclient import TestClient

from chatbot import paths
from chatbot.api.app import app
from chatbot.data import access


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def synthetic_store(tmp_path, monkeypatch):
    """Construit un petit store Zarr déterministe et redirige l'accès dessus.

    Deux logements (un air/eau, un géothermique) ; séries journalières sur 4 jours
    (2 en janvier = saison de chauffe, 2 en juillet) avec des valeurs choisies pour
    tester les formules d'agrégation et de COP.
    """
    store = tmp_path / "pac.zarr"

    # Parc : 2 logements.
    fleet = xr.Dataset(
        {
            "type_source_froide": ("logement", np.array(["air/eau", "eau/eau"])),
            "type_pac": ("logement", np.array(["Double service", "Chauffage seul"])),
            "scop_declare_basse_temperature": ("logement", np.array([4.0, 5.0])),
            "departement": ("logement", np.array([26.0, 75.0])),
        },
        coords={"logement": np.array(["A", "B"])},
    )
    fleet.to_zarr(store, group="fleet", mode="w", zarr_format=3)

    # Mesures journalières pour le logement A uniquement.
    times = pd.to_datetime(
        ["2024-01-01", "2024-01-02", "2024-07-01", "2024-07-02"]
    ).values
    daily = xr.Dataset(
        {
            "elec_energy_wh": (
                ("logement", "time"),
                [[1000.0, 1000.0, 1000.0, 1000.0]],
            ),
            "thermal_calo_wh": (("logement", "time"), [[2000.0, 2000.0, 100.0, 100.0]]),
            "thermal_frig_wh": (("logement", "time"), [[0.0, 0.0, 600.0, 600.0]]),
            "thermal_net_wh": (
                ("logement", "time"),
                [[2000.0, 2000.0, -500.0, -500.0]],
            ),
            "t_meteo": (("logement", "time"), [[5.0, 7.0, 25.0, 27.0]]),
        },
        coords={"logement": np.array(["A"]), "time": times},
    )
    daily["t_meteo"].attrs["units"] = "°C"
    # Mêmes données réutilisées pour les autres résolutions (suffit aux tests).
    for group in ("raw", "hourly", "daily", "monthly"):
        daily.to_zarr(store, group=group, mode="a", zarr_format=3)

    monkeypatch.setattr(paths, "ZARR_PATH", store)
    access.open_group.cache_clear()
    yield store
    access.open_group.cache_clear()
