"""Tests des fonctions pures d'ingestion (sans fichiers source)."""

import pandas as pd

from chatbot.data import ingest


def test_agg_kind_classification():
    # Énergies -> somme ; puissances et températures -> moyenne.
    assert ingest._agg_kind("cc_chauffage_calo") == "sum"
    assert ingest._agg_kind("elec_energy_wh") == "sum"
    assert ingest._agg_kind("thermal_net_wh") == "sum"
    assert ingest._agg_kind("pac") == "mean"
    assert ingest._agg_kind("t_meteo") == "mean"


def test_add_derived_energy_semantics():
    df = pd.DataFrame(
        {
            "pac": [600.0, 0.0],  # W
            "resistance_chauffage": [0.0, 60.0],
            "resistance_ecs": [0.0, 0.0],
            "cc_chauffage_calo": [10.0, 0.0],  # Wh / minute
            "cc_ecs_calo": [0.0, 5.0],
            "cc_chauffage_frig": [1.0, 0.0],
            "cc_ecs_frig": [0.0, 0.0],
        }
    )
    out = ingest._add_derived(df)
    # Puissance élec totale = pac + appoints.
    assert list(out["elec_power_w"]) == [600.0, 60.0]
    # Énergie élec par minute = P / 60.
    assert out["elec_energy_wh"].iloc[0] == 10.0
    assert out["elec_energy_wh"].iloc[1] == 1.0
    # Thermique : calo - frig.
    assert list(out["thermal_calo_wh"]) == [10.0, 5.0]
    assert list(out["thermal_frig_wh"]) == [1.0, 0.0]
    assert list(out["thermal_net_wh"]) == [9.0, 5.0]
