"""Tests déterministes des analyses sur un store Zarr synthétique."""

import math

from chatbot.data import analytics


def test_fleet_summary_counts_par_type(synthetic_store):
    s = analytics.fleet_summary()
    assert s["n_logements"] == 2
    assert s["par_type_source_froide"] == {"air/eau": 1, "eau/eau": 1}
    # SCOP déclaré moyen = (4.0 + 5.0) / 2.
    assert s["scop_declare_basse_temperature_moyen"] == 4.5
    assert s["logements_avec_mesures"] == ["A"]


def test_aggregate_mean_and_sum(synthetic_store):
    mean = analytics.aggregate("t_meteo", logement="A", how="mean")
    assert math.isclose(mean["value"], (5 + 7 + 25 + 27) / 4)
    assert mean["units"] == "°C"

    total = analytics.aggregate("elec_energy_wh", logement="A", how="sum")
    assert total["value"] == 4000.0


def test_performance_full_year(synthetic_store):
    p = analytics.performance("A")
    # élec = 4000 Wh = 4.0 kWh ; net = 2000+2000-500-500 = 3000 Wh = 3.0 kWh.
    assert p["elec_kwh"] == 4.0
    assert p["thermal_net_kwh"] == 3.0
    assert p["cop_reel"] == 0.75
    assert p["scop_declare_basse_temperature"] == 4.0
    assert p["n_jours"] == 4


def test_performance_heating_season_only_drops_summer(synthetic_store):
    p = analytics.performance("A", heating_season_only=True)
    # Seuls les 2 jours de janvier : élec 2000 Wh, net 4000 Wh -> COP 2.0.
    assert p["n_jours"] == 2
    assert p["elec_kwh"] == 2.0
    assert p["thermal_net_kwh"] == 4.0
    assert p["cop_reel"] == 2.0


def test_unknown_logement_raises(synthetic_store):
    import pytest

    with pytest.raises(KeyError):
        analytics.performance("ZZZ")


def test_select_logements_filter(synthetic_store):
    from chatbot.data import access

    assert access.select_logements(type_source_froide="eau/eau") == ["B"]
    assert access.select_logements(type_source_froide="air/eau") == ["A"]
